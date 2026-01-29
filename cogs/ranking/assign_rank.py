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

from cogs.ranking.services.assign_rank_service import (
    store_persistent_message,
    get_persistent_message,
    get_channel_id,
    update_user_valorant_info,
    get_all_users_with_valo_info,
    get_role_mappings,
    refresh_role_mappings,
    delete_valo_data,
    get_user_by_pseudo_tag,
    get_last_notification,
    update_last_notification,
    mark_user_inactive,
    reactivate_user,
    valorant_account_linked,
    # Nouvelles fonctions pipeline
    get_users_for_pipeline,
    update_pipeline_success,
    update_pipeline_error,
    reset_user_for_account_change,
    get_all_valorant_discord_ids,
)
from cogs.ranking.services.valorant_pipeline import (
    ValorantPipeline,
    UserPipelineState,
    PipelineResult,
    LocalRateLimitReached,
)
from integrations.http_client import HTTPClient
from integrations.henrikdev.service import HenrikDevService
from integrations.exceptions import RateLimitError
from cogs.moderation.services.moderation_service import ModerationService
from utils.checks import rules_interaction_check

logger = logging.getLogger(__name__)

EMBED_MESSAGE_TYPE = "embed_rank"

# Mapping rang Valorant -> role_name (roles_configurations.role_name)
VALORANT_RANK_TO_ROLE_KEY = {
    "Iron 1": "fer",
    "Iron 2": "fer",
    "Iron 3": "fer",
    "Bronze 1": "bronze",
    "Bronze 2": "bronze",
    "Bronze 3": "bronze",
    "Silver 1": "argent",
    "Silver 2": "argent",
    "Silver 3": "argent",
    "Gold 1": "or",
    "Gold 2": "or",
    "Gold 3": "or",
    "Platinum 1": "platine",
    "Platinum 2": "platine",
    "Platinum 3": "platine",
    "Diamond 1": "diamant",
    "Diamond 2": "diamant",
    "Diamond 3": "diamant",
    "Ascendant 1": "ascendant",
    "Ascendant 2": "ascendant",
    "Ascendant 3": "ascendant",
    "Immortal 1": "immortel",
    "Immortal 2": "immortel",
    "Immortal 3": "immortel",
    "Radiant": "radiant",
    "Unrated": "no_rank",
}


async def get_rules_channel_id(guild_id: int) -> Optional[int]:
    return await get_channel_id(guild_id, "rules")


class PseudoTagModal(discord.ui.Modal):
    """Modal pour renseigner ou changer son pseudo/tag Valorant."""

    def __init__(self, user: discord.User, cog, is_change: bool = False):
        title = "Changer de compte Valorant" if is_change else "Renseignez votre Pseudo et Tag Valorant"
        super().__init__(title=title)
        self.user = user
        self.cog = cog
        self.is_change = is_change

        self.pseudo = discord.ui.TextInput(
            label="Pseudo",
            placeholder="Entrez votre pseudo Valorant (exemple: Swyzin)",
            max_length=32,
            required=True,
        )
        self.tag = discord.ui.TextInput(
            label="Tag",
            placeholder="Entrez votre tag Valorant sans le # (exemple: meow)",
            max_length=6,
            required=True,
        )
        self.add_item(self.pseudo)
        self.add_item(self.tag)

    async def on_submit(self, interaction: discord.Interaction):
        pseudo = self.pseudo.value.strip()
        tag = self.tag.value.strip()

        if not pseudo:
            await interaction.response.send_message(
                "Le pseudo ne doit pas etre vide.",
                ephemeral=True
            )
            return

        if not tag.isalnum():
            await interaction.response.send_message(
                "Le tag ne doit contenir que des lettres et des chiffres.",
                ephemeral=True
            )
            return

        # Vérifier les doublons
        existing_discord_id = await get_user_by_pseudo_tag(pseudo, tag)
        if existing_discord_id:
            if existing_discord_id == self.user.id:
                await interaction.response.send_message(
                    "Vous avez deja enregistre ce pseudo et tag Valorant.",
                    ephemeral=True
                )
                return
            else:
                existing_user = self.cog.bot.get_user(existing_discord_id)
                if not existing_user:
                    try:
                        existing_user = await self.cog.bot.fetch_user(existing_discord_id)
                    except discord.NotFound:
                        existing_user = None
                await interaction.response.send_message(
                    "Ce pseudo et tag Valorant sont deja utilises par un autre utilisateur.",
                    ephemeral=True
                )
                if existing_user:
                    await self.cog.notify_duplicate_pseudo_tag(
                        existing_user, self.user, pseudo, tag, interaction.guild
                    )
                return

        if not await rules_interaction_check(interaction):
            return

        try:
            if self.is_change:
                # Reset complet des données pour le nouveau compte
                success = await reset_user_for_account_change(
                    interaction.user.id, pseudo, tag
                )
                message = (
                    f"Votre compte Valorant a ete change vers : {pseudo}#{tag}\n"
                    "La mise a jour de votre rang commencera bientot."
                )
            else:
                # Nouvelle liaison de compte
                success = await update_user_valorant_info(interaction.user.id, pseudo, tag)
                message = f"Vos informations Valorant ont ete enregistrees : {pseudo}#{tag}"

            if success:
                await interaction.response.send_message(message, ephemeral=True)
                action = "changed" if self.is_change else "registered"
                logger.info(f"User {interaction.user} {action} Valorant: {pseudo}#{tag}")
            else:
                await interaction.response.send_message(
                    "Une erreur est survenue. Veuillez reessayer plus tard.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement pour {interaction.user}: {e}")
            await interaction.response.send_message(
                "Une erreur est survenue. Veuillez reessayer plus tard.",
                ephemeral=True
            )


class EmbedButtonsView(discord.ui.View):
    """Vue avec les boutons pour l'embed de gestion Valorant."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Renseigner Pseudo/Tag Valorant",
        style=discord.ButtonStyle.primary,
        custom_id="button:pseudo_tag"
    )
    async def pseudo_tag_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PseudoTagModal(interaction.user, self.cog, is_change=False)
        if not interaction.response.is_done():
            await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Changer de compte Valorant",
        style=discord.ButtonStyle.secondary,
        custom_id="button:change_valo_account"
    )
    async def change_account_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        # Vérifier si l'utilisateur a un compte lié
        if not await valorant_account_linked(interaction.user.id):
            await interaction.response.send_message(
                "Vous n'avez pas encore de compte Valorant lie. "
                "Utilisez le bouton bleu pour en lier un.",
                ephemeral=True
            )
            return

        modal = PseudoTagModal(interaction.user, self.cog, is_change=True)
        if not interaction.response.is_done():
            await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Effacer mes donnees Valorant",
        style=discord.ButtonStyle.danger,
        custom_id="button:delete_valo_data"
    )
    async def delete_valo_data_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        try:
            success = await delete_valo_data(interaction.user.id)
            if success:
                await interaction.followup.send(
                    "Vos donnees Valorant ont ete supprimees de la base de donnees.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "Une erreur est survenue lors de la suppression de vos donnees.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Erreur lors de la suppression des donnees Valorant pour {interaction.user}: {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors de la suppression de vos donnees.",
                ephemeral=True
            )


class EmbedCog(commands.Cog):
    """Cog principal pour la gestion des rangs Valorant."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message_id = None

        # Services API
        self._http_client: Optional[HTTPClient] = None
        self._henrik_service: Optional[HenrikDevService] = None
        self._pipeline: Optional[ValorantPipeline] = None

        logger.info("EmbedCog initialise.")
        self.bot.loop.create_task(self._async_init())
        self.refresh_roles_cache_task.start()

    async def _async_init(self):
        """Initialisation asynchrone après que le bot soit prêt."""
        await self.bot.wait_until_ready()

        # Initialiser le client HTTP et les services
        api_key = os.getenv("HENRIK_VALO_KEY")
        if not api_key:
            logger.error("HENRIK_VALO_KEY non defini! Le pipeline ne fonctionnera pas.")
            return

        self._http_client = HTTPClient(timeout_seconds=15.0)
        await self._http_client.__aenter__()

        self._henrik_service = HenrikDevService(self._http_client, api_key)
        self._pipeline = ValorantPipeline(self._henrik_service)

        logger.info("Services API initialises.")

        # Recharger l'embed persistant
        await self.reload_persistent_embed()

        # Sync de présence au démarrage
        await self._startup_presence_sync()

        # Démarrer la boucle de mise à jour
        self.bot.loop.create_task(self.update_roles_loop())

    def cog_unload(self):
        self.refresh_roles_cache_task.cancel()
        if self._http_client:
            self.bot.loop.create_task(self._http_client.__aexit__(None, None, None))

    async def _startup_presence_sync(self):
        """
        Synchronise l'état de présence au démarrage.
        Rattrape les événements join/leave manqués pendant le downtime.
        """
        logger.info("[startup_presence_sync] Debut de la synchronisation de presence...")

        # Récupérer tous les discord_id avec compte Valorant
        valo_discord_ids = set(await get_all_valorant_discord_ids())

        # Récupérer tous les membres actuellement visibles
        present_ids = set()
        for guild in self.bot.guilds:
            for member in guild.members:
                present_ids.add(member.id)

        # Réactiver les utilisateurs présents
        reactivated = 0
        for discord_id in valo_discord_ids & present_ids:
            if await reactivate_user(discord_id):
                reactivated += 1

        # Désactiver les utilisateurs absents
        deactivated = 0
        absent_ids = valo_discord_ids - present_ids
        for discord_id in absent_ids:
            if await mark_user_inactive(discord_id):
                deactivated += 1

        logger.info(
            f"[startup_presence_sync] Termine: {reactivated} reactives, "
            f"{deactivated} desactives"
        )

    async def reload_persistent_embed(self):
        """Recharge les vues des embeds persistants."""
        logger.info("Rechargement de l'embed persistant...")

        for guild in self.bot.guilds:
            message_data = await get_persistent_message(
                guild.id,
                EMBED_MESSAGE_TYPE,
                guild.name
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
        """Réactive le tracking si un utilisateur revient."""
        if await valorant_account_linked(member.id):
            reactivated = await reactivate_user(member.id)
            if reactivated:
                logger.info(f"[on_member_join] Tracking reactive pour {member.id}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Désactive le tracking si l'utilisateur quitte tous les serveurs."""
        # Vérifier si présent dans un autre guild
        for guild in self.bot.guilds:
            if guild.id != member.guild.id and guild.get_member(member.id):
                return  # Encore présent ailleurs

        # Plus dans aucun guild -> marquer inactif
        if await valorant_account_linked(member.id):
            deactivated = await mark_user_inactive(member.id)
            if deactivated:
                logger.info(f"[on_member_remove] {member.id} marque inactif (quitte tous les guilds)")

    @commands.command(name="send_embed_rang")
    @commands.has_permissions(administrator=True)
    async def send_embed(self, ctx: commands.Context):
        """Envoie l'embed de gestion Valorant."""
        guild_id = ctx.guild.id
        action = "rang"
        channel_id = await get_channel_id(guild_id, action)
        if not channel_id:
            await ctx.send(f"Aucun salon defini pour l'action '{action}'.", delete_after=10)
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Le salon d'embed specifie est introuvable.", delete_after=10)
            return

        message_data = await get_persistent_message(guild_id, EMBED_MESSAGE_TYPE)
        if message_data:
            try:
                await channel.fetch_message(message_data["message_id"])
                await ctx.send("L'embed a deja ete envoye dans ce salon.", delete_after=10)
                return
            except discord.NotFound:
                pass  # Message supprimé, on en envoie un nouveau

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
            color=discord.Color.blue()
        )
        embed.set_footer(text="Tenez a jour vos informations pour obtenir le role correspondant a votre rang.")

        view = EmbedButtonsView(self)
        try:
            message = await channel.send(embed=embed, view=view)
            success = await store_persistent_message(
                guild_id, channel.id, message.id, EMBED_MESSAGE_TYPE, ctx.guild.name
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
        guild: discord.Guild
    ):
        """Notifie les modérateurs d'un doublon de pseudo/tag."""
        channel_id = await get_channel_id(guild.id, "duplicate_alert")
        if not channel_id:
            channel_id = await get_channel_id(guild.id, "moderation")
        if not channel_id:
            channel_id = await get_channel_id(guild.id, "rank_up")
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
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="Gestion des Doublons de Pseudo Valorant")

        try:
            await channel.send(embed=embed)
            logger.info(f"Embed doublon envoye pour {current_user} et {existing_user}")
        except Exception as e:
            logger.error(f"Erreur envoi embed doublon: {e}")

    # -------------------------------------------------------------------------
    # Boucle de mise à jour pipeline
    # -------------------------------------------------------------------------

    async def update_roles_loop(self):
        """Boucle principale de mise à jour des rangs via le pipeline."""
        while True:
            if not self._pipeline:
                logger.warning("[update_roles_loop] Pipeline non initialise, attente...")
                await asyncio.sleep(30)
                continue

            try:
                await self._process_pipeline_batch()
            except RateLimitError as e:
                logger.warning(f"[update_roles_loop] RateLimitError: {e}. Pause 60s.")
                await asyncio.sleep(60)
            except LocalRateLimitReached as e:
                logger.info(f"[update_roles_loop] Limite locale atteinte. Pause {e.reset_seconds}s.")
                await asyncio.sleep(e.reset_seconds)
            except Exception as e:
                logger.exception(f"[update_roles_loop] Erreur inattendue: {e}")
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(5)  # Court délai entre les batches

    async def _process_pipeline_batch(self):
        """Traite un batch d'utilisateurs via le pipeline."""
        users = await get_users_for_pipeline(limit=20)

        if not users:
            logger.debug("[_process_pipeline_batch] Aucun utilisateur a traiter.")
            return

        logger.info(f"[_process_pipeline_batch] Traitement de {len(users)} utilisateurs.")

        # Pré-charger les caches
        guild_list = list(self.bot.guilds)
        ban_role_cache = await self._load_ban_role_cache(guild_list)

        # Stats du batch
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
                last_error_at=record.get("last_error_at")
            )

            # Vérifier backoff
            if self._pipeline.should_skip_due_to_errors(state):
                stats["skipped"] += 1
                continue

            # Vérifier limite locale
            if not self._pipeline._check_local_rate_limit():
                reset = self._pipeline.get_local_rate_limit_reset()
                raise LocalRateLimitReached(reset)

            # Trouver le membre
            member = self._find_member_in_cache(state.discord_id, guild_list)
            if not member:
                await mark_user_inactive(state.discord_id)
                await update_pipeline_error(state.discord_id)
                stats["errors"] += 1
                continue

            # Vérifier si banni
            if self._is_member_banned(member, ban_role_cache):
                await update_pipeline_success(state.discord_id)
                stats["skipped"] += 1
                continue

            stats["processed"] += 1

            # Exécuter l'étape pipeline
            try:
                result, rate_limit = await self._pipeline.execute_step(state)
            except RateLimitError:
                raise  # Remonter pour pause globale
            except Exception as e:
                logger.error(f"[_process_pipeline_batch] Erreur execute_step pour {state.discord_id}: {e}")
                await update_pipeline_error(state.discord_id)
                stats["errors"] += 1
                continue

            if result.success:
                await update_pipeline_success(
                    state.discord_id,
                    puuid=result.puuid,
                    region=result.region,
                    platform=result.platform,
                    rank=result.rank,
                    elo=result.elo
                )

                # Si on a le rang, mettre à jour les rôles Discord
                if result.rank:
                    await self._update_member_role(member, result.rank, state.rank)
                    stats["updated"] += 1
            else:
                await update_pipeline_error(state.discord_id)
                stats["errors"] += 1

                # Notifier l'utilisateur si nécessaire
                if result.should_notify_user:
                    await self._notify_user_error(member, state, result)

            # Ajuster le rythme selon le rate limit API
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
        """Charge le cache des rôles de ban pour chaque guild."""
        cache = {}
        for guild in guild_list:
            try:
                cache[guild.id] = await ModerationService.get_ban_role_id(guild.id)
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
        """Vérifie si le membre a un rôle de ban."""
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
        _old_rank: Optional[str] = None
    ):
        """Met à jour le rôle de rang du membre."""
        role_key = VALORANT_RANK_TO_ROLE_KEY.get(new_rank)
        if not role_key:
            logger.warning(f"[_update_member_role] Aucun mapping pour rang '{new_rank}'")
            return

        role_mappings = await get_role_mappings(member.guild.id, member.guild.name)
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

        # Supprimer les anciens rôles de rang
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

        # Ajouter le nouveau rôle si nécessaire
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
        result: PipelineResult
    ):
        """Notifie l'utilisateur d'une erreur persistante."""
        # Vérifier cooldown de notification (7 jours)
        last_notif = await get_last_notification(state.discord_id)
        now = datetime.now(timezone.utc)

        if last_notif and (now - last_notif) < timedelta(days=7):
            return  # Déjà notifié récemment

        try:
            # Récupérer le channel de rang pour la mention
            rank_channel_id = await get_channel_id(member.guild.id, "rang")
            channel_mention = f"<#{rank_channel_id}>" if rank_channel_id else "le salon de rang"

            await member.send(
                f"La recuperation de vos informations Valorant a echoue pour "
                f"**{state.pseudo}#{state.tag}**.\n"
                f"Erreur: {result.error_message or 'Inconnue'}\n\n"
                f"Veuillez verifier vos identifiants ou modifier vos informations "
                f"dans {channel_mention}."
            )
            await update_last_notification(state.discord_id, now)
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
        """Rafraîchit le cache des rôles toutes les heures."""
        logger.info("Debut du rafraichissement du cache des roles.")
        for guild in self.bot.guilds:
            await refresh_role_mappings(guild.id, guild.name)
        logger.info("Rafraichissement du cache des roles termine.")

    @refresh_roles_cache_task.before_loop
    async def before_refresh_roles_cache_task(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedCog(bot))
    logger.info("Cog EmbedCog charge.")
