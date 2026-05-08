# cogs/ranking/assign_rank.py
"""
Cog de gestion des rangs Valorant.
Permet aux utilisateurs de lier leur compte Valorant et met a jour automatiquement
leurs roles Discord en fonction de leur rang.
"""

import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import discord
from discord.ext import commands, tasks

from cogs.ranking.services.ranking_service import RankingService
from cogs.ranking.services.valorant_pipeline import (
    ValorantPipeline,
    UserPipelineState,
    PipelineResult,
    LocalRateLimitReached,
)
from cogs.ranking.views import EmbedButtonsView
from integrations.henrikdev.service import HenrikDevService
from integrations.exceptions import RateLimitError

logger = logging.getLogger(__name__)

EMBED_MESSAGE_TYPE = "embed_rank"


class EmbedCog(commands.Cog):
    """Cog principal pour la gestion des rangs Valorant."""

    def __init__(
        self,
        bot: commands.Bot,
        ranking_service: RankingService,
        henrik_service: HenrikDevService,
    ):
        self.bot = bot
        self._ranking_svc = ranking_service
        self._pipeline = ValorantPipeline(henrik_service)

        logger.info("EmbedCog initialise.")
        self._init_task = asyncio.create_task(self._async_init())
        self.refresh_roles_cache_task.start()

    async def _async_init(self):
        """Initialisation asynchrone apres que le bot soit pret."""
        await self.bot.wait_until_ready()

        # Recharger l'embed persistant
        await self.reload_persistent_embed()

        # Sync de presence au demarrage
        await self._startup_presence_sync()

        # Demarrer la boucle de mise a jour
        if not self.update_roles_loop.is_running():
            self.update_roles_loop.start()

    def cog_unload(self):
        self.refresh_roles_cache_task.cancel()
        self.update_roles_loop.cancel()
        self._init_task.cancel()

    async def _startup_presence_sync(self):
        """
        Synchronise l'etat de presence au demarrage.
        Rattrape les evenements join/leave manques pendant le downtime.
        Une seule transaction bulk au lieu de N appels individuels.
        """
        logger.info("[startup_presence_sync] Debut de la synchronisation de presence...")

        valo_discord_ids = set(await self._ranking_svc.get_all_discord_ids())
        present_ids = {m.id for g in self.bot.guilds for m in g.members}

        reactivated, deactivated = await self._ranking_svc.sync_presence(
            present_ids & valo_discord_ids, valo_discord_ids,
        )

        logger.info(
            f"[startup_presence_sync] Termine: {reactivated} reactives, "
            f"{deactivated} desactives"
        )

    async def reload_persistent_embed(self):
        """Recharge les vues des embeds persistants."""
        logger.info("Rechargement de l'embed persistant...")

        for guild in self.bot.guilds:
            message_data = await self._ranking_svc.get_persistent_message(
                guild.id, EMBED_MESSAGE_TYPE,
            )
            if not message_data:
                logger.debug(f"Aucun message persistant pour guild {guild.id}.")
                continue

            channel = guild.get_channel(message_data["channel_id"])
            if not channel:
                logger.warning(f"Canal introuvable: {message_data['channel_id']} dans guild={guild.id}")
                continue

            try:
                message = await channel.fetch_message(message_data["message_id"])
                view = EmbedButtonsView(self)
                self.bot.add_view(view, message_id=message.id)
                logger.info(f"Vue ajoutee pour message {message.id} dans {channel.name}")
            except discord.NotFound:
                logger.warning(f"Message introuvable: {message_data['message_id']}")
            except Exception as e:
                logger.error(f"Erreur rechargement embed: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"Cog {self.__class__.__name__} pret.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Reactive le tracking si un utilisateur revient."""
        if await self._ranking_svc.account_linked(member.id):
            reactivated = await self._ranking_svc.reactivate(member.id)
            if reactivated:
                logger.info(f"[on_member_join] Tracking reactive pour {member.id}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Desactive le tracking si l'utilisateur quitte tous les serveurs."""
        for guild in self.bot.guilds:
            if guild.id != member.guild.id and guild.get_member(member.id):
                return  # Encore present ailleurs

        if await self._ranking_svc.account_linked(member.id):
            deactivated = await self._ranking_svc.mark_inactive(member.id)
            if deactivated:
                logger.info(f"[on_member_remove] {member.id} marque inactif (quitte tous les guilds)")

    @commands.command(name="send_embed_rang")
    @commands.has_permissions(administrator=True)
    async def send_embed(self, ctx: commands.Context):
        """Envoie l'embed de gestion Valorant."""
        guild_id = ctx.guild.id
        channel_id = await self._ranking_svc.get_channel_id(guild_id, "rang")
        if not channel_id:
            await ctx.send("Aucun salon defini pour l'action 'rang'.", delete_after=10)
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Le salon d'embed specifie est introuvable.", delete_after=10)
            return

        message_data = await self._ranking_svc.get_persistent_message(guild_id, EMBED_MESSAGE_TYPE)
        if message_data:
            try:
                await channel.fetch_message(message_data["message_id"])
                await ctx.send("L'embed a deja ete envoye dans ce salon.", delete_after=10)
                return
            except discord.NotFound:
                pass

        embed = discord.Embed(
            title="Gestion de vos informations Valorant",
            description=(
                "Ce message vous permet de **renseigner**, **changer** ou **effacer** "
                "vos donnees Valorant.\n\n"
                "**Instructions :**\n"
                "1. Cliquez sur le bouton bleu pour lier votre compte Valorant.\n"
                "2. Un formulaire s'ouvrira ou vous devrez entrer :\n"
                "   - **Pseudo** : Votre pseudo Valorant (exemple : `globeX`).\n"
                "   - **Tag** : Votre tag Valorant sans le `#` (exemple : `meow`).\n\n"
                "3. Pour changer de compte, utilisez le bouton gris.\n\n"
                "*Note : Vous devez d'abord accepter le reglement.*\n"
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Tenez a jour vos informations pour obtenir le role correspondant a votre rang.")

        view = EmbedButtonsView(self)
        try:
            message = await channel.send(embed=embed, view=view)
            success = await self._ranking_svc.store_persistent_message(
                guild_id, ctx.guild.name, channel.id, message.id, EMBED_MESSAGE_TYPE,
            )
            if success:
                await ctx.send(f"Embed envoye dans {channel.mention}.", delete_after=10)
                logger.info(f"Embed envoye dans {channel.id} par {ctx.author}")
            else:
                await ctx.send("Embed envoye, mais erreur de stockage en BDD.", delete_after=10)
        except Exception as e:
            logger.error(f"Erreur envoi embed: {e}")
            await ctx.send("Une erreur est survenue lors de l'envoi de l'embed.", delete_after=10)

    async def notify_duplicate_pseudo_tag(
        self,
        existing_user: discord.User,
        current_user: discord.User,
        pseudo: str,
        tag: str,
        guild: discord.Guild,
    ):
        """Notifie les moderateurs d'un doublon de pseudo/tag."""
        channel_id = await self._ranking_svc.get_channel_id(guild.id, "duplicate_alert")
        if not channel_id:
            channel_id = await self._ranking_svc.get_channel_id(guild.id, "moderation")
        if not channel_id:
            channel_id = await self._ranking_svc.get_channel_id(guild.id, "rank_up")
        if not channel_id:
            logger.error(f"[notify_duplicate] Aucun channel configure pour guild {guild.id}")
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            logger.error(f"Salon {channel_id} introuvable dans guild {guild.id}")
            return

        embed = discord.Embed(
            title="Doublon de Pseudo Valorant Detecte",
            description=(
                f"Un doublon a ete detecte pour le pseudo et tag Valorant : **{pseudo}#{tag}**.\n\n"
                f"**Utilisateur 1 :** {existing_user.mention} (ID: {existing_user.id})\n"
                f"**Utilisateur 2 :** {current_user.mention} (ID: {current_user.id})\n\n"
                "Veuillez resoudre ce doublon."
            ),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="Gestion des Doublons de Pseudo Valorant")

        try:
            await channel.send(embed=embed)
            logger.info(f"Embed doublon envoye pour {current_user} et {existing_user}")
        except Exception as e:
            logger.error(f"Erreur envoi embed doublon: {e}")

    # -------------------------------------------------------------------------
    # Boucle de mise a jour pipeline
    # -------------------------------------------------------------------------

    @tasks.loop(seconds=5)
    async def update_roles_loop(self):
        """Boucle principale de mise a jour des rangs via le pipeline."""
        try:
            await self._process_pipeline_batch()
        except RateLimitError as e:
            logger.warning(f"[update_roles_loop] RateLimitError: {e}. Pause 60s.")
            self.update_roles_loop.change_interval(seconds=60)
        except LocalRateLimitReached as e:
            delay = max(1, e.reset_seconds)
            logger.info(f"[update_roles_loop] Limite locale atteinte. Pause {delay}s.")
            self.update_roles_loop.change_interval(seconds=delay)
        except Exception as e:
            logger.exception(f"[update_roles_loop] Erreur inattendue: {e}")
            self.update_roles_loop.change_interval(seconds=60)
        else:
            self.update_roles_loop.change_interval(seconds=5)

    @update_roles_loop.before_loop
    async def before_update_roles_loop(self):
        await self.bot.wait_until_ready()

    async def _process_pipeline_batch(self):
        """Traite un batch d'utilisateurs via le pipeline."""
        users = await self._ranking_svc.get_users_for_pipeline(limit=20)

        if not users:
            logger.debug("[_process_pipeline_batch] Aucun utilisateur a traiter.")
            return

        logger.info(f"[_process_pipeline_batch] Traitement de {len(users)} utilisateurs.")

        guild_list = list(self.bot.guilds)
        ban_role_cache = await self._load_ban_role_cache(guild_list)

        stats = {"processed": 0, "updated": 0, "errors": 0, "skipped": 0}

        for record in users:
            state = UserPipelineState(
                discord_id=record["discord_id"],
                pseudo=record["valorant_pseudo"],
                tag=record["valorant_tag"],
                puuid=record.get("valorant_puuid"),
                region=record.get("valorant_region"),
                platform=record.get("valorant_platform"),
                rank=record.get("valorant_rank"),
                elo=record.get("valorant_elo"),
                error_count=record.get("error_count") or 0,
                last_error_at=record.get("last_error_at"),
            )

            if self._pipeline.should_skip_due_to_errors(state):
                stats["skipped"] += 1
                continue

            if not self._pipeline._check_local_rate_limit():
                reset = self._pipeline.get_local_rate_limit_reset()
                raise LocalRateLimitReached(reset)

            member = self._find_member_in_cache(state.discord_id, guild_list)
            if not member:
                # Membre absent : mark_inactive suffit (filtre par is_active dans le pipeline)
                await self._ranking_svc.mark_inactive(state.discord_id)
                stats["skipped"] += 1
                continue

            if self._is_member_banned(member, ban_role_cache):
                await self._ranking_svc.update_pipeline_success(state.discord_id)
                stats["skipped"] += 1
                continue

            stats["processed"] += 1

            try:
                result, rate_limit = await self._pipeline.execute_step(state)
            except RateLimitError:
                raise
            except Exception as e:
                logger.error(f"[_process_pipeline_batch] Erreur execute_step pour {state.discord_id}: {e}")
                await self._ranking_svc.update_pipeline_error(state.discord_id)
                stats["errors"] += 1
                continue

            if result.success:
                await self._ranking_svc.update_pipeline_success(
                    state.discord_id,
                    puuid=result.puuid,
                    region=result.region,
                    platform=result.platform,
                    rank=result.rank,
                    elo=result.elo,
                    pseudo=result.api_name,
                    tag=result.api_tag,
                    current_season=result.current_season,
                    current_act=result.current_act,
                )

                if result.rank:
                    await self._update_member_role(member, result.rank, state.rank)
                    stats["updated"] += 1
            else:
                await self._ranking_svc.update_pipeline_error(state.discord_id)
                stats["errors"] += 1

                if result.should_notify_user:
                    await self._notify_user_error(member, state, result)

            if rate_limit:
                pause = self._pipeline.should_pause_for_rate_limit(rate_limit)
                if pause > 0:
                    logger.info(f"Rate limit bas (remaining={rate_limit.remaining}), pause {pause}s")
                    await asyncio.sleep(pause)

        logger.info(
            f"[_process_pipeline_batch] Batch termine: {stats['processed']} traites, "
            f"{stats['updated']} mis a jour, {stats['errors']} erreurs, {stats['skipped']} ignores"
        )

    async def _load_ban_role_cache(self, guild_list: List[discord.Guild]) -> Dict[int, Optional[int]]:
        """Charge le cache des roles de ban pour chaque guild."""
        cache = {}
        for guild in guild_list:
            try:
                cache[guild.id] = await self._ranking_svc.get_ban_role_id(guild.id)
            except Exception:
                cache[guild.id] = None
        return cache

    def _find_member_in_cache(
        self, discord_id: int, guild_list: List[discord.Guild]
    ) -> Optional[discord.Member]:
        """Trouve un membre dans le cache des guilds."""
        for guild in guild_list:
            member = guild.get_member(discord_id)
            if member:
                return member
        return None

    def _is_member_banned(
        self, member: discord.Member, ban_role_cache: Dict[int, Optional[int]]
    ) -> bool:
        """Verifie si le membre a un role de ban."""
        ban_role_id = ban_role_cache.get(member.guild.id)
        if ban_role_id:
            ban_role = member.guild.get_role(ban_role_id)
            if ban_role and ban_role in member.roles:
                return True
        return False

    async def _update_member_role(
        self,
        member: discord.Member,
        new_rank: str,
        _old_rank: Optional[str] = None,
    ):
        """Met a jour le role de rang du membre."""
        role_key = RankingService.get_role_key_for_rank(new_rank)
        if not role_key:
            logger.warning(f"[_update_member_role] Aucun mapping pour rang '{new_rank}'")
            return

        role_mappings = await self._ranking_svc.get_role_mappings(member.guild.id)
        if not role_mappings:
            logger.warning(f"[_update_member_role] Pas de config roles pour guild={member.guild.id}")
            return

        discord_role_id = role_mappings.get(role_key)
        if not discord_role_id:
            logger.warning(f"[_update_member_role] Pas de role_id pour {role_key}")
            return

        desired_role = member.guild.get_role(discord_role_id)
        if not desired_role:
            logger.warning(f"[_update_member_role] Role introuvable: {discord_role_id}")
            return

        rank_role_ids = set(role_mappings.values())
        roles_to_remove = [
            r for r in member.roles
            if r.id in rank_role_ids and r.id != desired_role.id
        ]

        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason="Mise a jour rang Valorant")
                logger.debug(f"Roles supprimes pour {member.display_name}: {[r.name for r in roles_to_remove]}")
            except Exception as e:
                logger.error(f"Erreur remove_roles pour {member.display_name}: {e}")
                return

        if desired_role not in member.roles:
            try:
                await member.add_roles(desired_role, reason="Mise a jour rang Valorant")
                logger.info(f"Role '{desired_role.name}' ajoute a {member.display_name}")
            except Exception as e:
                logger.error(f"Erreur add_roles pour {member.display_name}: {e}")

    async def _notify_user_error(
        self,
        member: discord.Member,
        state: UserPipelineState,
        result: PipelineResult,
    ):
        """Notifie l'utilisateur d'une erreur persistante."""
        last_notif = await self._ranking_svc.get_last_notification(state.discord_id)
        now = datetime.now(timezone.utc)

        if last_notif and (now - last_notif) < timedelta(days=7):
            return

        try:
            rank_channel_id = await self._ranking_svc.get_channel_id(member.guild.id, "rang")
            channel_mention = f"<#{rank_channel_id}>" if rank_channel_id else "le salon de rang"

            await member.send(
                f"La recuperation de vos informations Valorant a echoue pour "
                f"**{state.pseudo}#{state.tag}**.\n"
                f"Erreur: {result.error_message or 'Inconnue'}\n\n"
                f"Veuillez verifier vos identifiants ou modifier vos informations "
                f"dans {channel_mention}."
            )
            await self._ranking_svc.update_last_notification(state.discord_id, now)
            logger.info(f"Notification erreur envoyee a {state.discord_id}")
        except discord.Forbidden:
            logger.debug(f"Impossible d'envoyer DM a {state.discord_id} (DMs fermes)")
        except Exception as e:
            logger.error(f"Erreur envoi notification a {state.discord_id}: {e}")

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        await ctx.send("Pong!")

    @tasks.loop(hours=1)
    async def refresh_roles_cache_task(self):
        """Rafraichit le cache des roles toutes les heures."""
        logger.info("Debut du rafraichissement du cache des roles.")
        for guild in self.bot.guilds:
            await self._ranking_svc.refresh_role_mappings(guild.id)
        logger.info("Rafraichissement du cache des roles termine.")

    @refresh_roles_cache_task.before_loop
    async def before_refresh_roles_cache_task(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    ranking_service = getattr(bot, "ranking_service", None)
    if ranking_service is None:
        logger.error("ranking_service non initialise. EmbedCog ne sera pas charge.")
        return

    henrik_service = getattr(bot, "henrik_service", None)
    if henrik_service is None:
        logger.error("henrik_service non initialise. EmbedCog ne sera pas charge.")
        return

    await bot.add_cog(EmbedCog(bot, ranking_service, henrik_service))
    logger.info("Cog EmbedCog charge.")
