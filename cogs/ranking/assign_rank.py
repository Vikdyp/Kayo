# cogs/ranking/assign_rank.py
"""
Cog de gestion des rangs Valorant.
Permet aux utilisateurs de lier leur compte Valorant et met à jour automatiquement
leurs rôles Discord en fonction de leur rang.
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import discord
from discord.ext import commands, tasks

from cogs.ranking.services.assign_rank_service import AssignRankService
from cogs.ranking.services.valorant_pipeline import (
    ValorantPipeline,
    UserPipelineState,
    PipelineResult,
    LocalRateLimitReached,
)
from integrations.http_client import HTTPClient
from integrations.henrikdev.service import HenrikDevService
from integrations.exceptions import RateLimitError

logger = logging.getLogger(__name__)

EMBED_MESSAGE_TYPE = "embed_rank"

# Mapping rang Valorant -> clé role (guild_roles.key)
VALORANT_RANK_TO_ROLE_KEY = {
    "Iron 1": "fer", "Iron 2": "fer", "Iron 3": "fer",
    "Bronze 1": "bronze", "Bronze 2": "bronze", "Bronze 3": "bronze",
    "Silver 1": "argent", "Silver 2": "argent", "Silver 3": "argent",
    "Gold 1": "or", "Gold 2": "or", "Gold 3": "or",
    "Platinum 1": "platine", "Platinum 2": "platine", "Platinum 3": "platine",
    "Diamond 1": "diamant", "Diamond 2": "diamant", "Diamond 3": "diamant",
    "Ascendant 1": "ascendant", "Ascendant 2": "ascendant", "Ascendant 3": "ascendant",
    "Immortal 1": "immortel", "Immortal 2": "immortel", "Immortal 3": "immortel",
    "Radiant": "radiant",
    "Unrated": "no_rank",
}


class PseudoTagModal(discord.ui.Modal):
    """Modal pour renseigner ou changer son pseudo/tag Valorant."""

    def __init__(self, user: discord.User, cog: "EmbedCog", is_change: bool = False):
        title = "Changer de compte Valorant" if is_change else "Renseignez votre Pseudo et Tag Valorant"
        super().__init__(title=title)
        self.user = user
        self.cog = cog
        self.is_change = is_change

        self.pseudo = discord.ui.TextInput(
            label="Pseudo",
            placeholder="Entrez votre pseudo Valorant (exemple: Swyzin)",
            max_length=32, required=True,
        )
        self.tag = discord.ui.TextInput(
            label="Tag",
            placeholder="Entrez votre tag Valorant sans le # (exemple: meow)",
            max_length=6, required=True,
        )
        self.add_item(self.pseudo)
        self.add_item(self.tag)

    async def on_submit(self, interaction: discord.Interaction):
        pseudo = self.pseudo.value.strip()
        tag = self.tag.value.strip()

        if not pseudo:
            await interaction.response.send_message("Le pseudo ne doit pas etre vide.", ephemeral=True)
            return

        if not tag.isalnum():
            await interaction.response.send_message(
                "Le tag ne doit contenir que des lettres et des chiffres.", ephemeral=True
            )
            return

        svc = self.cog._service

        # Vérifier les doublons
        existing_discord_id = await svc.get_user_by_pseudo_tag(pseudo, tag)
        if existing_discord_id:
            if existing_discord_id == self.user.id:
                await interaction.response.send_message(
                    "Vous avez deja enregistre ce pseudo et tag Valorant.", ephemeral=True
                )
                return
            else:
                await interaction.response.send_message(
                    "Ce pseudo et tag Valorant sont deja utilises par un autre utilisateur.", ephemeral=True
                )
                existing_user = self.cog.bot.get_user(existing_discord_id)
                if not existing_user:
                    try:
                        existing_user = await self.cog.bot.fetch_user(existing_discord_id)
                    except discord.NotFound:
                        existing_user = None
                if existing_user:
                    await self.cog._notify_duplicate(existing_user, self.user, pseudo, tag, interaction.guild)
                return

        # Vérifier que l'utilisateur a accepté le règlement
        has_accepted = await self.cog.bot.guild_members_svc.has_accepted_rules(
            interaction.guild.id, interaction.user.id
        )
        if not has_accepted:
            await interaction.response.send_message(
                "Vous devez d'abord accepter le reglement.", ephemeral=True
            )
            return

        try:
            if self.is_change:
                success = await svc.reset_user_for_account_change(interaction.user.id, pseudo, tag)
                message = (
                    f"Votre compte Valorant a ete change vers : {pseudo}#{tag}\n"
                    "La mise a jour de votre rang commencera bientot."
                )
            else:
                success = await svc.update_user_valorant_info(interaction.user.id, pseudo, tag)
                message = f"Vos informations Valorant ont ete enregistrees : {pseudo}#{tag}"

            if success:
                await interaction.response.send_message(message, ephemeral=True)
            else:
                await interaction.response.send_message(
                    "Une erreur est survenue. Veuillez reessayer plus tard.", ephemeral=True
                )
        except Exception as e:
            logger.error(f"Erreur enregistrement pour {interaction.user}: {e}")
            await interaction.response.send_message(
                "Une erreur est survenue. Veuillez reessayer plus tard.", ephemeral=True
            )


class EmbedButtonsView(discord.ui.View):
    """Vue avec les boutons pour l'embed de gestion Valorant."""

    def __init__(self, cog: "EmbedCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Renseigner Pseudo/Tag Valorant",
        style=discord.ButtonStyle.primary,
        custom_id="button:pseudo_tag",
    )
    async def pseudo_tag_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PseudoTagModal(interaction.user, self.cog, is_change=False)
        if not interaction.response.is_done():
            await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Changer de compte Valorant",
        style=discord.ButtonStyle.secondary,
        custom_id="button:change_valo_account",
    )
    async def change_account_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not await self.cog._service.valorant_account_linked(interaction.user.id):
            await interaction.response.send_message(
                "Vous n'avez pas encore de compte Valorant lie. Utilisez le bouton bleu.", ephemeral=True
            )
            return
        modal = PseudoTagModal(interaction.user, self.cog, is_change=True)
        if not interaction.response.is_done():
            await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Effacer mes donnees Valorant",
        style=discord.ButtonStyle.danger,
        custom_id="button:delete_valo_data",
    )
    async def delete_valo_data_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        try:
            success = await self.cog._service.delete_valo_data(interaction.user.id)
            msg = "Vos donnees Valorant ont ete supprimees." if success else "Erreur lors de la suppression."
            await interaction.followup.send(msg, ephemeral=True)
        except Exception as e:
            logger.error(f"Erreur suppression valo data {interaction.user}: {e}")
            await interaction.followup.send("Erreur lors de la suppression.", ephemeral=True)


class EmbedCog(commands.Cog):
    """Cog principal pour la gestion des rangs Valorant."""

    def __init__(self, bot: commands.Bot, service: AssignRankService):
        self.bot = bot
        self._service = service
        self.message_id = None

        self._http_client: Optional[HTTPClient] = None
        self._henrik_service: Optional[HenrikDevService] = None
        self._pipeline: Optional[ValorantPipeline] = None

        logger.info("EmbedCog initialise.")
        self.bot.loop.create_task(self._async_init())
        self.refresh_roles_cache_task.start()

    async def _async_init(self):
        await self.bot.wait_until_ready()

        api_key = os.getenv("HENRIK_VALO_KEY")
        if not api_key:
            logger.error("HENRIK_VALO_KEY non defini!")
            return

        self._http_client = HTTPClient(timeout_seconds=15.0)
        await self._http_client.__aenter__()
        self._henrik_service = HenrikDevService(self._http_client, api_key)
        self._pipeline = ValorantPipeline(self._henrik_service)

        await self._reload_persistent_embed()
        await self._startup_presence_sync()
        self.bot.loop.create_task(self._update_roles_loop())

    def cog_unload(self):
        self.refresh_roles_cache_task.cancel()
        if self._http_client:
            self.bot.loop.create_task(self._http_client.__aexit__(None, None, None))

    # ------------------------------------------------------------------
    # Startup sync
    # ------------------------------------------------------------------

    async def _startup_presence_sync(self):
        logger.info("[startup_presence_sync] Debut synchronisation...")
        valo_ids = set(await self._service.get_all_valorant_discord_ids())

        present_ids = set()
        for guild in self.bot.guilds:
            for member in guild.members:
                present_ids.add(member.id)

        reactivated = 0
        for did in valo_ids & present_ids:
            if await self._service.reactivate_user(did):
                reactivated += 1

        deactivated = 0
        for did in valo_ids - present_ids:
            if await self._service.mark_user_inactive(did):
                deactivated += 1

        logger.info(f"[startup_presence_sync] {reactivated} reactives, {deactivated} desactives")

    async def _reload_persistent_embed(self):
        for guild in self.bot.guilds:
            msg_info = await self._service.get_persistent_message(guild.id, EMBED_MESSAGE_TYPE)
            if not msg_info:
                continue

            channel = guild.get_channel(msg_info.channel_id)
            if not channel:
                continue

            try:
                message = await channel.fetch_message(msg_info.message_id)
                view = EmbedButtonsView(self)
                self.bot.add_view(view, message_id=message.id)
            except discord.NotFound:
                pass
            except Exception as e:
                logger.error(f"Erreur rechargement embed: {e}")

    # ------------------------------------------------------------------
    # Listeners
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if await self._service.valorant_account_linked(member.id):
            if await self._service.reactivate_user(member.id):
                logger.info(f"[on_member_join] Tracking reactive pour {member.id}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        for guild in self.bot.guilds:
            if guild.id != member.guild.id and guild.get_member(member.id):
                return
        if await self._service.valorant_account_linked(member.id):
            if await self._service.mark_user_inactive(member.id):
                logger.info(f"[on_member_remove] {member.id} marque inactif")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @commands.command(name="send_embed_rang")
    @commands.has_permissions(administrator=True)
    async def send_embed(self, ctx: commands.Context):
        guild = ctx.guild
        channel_id = await self._service.get_channel_id(guild.id, "rang")
        if not channel_id:
            await ctx.send("Aucun salon defini pour 'rang'.", delete_after=10)
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Salon d'embed introuvable.", delete_after=10)
            return

        msg_info = await self._service.get_persistent_message(guild.id, EMBED_MESSAGE_TYPE)
        if msg_info:
            try:
                await channel.fetch_message(msg_info.message_id)
                await ctx.send("L'embed a deja ete envoye.", delete_after=10)
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
                "   - **Pseudo** : Votre pseudo Valorant.\n"
                "   - **Tag** : Votre tag sans le `#`.\n\n"
                "3. Pour changer de compte, utilisez le bouton gris.\n\n"
                "*Note : Vous devez d'abord accepter le reglement.*\n"
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Tenez a jour vos informations pour obtenir le role correspondant a votre rang.")

        view = EmbedButtonsView(self)
        try:
            message = await channel.send(embed=embed, view=view)
            await self._service.store_persistent_message(
                guild.id, guild.name, channel.id, message.id, EMBED_MESSAGE_TYPE
            )
            await ctx.send(f"Embed envoye dans {channel.mention}.", delete_after=10)
        except Exception as e:
            logger.error(f"Erreur envoi embed: {e}")
            await ctx.send("Erreur lors de l'envoi.", delete_after=10)

    # ------------------------------------------------------------------
    # Notification doublon
    # ------------------------------------------------------------------

    async def _notify_duplicate(
        self, existing_user: discord.User, current_user: discord.User,
        pseudo: str, tag: str, guild: discord.Guild,
    ):
        channel_id = await self._service.get_channel_id(guild.id, "duplicate_alert")
        if not channel_id:
            channel_id = await self._service.get_channel_id(guild.id, "modération")
        if not channel_id:
            channel_id = await self._service.get_channel_id(guild.id, "rank_up")
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        embed = discord.Embed(
            title="Doublon de Pseudo Valorant Detecte",
            description=(
                f"Doublon pour **{pseudo}#{tag}**.\n\n"
                f"**Utilisateur 1 :** {existing_user.mention} (ID: {existing_user.id})\n"
                f"**Utilisateur 2 :** {current_user.mention} (ID: {current_user.id})"
            ),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Erreur envoi embed doublon: {e}")

    # ------------------------------------------------------------------
    # Pipeline loop
    # ------------------------------------------------------------------

    async def _update_roles_loop(self):
        while True:
            if not self._pipeline:
                await asyncio.sleep(30)
                continue
            try:
                await self._process_pipeline_batch()
            except RateLimitError:
                await asyncio.sleep(60)
            except LocalRateLimitReached as e:
                await asyncio.sleep(e.reset_seconds)
            except Exception as e:
                logger.exception(f"[update_roles_loop] Erreur: {e}")
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(5)

    async def _process_pipeline_batch(self):
        users = await self._service.get_users_for_pipeline(limit=20)
        if not users:
            return

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
                raise LocalRateLimitReached(self._pipeline.get_local_rate_limit_reset())

            member = self._find_member(state.discord_id, guild_list)
            if not member:
                await self._service.mark_user_inactive(state.discord_id)
                await self._service.update_pipeline_error(state.discord_id)
                stats["errors"] += 1
                continue

            if self._is_banned(member, ban_role_cache):
                await self._service.update_pipeline_success(state.discord_id)
                stats["skipped"] += 1
                continue

            stats["processed"] += 1

            try:
                result, rate_limit = await self._pipeline.execute_step(state)
            except RateLimitError:
                raise
            except Exception as e:
                logger.error(f"Erreur execute_step {state.discord_id}: {e}")
                await self._service.update_pipeline_error(state.discord_id)
                stats["errors"] += 1
                continue

            if result.success:
                await self._service.update_pipeline_success(
                    state.discord_id,
                    puuid=result.puuid, region=result.region,
                    platform=result.platform, rank=result.rank, elo=result.elo,
                )
                if result.rank:
                    await self._update_member_role(member, result.rank, state.rank)
                    stats["updated"] += 1
            else:
                await self._service.update_pipeline_error(state.discord_id)
                stats["errors"] += 1
                if result.should_notify_user:
                    await self._notify_user_error(member, state, result)

            if rate_limit:
                pause = self._pipeline.should_pause_for_rate_limit(rate_limit)
                if pause > 0:
                    await asyncio.sleep(pause)

        logger.info(
            f"[batch] {stats['processed']} traites, {stats['updated']} maj, "
            f"{stats['errors']} erreurs, {stats['skipped']} ignores"
        )

    async def _load_ban_role_cache(self, guild_list: List[discord.Guild]) -> Dict[int, Optional[int]]:
        cache = {}
        mod_svc = getattr(self.bot, "moderation_service", None)
        for guild in guild_list:
            try:
                cache[guild.id] = await mod_svc.get_ban_role_id(guild.id) if mod_svc else None
            except Exception:
                cache[guild.id] = None
        return cache

    @staticmethod
    def _find_member(discord_id: int, guild_list: List[discord.Guild]) -> Optional[discord.Member]:
        for guild in guild_list:
            member = guild.get_member(discord_id)
            if member:
                return member
        return None

    @staticmethod
    def _is_banned(member: discord.Member, ban_role_cache: Dict[int, Optional[int]]) -> bool:
        ban_role_id = ban_role_cache.get(member.guild.id)
        if ban_role_id:
            ban_role = member.guild.get_role(ban_role_id)
            if ban_role and ban_role in member.roles:
                return True
        return False

    async def _update_member_role(self, member: discord.Member, new_rank: str, _old_rank: Optional[str] = None):
        role_key = VALORANT_RANK_TO_ROLE_KEY.get(new_rank)
        if not role_key:
            return

        role_mappings = await self._service.get_role_mappings(member.guild.id)
        if not role_mappings:
            return

        discord_role_id = role_mappings.get(role_key)
        if not discord_role_id:
            return

        desired_role = member.guild.get_role(discord_role_id)
        if not desired_role:
            return

        rank_role_ids = set(role_mappings.values())
        roles_to_remove = [r for r in member.roles if r.id in rank_role_ids and r.id != desired_role.id]

        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason="Mise a jour rang Valorant")
            except Exception as e:
                logger.error(f"Erreur remove_roles {member}: {e}")
                return

        if desired_role not in member.roles:
            try:
                await member.add_roles(desired_role, reason="Mise a jour rang Valorant")
            except Exception as e:
                logger.error(f"Erreur add_roles {member}: {e}")

    async def _notify_user_error(self, member: discord.Member, state: UserPipelineState, result: PipelineResult):
        last_notif = await self._service.get_last_notification(state.discord_id)
        now = datetime.now(timezone.utc)
        if last_notif and (now - last_notif) < timedelta(days=7):
            return

        try:
            rank_channel_id = await self._service.get_channel_id(member.guild.id, "rang")
            channel_mention = f"<#{rank_channel_id}>" if rank_channel_id else "le salon de rang"
            await member.send(
                f"La recuperation de vos informations Valorant a echoue pour "
                f"**{state.pseudo}#{state.tag}**.\n"
                f"Erreur: {result.error_message or 'Inconnue'}\n\n"
                f"Veuillez verifier vos identifiants ou modifier vos informations dans {channel_mention}."
            )
            await self._service.update_last_notification(state.discord_id, now)
        except discord.Forbidden:
            pass
        except Exception as e:
            logger.error(f"Erreur envoi notification {state.discord_id}: {e}")

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        await ctx.send("Pong!")

    @tasks.loop(hours=1)
    async def refresh_roles_cache_task(self):
        for guild in self.bot.guilds:
            await self._service.refresh_role_mappings(guild.id)

    @refresh_roles_cache_task.before_loop
    async def before_refresh_roles_cache_task(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    from database.services.valorant_info_service import ValorantInfoService
    valo_info_svc = ValorantInfoService(bot.db)
    service = AssignRankService(
        valo_info_svc, bot.channel_config_svc, bot.role_config_svc, bot.persistent_msg_svc
    )
    await bot.add_cog(EmbedCog(bot, service))
    logger.info("EmbedCog charge.")
