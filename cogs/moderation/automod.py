# cogs/moderation/automod.py

import asyncio
import re
import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple, Optional, Any

from cogs.moderation.discord_actions import (
    apply_ban_role_all_guilds,
    collect_restorable_role_ids,
)
from cogs.moderation.services.automod_detection_service import AutomodDetectionService
from cogs.moderation.services.automod_spam_tracker import AutomodSpamTracker
from cogs.moderation.services.moderation_service import ModerationService
from cogs.moderation.services.automod_service import AutomodService
from cogs.moderation.presenters import (
    build_automod_status_embed,
    build_generic_automod_log_embed,
    build_scam_ban_dm_embed,
    build_scam_log_embed,
    build_spam_alert_embed,
    format_custom_items_message,
)
from cogs.moderation.views.spam_confirmation_view import SpamConfirmationView

logger = logging.getLogger(__name__)


class AutoMod(commands.Cog):
    """Cog pour l'auto-modération: détection de scam et spam."""

    def __init__(
        self,
        bot: commands.Bot,
        moderation_service: ModerationService,
        automod_service: AutomodService,
    ):
        self.bot = bot
        self._mod_svc = moderation_service
        self._automod_svc = automod_service
        self._spam_tracker = AutomodSpamTracker()
        # Set pour éviter les alertes en double
        self.pending_spam_alerts: Set[Tuple[int, int]] = set()
        self._pending_cleanup_tasks: Set[asyncio.Task] = set()
        # Utilisateurs déjà en traitement scam, évite les doubles actions concurrentes.
        self.banning_users: Set[int] = set()
        self._detection_svc = AutomodDetectionService()
        # Cache des configurations par serveur
        self.config_cache: Dict[int, Dict[str, Any]] = {}
        logger.info("AutoMod initialisé.")

    def cog_unload(self) -> None:
        for task in self._pending_cleanup_tasks:
            task.cancel()
        self._pending_cleanup_tasks.clear()

    async def get_guild_config(self, guild_id: int, guild_name: str) -> Dict[str, Any]:
        """Récupère la configuration du serveur (avec cache)."""
        if guild_id in self.config_cache:
            return self.config_cache[guild_id]

        config = await self._automod_svc.get_or_create_config(guild_id, guild_name)
        self.config_cache[guild_id] = config
        return config

    def invalidate_cache(self, guild_id: int) -> None:
        """Invalide le cache de configuration pour un serveur."""
        if guild_id in self.config_cache:
            del self.config_cache[guild_id]

    # ========== Commande /automod ==========

    @app_commands.command(name="automod", description="Configurer l'auto-modération du serveur")
    @app_commands.describe(
        action="Action à effectuer",
        role="Rôle à ajouter/retirer de la whitelist",
        channel="Salon à ajouter/retirer de la whitelist",
        pattern="Pattern regex personnalisé (ex: free\\s*vbucks)",
        domain="Domaine de scam personnalisé (ex: fake-discord.com)",
        spam_threshold="Seuil de salons pour le spam (2-10)",
        spam_time_window="Fenêtre de temps en secondes (10-300)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Voir le statut", value="status"),
        app_commands.Choice(name="Activer détection scam", value="enable_scam"),
        app_commands.Choice(name="Désactiver détection scam", value="disable_scam"),
        app_commands.Choice(name="Activer détection spam", value="enable_spam"),
        app_commands.Choice(name="Désactiver détection spam", value="disable_spam"),
        app_commands.Choice(name="Configurer spam", value="spam_config"),
        app_commands.Choice(name="Ajouter rôle whitelist", value="add_role"),
        app_commands.Choice(name="Retirer rôle whitelist", value="remove_role"),
        app_commands.Choice(name="Ajouter salon whitelist", value="add_channel"),
        app_commands.Choice(name="Retirer salon whitelist", value="remove_channel"),
        app_commands.Choice(name="Ajouter pattern scam", value="add_pattern"),
        app_commands.Choice(name="Retirer pattern scam", value="remove_pattern"),
        app_commands.Choice(name="Lister patterns", value="list_patterns"),
        app_commands.Choice(name="Ajouter domaine scam", value="add_domain"),
        app_commands.Choice(name="Retirer domaine scam", value="remove_domain"),
        app_commands.Choice(name="Lister domaines", value="list_domains"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def automod_command(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        role: Optional[discord.Role] = None,
        channel: Optional[discord.TextChannel] = None,
        pattern: Optional[str] = None,
        domain: Optional[str] = None,
        spam_threshold: Optional[int] = None,
        spam_time_window: Optional[int] = None
    ):
        """Commande principale pour configurer l'auto-modération."""
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild.id
        guild_name = interaction.guild.name

        # ===== STATUS =====
        if action.value == "status":
            await self._show_status(interaction)
            return

        # ===== TOGGLE SCAM =====
        if action.value == "enable_scam":
            success = await self._automod_svc.set_scam_detection(guild_id, guild_name, True)
            self.invalidate_cache(guild_id)
            if success:
                await interaction.followup.send("✅ Détection de scam **activée**.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
            return

        if action.value == "disable_scam":
            success = await self._automod_svc.set_scam_detection(guild_id, guild_name, False)
            self.invalidate_cache(guild_id)
            if success:
                await interaction.followup.send("✅ Détection de scam **désactivée**.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
            return

        # ===== TOGGLE SPAM =====
        if action.value == "enable_spam":
            success = await self._automod_svc.set_spam_detection(guild_id, guild_name, True)
            self.invalidate_cache(guild_id)
            if success:
                await interaction.followup.send("✅ Détection de spam multi-salons **activée**.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
            return

        if action.value == "disable_spam":
            success = await self._automod_svc.set_spam_detection(guild_id, guild_name, False)
            self.invalidate_cache(guild_id)
            if success:
                await interaction.followup.send("✅ Détection de spam multi-salons **désactivée**.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
            return

        # ===== SPAM CONFIG =====
        if action.value == "spam_config":
            if spam_threshold is None and spam_time_window is None:
                await interaction.followup.send(
                    "❌ Veuillez spécifier `spam_threshold` et/ou `spam_time_window`.",
                    ephemeral=True
                )
                return

            messages = []

            if spam_threshold is not None:
                if spam_threshold < 2 or spam_threshold > 10:
                    await interaction.followup.send("❌ Le seuil doit être entre 2 et 10.", ephemeral=True)
                    return
                success = await self._automod_svc.set_spam_threshold(guild_id, guild_name, spam_threshold)
                if success:
                    messages.append(f"Seuil: **{spam_threshold}** salons")

            if spam_time_window is not None:
                if spam_time_window < 10 or spam_time_window > 300:
                    await interaction.followup.send("❌ La fenêtre doit être entre 10 et 300 secondes.", ephemeral=True)
                    return
                success = await self._automod_svc.set_spam_time_window(guild_id, guild_name, spam_time_window)
                if success:
                    messages.append(f"Fenêtre: **{spam_time_window}** secondes")

            self.invalidate_cache(guild_id)

            if messages:
                await interaction.followup.send(f"✅ Configuration spam mise à jour:\n" + "\n".join(messages), ephemeral=True)
            else:
                await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
            return

        # ===== WHITELIST ROLE =====
        if action.value == "add_role":
            if not role:
                await interaction.followup.send("❌ Veuillez spécifier un rôle.", ephemeral=True)
                return
            success = await self._automod_svc.add_whitelisted_role(guild_id, guild_name, role.id)
            self.invalidate_cache(guild_id)
            if success:
                await interaction.followup.send(f"✅ Rôle {role.mention} ajouté à la whitelist.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
            return

        if action.value == "remove_role":
            if not role:
                await interaction.followup.send("❌ Veuillez spécifier un rôle.", ephemeral=True)
                return
            success = await self._automod_svc.remove_whitelisted_role(guild_id, guild_name, role.id)
            self.invalidate_cache(guild_id)
            if success:
                await interaction.followup.send(f"✅ Rôle {role.mention} retiré de la whitelist.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
            return

        # ===== WHITELIST CHANNEL =====
        if action.value == "add_channel":
            if not channel:
                await interaction.followup.send("❌ Veuillez spécifier un salon.", ephemeral=True)
                return
            success = await self._automod_svc.add_whitelisted_channel(guild_id, guild_name, channel.id)
            self.invalidate_cache(guild_id)
            if success:
                await interaction.followup.send(f"✅ Salon {channel.mention} ajouté à la whitelist.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
            return

        if action.value == "remove_channel":
            if not channel:
                await interaction.followup.send("❌ Veuillez spécifier un salon.", ephemeral=True)
                return
            success = await self._automod_svc.remove_whitelisted_channel(guild_id, guild_name, channel.id)
            self.invalidate_cache(guild_id)
            if success:
                await interaction.followup.send(f"✅ Salon {channel.mention} retiré de la whitelist.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
            return

        # ===== PATTERNS =====
        if action.value == "list_patterns":
            config = await self.get_guild_config(guild_id, guild_name)
            patterns = config.get('custom_scam_patterns', []) or []
            await interaction.followup.send(
                format_custom_items_message(
                    label="Patterns personnalisés",
                    items=patterns,
                    empty_message="Aucun pattern personnalisé configuré.",
                ),
                ephemeral=True,
            )
            return

        if action.value == "add_pattern":
            if not pattern:
                await interaction.followup.send("❌ Veuillez spécifier un pattern.", ephemeral=True)
                return
            try:
                re.compile(pattern)
            except re.error as e:
                await interaction.followup.send(f"❌ Pattern regex invalide: {e}", ephemeral=True)
                return
            success = await self._automod_svc.add_custom_pattern(guild_id, guild_name, pattern)
            self.invalidate_cache(guild_id)
            if success:
                await interaction.followup.send(f"✅ Pattern `{pattern}` ajouté.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
            return

        if action.value == "remove_pattern":
            if not pattern:
                await interaction.followup.send("❌ Veuillez spécifier un pattern.", ephemeral=True)
                return
            success = await self._automod_svc.remove_custom_pattern(guild_id, guild_name, pattern)
            self.invalidate_cache(guild_id)
            if success:
                await interaction.followup.send(f"✅ Pattern `{pattern}` retiré.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
            return

        # ===== DOMAINS =====
        if action.value == "list_domains":
            config = await self.get_guild_config(guild_id, guild_name)
            domains = config.get('custom_scam_domains', []) or []
            await interaction.followup.send(
                format_custom_items_message(
                    label="Domaines personnalisés",
                    items=domains,
                    empty_message="Aucun domaine personnalisé configuré.",
                ),
                ephemeral=True,
            )
            return

        if action.value == "add_domain":
            if not domain:
                await interaction.followup.send("❌ Veuillez spécifier un domaine.", ephemeral=True)
                return
            success = await self._automod_svc.add_custom_domain(guild_id, guild_name, domain)
            self.invalidate_cache(guild_id)
            if success:
                await interaction.followup.send(f"✅ Domaine `{domain}` ajouté.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
            return

        if action.value == "remove_domain":
            if not domain:
                await interaction.followup.send("❌ Veuillez spécifier un domaine.", ephemeral=True)
                return
            success = await self._automod_svc.remove_custom_domain(guild_id, guild_name, domain)
            self.invalidate_cache(guild_id)
            if success:
                await interaction.followup.send(f"✅ Domaine `{domain}` retiré.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)
            return

    async def _show_status(self, interaction: discord.Interaction) -> None:
        """Affiche la configuration actuelle de l'automod."""
        config = await self.get_guild_config(interaction.guild.id, interaction.guild.name)
        embed = build_automod_status_embed(config=config, timestamp=datetime.utcnow())
        await interaction.followup.send(embed=embed, ephemeral=True)

    def add_to_spam_whitelist(self, user_id: int, guild_id: int) -> None:
        """Ajoute un utilisateur à la whitelist temporaire (24h)."""
        expiration = self._spam_tracker.add_to_whitelist(user_id, guild_id)
        logger.debug(f"Utilisateur {user_id} ajouté à la whitelist spam jusqu'à {expiration}")

    def is_spam_whitelisted(self, user_id: int, guild_id: int) -> bool:
        """Vérifie si un utilisateur est dans la whitelist spam."""
        return self._spam_tracker.is_whitelisted(user_id, guild_id)

    async def is_member_whitelisted(self, member: discord.Member, config: Dict[str, Any]) -> bool:
        """Vérifie si un membre est exempté de l'automod (admin, modo, rôle whitelisté)."""
        return self._detection_svc.is_member_whitelisted(member, config)

    def is_channel_whitelisted(self, channel_id: int, config: Dict[str, Any]) -> bool:
        """Vérifie si un salon est exempté de l'automod."""
        return self._detection_svc.is_channel_whitelisted(channel_id, config)

    def extract_urls(self, content: str) -> List[str]:
        """Extrait les URLs d'un message."""
        return self._detection_svc.extract_urls(content)

    def is_scam_domain(self, url: str, config: Dict[str, Any]) -> bool:
        """Vérifie si une URL appartient à un domaine de scam."""
        return self._detection_svc.is_scam_domain(url, config)

    def is_scam_content(self, content: str, config: Dict[str, Any]) -> bool:
        """Vérifie si le contenu du message correspond à un pattern de scam."""
        return self._detection_svc.is_scam_content(content, config)

    async def is_scam_message(self, message: discord.Message, config: Dict[str, Any]) -> bool:
        """Vérifie si un message est un scam."""
        return self._detection_svc.is_scam_message_content(message.content, config)

    async def handle_scam(self, message: discord.Message) -> None:
        """Gère un message scam détecté: supprime, ban, et log."""
        member = message.author
        guild = message.guild

        if member.id in self.banning_users:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass
            return

        self.banning_users.add(member.id)
        try:
            logger.warning(f"Scam détecté de {member.display_name} dans {guild.name}: {message.content[:100]}")

            roles_to_backup = collect_restorable_role_ids(member)

            try:
                await member.timeout(timedelta(seconds=60), reason="Scam détecté - traitement en cours")
                logger.debug(f"Timeout temporaire appliqué à {member.display_name}")
            except (discord.Forbidden, discord.HTTPException) as e:
                logger.debug(f"Impossible d'appliquer le timeout temporaire: {e}")

            try:
                await message.delete()
                logger.info(f"Message scam supprimé de {member.display_name}")
            except discord.Forbidden:
                logger.error(f"Pas de permission pour supprimer le message scam de {member.display_name}")
            except discord.NotFound:
                pass

            if roles_to_backup:
                await self._mod_svc.update_roles_backup(
                    guild_id=guild.id,
                    guild_name=guild.name,
                    discord_user_id=member.id,
                    roles=roles_to_backup,
                )

            await self._mod_svc.add_ban(
                guild_id=guild.id,
                guild_name=guild.name,
                user_id=member.id,
                ban_type="perm",
                reason="Scam détecté (auto-modération)",
                banned_by=self.bot.user.id,
                ban_end=None,
            )

            await apply_ban_role_all_guilds(
                self.bot,
                self._mod_svc,
                member.id,
                "Scam détecté (auto-modération)",
                source_member=member,
            )

            logger.info(f"Utilisateur {member.display_name} banni pour scam")

            try:
                embed = build_scam_ban_dm_embed(
                    guild_name=guild.name,
                    timestamp=datetime.utcnow(),
                )
                await member.send(embed=embed)
            except discord.Forbidden:
                pass

            await self._log_automod_action(
                guild=guild,
                action_type="scam",
                user=member,
                content=message.content,
                channel=message.channel
            )

        except Exception as e:
            logger.exception(f"Erreur lors du ban pour scam: {e}")
        finally:
            self._schedule_banning_user_cleanup(member.id)

    async def _log_automod_action(
        self,
        guild: discord.Guild,
        action_type: str,
        user: discord.Member,
        content: str,
        channel: discord.TextChannel,
        extra_info: Optional[str] = None
    ) -> None:
        """Envoie un log dans le salon de modération."""
        try:
            mod_channel_id = await self._mod_svc.get_moderation_channel_id(guild.id)
            if not mod_channel_id:
                logger.warning(f"Salon de modération non configuré pour {guild.name}")
                return

            mod_channel = guild.get_channel(mod_channel_id)
            if not mod_channel:
                logger.warning(f"Salon de modération {mod_channel_id} introuvable dans {guild.name}")
                return

            if action_type == "scam":
                embed = build_scam_log_embed(
                    user_mention=user.mention,
                    user_id=user.id,
                    user_avatar_url=user.display_avatar.url,
                    channel_mention=channel.mention,
                    content=content,
                    timestamp=datetime.utcnow(),
                )
            else:
                embed = build_generic_automod_log_embed(
                    user_mention=user.mention,
                    description=extra_info,
                    timestamp=datetime.utcnow(),
                )

            await mod_channel.send(embed=embed)

        except Exception as e:
            logger.exception(f"Erreur lors du log automod: {e}")

    def _schedule_pending_alert_cleanup(
        self,
        alert_key: Tuple[int, int],
        *,
        delay_seconds: int = 30,
    ) -> None:
        task = asyncio.create_task(self._clear_pending_alert(alert_key, delay_seconds))
        self._pending_cleanup_tasks.add(task)
        task.add_done_callback(self._pending_cleanup_tasks.discard)

    async def _clear_pending_alert(self, alert_key: Tuple[int, int], delay_seconds: int) -> None:
        await asyncio.sleep(delay_seconds)
        self.pending_spam_alerts.discard(alert_key)

    def _schedule_banning_user_cleanup(self, user_id: int, *, delay_seconds: int = 5) -> None:
        task = asyncio.create_task(self._clear_banning_user(user_id, delay_seconds))
        self._pending_cleanup_tasks.add(task)
        task.add_done_callback(self._pending_cleanup_tasks.discard)

    async def _clear_banning_user(self, user_id: int, delay_seconds: int) -> None:
        await asyncio.sleep(delay_seconds)
        self.banning_users.discard(user_id)

    async def check_cross_channel_spam(self, message: discord.Message, config: Dict[str, Any]) -> bool:
        """
        Vérifie si un utilisateur envoie le même message dans plusieurs salons.
        Retourne True si spam détecté selon la configuration.
        """
        user_id = message.author.id
        guild_id = message.guild.id
        channel_id = message.channel.id
        message_id = message.id

        # Récupérer les paramètres de la config
        threshold = config.get('spam_channel_threshold', 3)
        time_window = config.get('spam_time_window', 60)

        return self._spam_tracker.record_and_detect(
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=message_id,
            content=message.content,
            threshold=threshold,
            time_window_seconds=time_window,
        )

    async def request_spam_confirmation(self, message: discord.Message) -> None:
        """Envoie une demande de confirmation aux modérateurs pour un spam détecté."""
        user = message.author
        guild = message.guild

        # Éviter les alertes en double par utilisateur et serveur
        alert_key = (user.id, guild.id)
        if alert_key in self.pending_spam_alerts:
            return
        self.pending_spam_alerts.add(alert_key)
        keep_pending = False

        try:
            message_refs = self._spam_tracker.get_matching_message_refs(
                user_id=user.id,
                guild_id=guild.id,
                content=message.content,
            )

            # Récupérer le salon de modération
            mod_channel_id = await self._mod_svc.get_moderation_channel_id(guild.id)
            if not mod_channel_id:
                logger.warning(f"Salon de modération non configuré pour {guild.name}")
                return

            mod_channel = guild.get_channel(mod_channel_id)
            if not mod_channel:
                logger.warning(f"Salon de modération introuvable pour {guild.name}")
                return

            # Construire la liste des salons
            channel_mentions = []
            for ch_id, msg_id in message_refs:
                channel = guild.get_channel(ch_id)
                if channel:
                    # Lien vers le message
                    channel_mentions.append(
                        f"• {channel.mention} ([message](https://discord.com/channels/{guild.id}/{ch_id}/{msg_id}))"
                    )

            embed = build_spam_alert_embed(
                user_mention=user.mention,
                user_id=user.id,
                user_avatar_url=user.display_avatar.url,
                content=message.content,
                channel_mentions=channel_mentions,
                timestamp=datetime.utcnow(),
            )

            # Créer la vue avec les boutons
            view = SpamConfirmationView(
                bot=self.bot,
                user=user,
                message_refs=message_refs,
                content=message.content,
                guild=guild,
                moderation_service=self._mod_svc,
            )

            await mod_channel.send(embed=embed, view=view)
            keep_pending = True
            logger.info(f"Alerte spam envoyée pour {user.display_name} dans {guild.name}")

        except Exception as e:
            logger.exception(f"Erreur lors de l'envoi de l'alerte spam: {e}")
        finally:
            if keep_pending:
                self._schedule_pending_alert_cleanup(alert_key)
            else:
                self.pending_spam_alerts.discard(alert_key)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Écoute tous les messages pour la détection de scam et spam."""
        # Ignorer les DMs
        if not message.guild:
            return

        # Ignorer les bots
        if message.author.bot:
            return

        # Éviter les doubles traitements pendant l'application du rôle ban.
        if message.author.id in self.banning_users:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass
            return

        # Récupérer la configuration du serveur
        config = await self.get_guild_config(message.guild.id, message.guild.name)

        # Ignorer les membres whitelistés (admins, modos, rôles config)
        if await self.is_member_whitelisted(message.author, config):
            return

        # Ignorer les salons whitelistés
        if self.is_channel_whitelisted(message.channel.id, config):
            return

        # 1. Vérifier scam → ban immédiat (si activé)
        if config.get('scam_detection_enabled', True):
            if await self.is_scam_message(message, config):
                await self.handle_scam(message)
                return

        # 2. Vérifier spam multi-salons → demande confirmation (si activé)
        if config.get('spam_detection_enabled', True):
            # Sauf si l'utilisateur est dans la whitelist temporaire
            if not self.is_spam_whitelisted(message.author.id, message.guild.id):
                if await self.check_cross_channel_spam(message, config):
                    await self.request_spam_confirmation(message)


async def setup(bot: commands.Bot):
    moderation_service = getattr(bot, "moderation_service", None)
    if moderation_service is None:
        logger.error("moderation_service non initialisé. AutoMod ne sera pas chargé.")
        return

    automod_service = getattr(bot, "automod_service", None)
    if automod_service is None:
        logger.error("automod_service non initialisé. AutoMod ne sera pas chargé.")
        return

    await bot.add_cog(AutoMod(bot, moderation_service, automod_service))
    logger.info("AutoMod Cog chargé avec succès.")
