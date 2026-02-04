# cogs/moderation/automod.py

import re
import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple, Optional, Any
from urllib.parse import urlparse

from cogs.moderation.services.moderation_service import ModerationService
from cogs.moderation.services.automod_service import AutomodService
from database.services.guild_channels_service import ChannelConfigurationService

logger = logging.getLogger(__name__)


# Patterns de scam connus
SCAM_PATTERNS = [
    r"free\s*nitro",
    r"discord\s*nitro\s*(for\s*)?free",
    r"steam\s*gift",
    r"@everyone.*free",
    r"claim\s*your\s*(free\s*)?gift",
    r"airdrop",
    r"free\s*discord\s*nitro",
    r"nitro\s*gratuit",
    r"get\s*free\s*nitro",
    r"discord\.gift",
    r"steamcommunity\.com.*gift",
]

# Domaines de scam connus
SCAM_DOMAINS = [
    "discordgift.site",
    "discord-nitro.gift",
    "discordnitro.gift",
    "steamcommunity.ru",
    "steampowered.ru",
    "dicsord.gift",  # typosquatting
    "discorrd.gift",
    "dlscord.gift",
    "disc0rd.gift",
    "discordapp.gift",
    "discord-app.gift",
    "discordgiveaway.com",
    "free-nitro.com",
    "nitro-discord.com",
    "steamgifts.ru",
]


class SpamConfirmationView(discord.ui.View):
    """Vue avec boutons pour confirmer ou ignorer un spam détecté."""

    def __init__(
        self,
        bot: commands.Bot,
        user: discord.Member,
        message_refs: List[Tuple[int, int]],  # [(channel_id, message_id), ...]
        content: str,
        guild: discord.Guild,
        moderation_service: ModerationService,
        timeout: float = 3600  # 1 heure
    ):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.user = user
        self.message_refs = message_refs
        self.content = content
        self.guild = guild
        self._mod_svc = moderation_service
        self.resolved = False

    @discord.ui.button(label="Bannir", style=discord.ButtonStyle.danger, emoji="🔨")
    async def ban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bannit l'utilisateur et supprime ses messages."""
        if self.resolved:
            await interaction.response.send_message("Cette action a déjà été traitée.", ephemeral=True)
            return

        self.resolved = True
        await interaction.response.defer()

        # Supprimer les messages
        deleted_count = 0
        for channel_id, msg_id in self.message_refs:
            try:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    msg = await channel.fetch_message(msg_id)
                    await msg.delete()
                    deleted_count += 1
            except discord.NotFound:
                pass  # Message déjà supprimé
            except discord.Forbidden:
                logger.warning(f"Pas de permission pour supprimer le message {msg_id} dans {channel_id}")
            except Exception as e:
                logger.error(f"Erreur lors de la suppression du message {msg_id}: {e}")

        # Bannir l'utilisateur via ModerationService
        try:
            # Sauvegarder les rôles
            roles_to_backup = [
                role.id for role in self.user.roles
                if role != self.guild.default_role and role.name.lower() != "ban"
            ]

            # Sauvegarder les rôles avant le ban
            if roles_to_backup:
                await self._mod_svc.update_roles_backup(
                    guild_id=self.guild.id,
                    guild_name=self.guild.name,
                    discord_user_id=self.user.id,
                    roles=roles_to_backup,
                )

            await self._mod_svc.add_ban(
                guild_id=self.guild.id,
                guild_name=self.guild.name,
                user_id=self.user.id,
                ban_type="perm",
                reason="Spam multi-salons détecté (confirmé par modérateur)",
                banned_by=interaction.user.id,
                ban_end=None,
            )

            # Appliquer le ban sur tous les serveurs
            await self._apply_ban_all_guilds(self.user.id, "Spam multi-salons détecté")

            # Envoyer un DM à l'utilisateur
            try:
                embed = discord.Embed(
                    title="📛 Vous avez été banni(e)",
                    description="Vous avez été banni(e) pour spam multi-salons.",
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(name="Serveur", value=self.guild.name, inline=False)
                embed.add_field(name="Raison", value="Spam multi-salons détecté", inline=False)
                await self.user.send(embed=embed)
            except discord.Forbidden:
                pass

            # Mettre à jour l'embed
            embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if embed:
                embed.color = discord.Color.red()
                embed.add_field(
                    name="✅ Action effectuée",
                    value=f"Banni par {interaction.user.mention}\n{deleted_count} message(s) supprimé(s)",
                    inline=False
                )

            # Désactiver les boutons
            for item in self.children:
                item.disabled = True

            await interaction.message.edit(embed=embed, view=self)
            logger.info(f"Spam confirmé: {self.user.display_name} banni par {interaction.user.display_name}")

        except Exception as e:
            logger.exception(f"Erreur lors du ban pour spam: {e}")
            await interaction.followup.send(f"Erreur lors du bannissement: {e}", ephemeral=True)

    @discord.ui.button(label="Ignorer", style=discord.ButtonStyle.secondary, emoji="❌")
    async def ignore_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ignore l'alerte et ajoute l'utilisateur à une whitelist temporaire."""
        if self.resolved:
            await interaction.response.send_message("Cette action a déjà été traitée.", ephemeral=True)
            return

        self.resolved = True
        await interaction.response.defer()

        # Ajouter à la whitelist temporaire (géré par le cog AutoMod)
        automod_cog = self.bot.get_cog("AutoMod")
        if automod_cog:
            automod_cog.add_to_spam_whitelist(self.user.id, self.guild.id)

        # Mettre à jour l'embed
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.color = discord.Color.light_grey()
            embed.add_field(
                name="❌ Ignoré",
                value=f"Ignoré par {interaction.user.mention}\nUtilisateur en whitelist pour 24h",
                inline=False
            )

        # Désactiver les boutons
        for item in self.children:
            item.disabled = True

        await interaction.message.edit(embed=embed, view=self)
        logger.info(f"Spam ignoré pour {self.user.display_name} par {interaction.user.display_name}")

    async def _apply_ban_all_guilds(self, user_id: int, reason: str) -> None:
        """Applique le rôle ban sur tous les serveurs."""
        for guild in self.bot.guilds:
            member = guild.get_member(user_id)
            if not member:
                continue

            ban_role_id = await self._mod_svc.get_ban_role_id(guild.id)
            if not ban_role_id:
                continue

            ban_role = guild.get_role(ban_role_id)
            if not ban_role or ban_role in member.roles:
                continue

            try:
                roles_to_remove = [role for role in member.roles if role != guild.default_role]
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason=reason)
                await member.add_roles(ban_role, reason=reason)
                logger.info(f"Rôle ban appliqué à {member.display_name} dans {guild.name}")
            except (discord.Forbidden, discord.HTTPException) as e:
                logger.error(f"Erreur ban {member.display_name} dans {guild.name}: {e}")

    async def on_timeout(self):
        """Appelé quand la vue expire."""
        if not self.resolved:
            # Mettre à jour l'embed pour indiquer l'expiration
            try:
                # On ne peut pas accéder au message directement ici
                logger.info(f"Vue de confirmation spam expirée pour {self.user.display_name}")
            except Exception:
                pass


class AutoMod(commands.Cog):
    """Cog pour l'auto-modération: détection de scam et spam."""

    def __init__(
        self,
        bot: commands.Bot,
        moderation_service: ModerationService,
        channel_service: ChannelConfigurationService,
        automod_service: AutomodService,
    ):
        self.bot = bot
        self._mod_svc = moderation_service
        self._channel_svc = channel_service
        self._automod_svc = automod_service
        # Cache pour tracker les messages récents par utilisateur
        # Structure: {user_id: [(guild_id, channel_id, message_id, content_hash, timestamp), ...]}
        self.message_cache: Dict[int, List[Tuple[int, int, int, int, datetime]]] = {}
        # Whitelist temporaire pour le spam (utilisateurs ignorés)
        # Structure: {(user_id, guild_id): expiration_datetime}
        self.spam_whitelist: Dict[Tuple[int, int], datetime] = {}
        # Set pour éviter les alertes en double
        self.pending_spam_alerts: Set[int] = set()
        # Compiler les patterns regex de base
        self.scam_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in SCAM_PATTERNS]
        # Cache des configurations par serveur
        self.config_cache: Dict[int, Dict[str, Any]] = {}
        logger.info("AutoMod initialisé.")

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
            if patterns:
                patterns_text = "\n".join([f"• `{p}`" for p in patterns])
                await interaction.followup.send(f"📋 **Patterns personnalisés ({len(patterns)}):**\n{patterns_text}", ephemeral=True)
            else:
                await interaction.followup.send("Aucun pattern personnalisé configuré.", ephemeral=True)
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
            if domains:
                domains_text = "\n".join([f"• `{d}`" for d in domains])
                await interaction.followup.send(f"📋 **Domaines personnalisés ({len(domains)}):**\n{domains_text}", ephemeral=True)
            else:
                await interaction.followup.send("Aucun domaine personnalisé configuré.", ephemeral=True)
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

        embed = discord.Embed(
            title="⚙️ Configuration AutoMod",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        # Statut des détections
        scam_status = "✅ Activé" if config.get('scam_detection_enabled', True) else "❌ Désactivé"
        spam_status = "✅ Activé" if config.get('spam_detection_enabled', True) else "❌ Désactivé"

        embed.add_field(
            name="📊 Détections",
            value=f"**Scam:** {scam_status}\n**Spam multi-salons:** {spam_status}",
            inline=False
        )

        # Paramètres spam
        threshold = config.get('spam_channel_threshold', 3)
        time_window = config.get('spam_time_window', 60)
        embed.add_field(
            name="⚡ Paramètres Spam",
            value=f"Seuil: **{threshold}** salons\nFenêtre: **{time_window}** secondes",
            inline=True
        )

        # Whitelist rôles
        whitelisted_roles = config.get('whitelisted_roles', []) or []
        if whitelisted_roles:
            roles_text = "\n".join([f"<@&{r}>" for r in whitelisted_roles[:5]])
            if len(whitelisted_roles) > 5:
                roles_text += f"\n... +{len(whitelisted_roles) - 5} autres"
        else:
            roles_text = "Aucun"
        embed.add_field(name="👥 Rôles exemptés", value=roles_text, inline=True)

        # Whitelist salons
        whitelisted_channels = config.get('whitelisted_channels', []) or []
        if whitelisted_channels:
            channels_text = "\n".join([f"<#{c}>" for c in whitelisted_channels[:5]])
            if len(whitelisted_channels) > 5:
                channels_text += f"\n... +{len(whitelisted_channels) - 5} autres"
        else:
            channels_text = "Aucun"
        embed.add_field(name="📝 Salons exemptés", value=channels_text, inline=True)

        # Patterns personnalisés
        custom_patterns = config.get('custom_scam_patterns', []) or []
        custom_domains = config.get('custom_scam_domains', []) or []
        embed.add_field(
            name="🔧 Personnalisations",
            value=f"**Patterns:** {len(custom_patterns)}\n**Domaines:** {len(custom_domains)}",
            inline=True
        )

        embed.set_footer(text="Utilisez /automod action:... pour modifier la configuration")
        await interaction.followup.send(embed=embed, ephemeral=True)

    def add_to_spam_whitelist(self, user_id: int, guild_id: int) -> None:
        """Ajoute un utilisateur à la whitelist temporaire (24h)."""
        expiration = datetime.utcnow() + timedelta(hours=24)
        self.spam_whitelist[(user_id, guild_id)] = expiration
        logger.debug(f"Utilisateur {user_id} ajouté à la whitelist spam jusqu'à {expiration}")

    def is_spam_whitelisted(self, user_id: int, guild_id: int) -> bool:
        """Vérifie si un utilisateur est dans la whitelist spam."""
        key = (user_id, guild_id)
        if key in self.spam_whitelist:
            if datetime.utcnow() < self.spam_whitelist[key]:
                return True
            else:
                # Expirée, la supprimer
                del self.spam_whitelist[key]
        return False

    async def is_member_whitelisted(self, member: discord.Member, config: Dict[str, Any]) -> bool:
        """Vérifie si un membre est exempté de l'automod (admin, modo, rôle whitelisté)."""
        if member.bot:
            return True
        if member.guild_permissions.administrator:
            return True
        if member.guild_permissions.manage_messages:
            return True
        if member.guild_permissions.ban_members:
            return True

        # Vérifier les rôles whitelistés depuis la config
        whitelisted_roles = config.get('whitelisted_roles', []) or []
        member_role_ids = [role.id for role in member.roles]
        for role_id in whitelisted_roles:
            if role_id in member_role_ids:
                return True

        return False

    def is_channel_whitelisted(self, channel_id: int, config: Dict[str, Any]) -> bool:
        """Vérifie si un salon est exempté de l'automod."""
        whitelisted_channels = config.get('whitelisted_channels', []) or []
        return channel_id in whitelisted_channels

    def extract_urls(self, content: str) -> List[str]:
        """Extrait les URLs d'un message."""
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        return re.findall(url_pattern, content)

    def is_scam_domain(self, url: str, config: Dict[str, Any]) -> bool:
        """Vérifie si une URL appartient à un domaine de scam."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Vérifier les domaines de base
            for scam_domain in SCAM_DOMAINS:
                if domain == scam_domain or domain.endswith("." + scam_domain):
                    return True

            # Vérifier les domaines personnalisés
            custom_domains = config.get('custom_scam_domains', []) or []
            for scam_domain in custom_domains:
                if domain == scam_domain or domain.endswith("." + scam_domain):
                    return True

        except Exception:
            pass
        return False

    def is_scam_content(self, content: str, config: Dict[str, Any]) -> bool:
        """Vérifie si le contenu du message correspond à un pattern de scam."""
        content_lower = content.lower()

        # Vérifier les patterns de base
        for pattern in self.scam_patterns:
            if pattern.search(content_lower):
                return True

        # Vérifier les patterns personnalisés
        custom_patterns = config.get('custom_scam_patterns', []) or []
        for pattern_str in custom_patterns:
            try:
                pattern = re.compile(pattern_str, re.IGNORECASE)
                if pattern.search(content_lower):
                    return True
            except re.error:
                continue  # Ignorer les patterns invalides

        return False

    async def is_scam_message(self, message: discord.Message, config: Dict[str, Any]) -> bool:
        """Vérifie si un message est un scam."""
        content = message.content

        # Vérifier les patterns de scam dans le contenu
        if self.is_scam_content(content, config):
            return True

        # Vérifier les URLs
        urls = self.extract_urls(content)
        for url in urls:
            if self.is_scam_domain(url, config):
                return True

        return False

    async def handle_scam(self, message: discord.Message) -> None:
        """Gère un message scam détecté: supprime, ban, et log."""
        member = message.author
        guild = message.guild

        logger.warning(f"Scam détecté de {member.display_name} dans {guild.name}: {message.content[:100]}")

        # 1. Supprimer le message
        try:
            await message.delete()
            logger.info(f"Message scam supprimé de {member.display_name}")
        except discord.Forbidden:
            logger.error(f"Pas de permission pour supprimer le message scam de {member.display_name}")
        except discord.NotFound:
            pass  # Déjà supprimé

        # 2. Bannir l'utilisateur
        try:
            # Sauvegarder les rôles
            roles_to_backup = [
                role.id for role in member.roles
                if role != guild.default_role and role.name.lower() != "ban"
            ]

            # Sauvegarder les rôles avant le ban
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

            # Appliquer le ban sur tous les serveurs
            await self._apply_ban_all_guilds(member.id, "Scam détecté (auto-modération)")

            logger.info(f"Utilisateur {member.display_name} banni pour scam")

        except Exception as e:
            logger.exception(f"Erreur lors du ban pour scam: {e}")

        # 3. Envoyer un DM à l'utilisateur
        try:
            embed = discord.Embed(
                title="📛 Vous avez été banni(e) automatiquement",
                description="Votre message a été détecté comme un scam.",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Serveur", value=guild.name, inline=False)
            embed.add_field(name="Raison", value="Message de scam détecté", inline=False)
            embed.add_field(
                name="Contestation",
                value="Si vous pensez qu'il s'agit d'une erreur, contactez un administrateur.",
                inline=False
            )
            await member.send(embed=embed)
        except discord.Forbidden:
            pass  # DMs fermés

        # 4. Log dans le salon de modération
        await self._log_automod_action(
            guild=guild,
            action_type="scam",
            user=member,
            content=message.content,
            channel=message.channel
        )

    async def _apply_ban_all_guilds(self, user_id: int, reason: str) -> None:
        """Applique le rôle ban sur tous les serveurs."""
        for guild in self.bot.guilds:
            member = guild.get_member(user_id)
            if not member:
                continue

            ban_role_id = await self._mod_svc.get_ban_role_id(guild.id)
            if not ban_role_id:
                continue

            ban_role = guild.get_role(ban_role_id)
            if not ban_role or ban_role in member.roles:
                continue

            try:
                roles_to_remove = [role for role in member.roles if role != guild.default_role]
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason=reason)
                await member.add_roles(ban_role, reason=reason)
                logger.info(f"Rôle ban appliqué à {member.display_name} dans {guild.name}")
            except (discord.Forbidden, discord.HTTPException) as e:
                logger.error(f"Erreur ban {member.display_name} dans {guild.name}: {e}")

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
            mod_channel_id = await self._channel_svc.get_one(guild.id, "modération")
            if not mod_channel_id:
                logger.warning(f"Salon de modération non configuré pour {guild.name}")
                return

            mod_channel = guild.get_channel(mod_channel_id)
            if not mod_channel:
                logger.warning(f"Salon de modération {mod_channel_id} introuvable dans {guild.name}")
                return

            if action_type == "scam":
                embed = discord.Embed(
                    title="🚨 Scam détecté - Ban automatique",
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(name="Utilisateur", value=f"{user.mention} ({user.id})", inline=False)
                embed.add_field(name="Salon", value=channel.mention, inline=True)
                embed.add_field(name="Action", value="Ban permanent", inline=True)
                embed.add_field(
                    name="Contenu du message",
                    value=content[:1000] if len(content) <= 1000 else content[:997] + "...",
                    inline=False
                )
                embed.set_thumbnail(url=user.display_avatar.url)
            else:
                embed = discord.Embed(
                    title="⚠️ Auto-modération",
                    description=extra_info or "Action automatique effectuée",
                    color=discord.Color.orange(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(name="Utilisateur", value=f"{user.mention}", inline=True)

            await mod_channel.send(embed=embed)

        except Exception as e:
            logger.exception(f"Erreur lors du log automod: {e}")

    def _cleanup_message_cache(self) -> None:
        """Nettoie le cache des messages anciens (> 2 minutes)."""
        cutoff = datetime.utcnow() - timedelta(minutes=2)
        for user_id in list(self.message_cache.keys()):
            self.message_cache[user_id] = [
                entry for entry in self.message_cache[user_id]
                if entry[4] > cutoff
            ]
            if not self.message_cache[user_id]:
                del self.message_cache[user_id]

    async def check_cross_channel_spam(self, message: discord.Message, config: Dict[str, Any]) -> bool:
        """
        Vérifie si un utilisateur envoie le même message dans plusieurs salons.
        Retourne True si spam détecté selon la configuration.
        """
        user_id = message.author.id
        guild_id = message.guild.id
        channel_id = message.channel.id
        message_id = message.id
        content_hash = hash(message.content.lower().strip())
        now = datetime.utcnow()

        # Récupérer les paramètres de la config
        threshold = config.get('spam_channel_threshold', 3)
        time_window = config.get('spam_time_window', 60)

        # Nettoyer le cache périodiquement
        self._cleanup_message_cache()

        # Ajouter ce message au cache
        if user_id not in self.message_cache:
            self.message_cache[user_id] = []

        self.message_cache[user_id].append((guild_id, channel_id, message_id, content_hash, now))

        # Vérifier le spam multi-salons avec la fenêtre de temps configurée
        cutoff = now - timedelta(seconds=time_window)
        recent_messages = [
            entry for entry in self.message_cache[user_id]
            if entry[4] > cutoff and entry[0] == guild_id  # Même serveur
        ]

        # Trouver les salons différents avec le même contenu
        channels_with_same_content = set()

        for entry in recent_messages:
            if entry[3] == content_hash:  # Même hash de contenu
                channels_with_same_content.add(entry[1])

        # Vérifier selon le seuil configuré
        if len(channels_with_same_content) >= threshold:
            return True

        return False

    async def request_spam_confirmation(self, message: discord.Message) -> None:
        """Envoie une demande de confirmation aux modérateurs pour un spam détecté."""
        user = message.author
        guild = message.guild

        # Éviter les alertes en double
        if user.id in self.pending_spam_alerts:
            return
        self.pending_spam_alerts.add(user.id)

        try:
            # Récupérer les messages à signaler
            content_hash = hash(message.content.lower().strip())
            cutoff = datetime.utcnow() - timedelta(seconds=60)
            message_refs = []

            if user.id in self.message_cache:
                for entry in self.message_cache[user.id]:
                    if entry[3] == content_hash and entry[4] > cutoff and entry[0] == guild.id:
                        message_refs.append((entry[1], entry[2]))  # (channel_id, message_id)

            # Récupérer le salon de modération
            mod_channel_id = await self._channel_svc.get_one(guild.id, "modération")
            if not mod_channel_id:
                logger.warning(f"Salon de modération non configuré pour {guild.name}")
                self.pending_spam_alerts.discard(user.id)
                return

            mod_channel = guild.get_channel(mod_channel_id)
            if not mod_channel:
                logger.warning(f"Salon de modération introuvable pour {guild.name}")
                self.pending_spam_alerts.discard(user.id)
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

            # Créer l'embed
            embed = discord.Embed(
                title="⚠️ Spam multi-salons détecté",
                description="Un utilisateur a envoyé le même message dans plusieurs salons.",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Utilisateur", value=f"{user.mention} ({user.id})", inline=False)
            embed.add_field(
                name="Contenu du message",
                value=message.content[:500] if len(message.content) <= 500 else message.content[:497] + "...",
                inline=False
            )
            embed.add_field(
                name=f"Salons concernés ({len(channel_mentions)})",
                value="\n".join(channel_mentions[:10]) if channel_mentions else "Aucun",
                inline=False
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text="Cliquez sur un bouton pour agir")

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
            logger.info(f"Alerte spam envoyée pour {user.display_name} dans {guild.name}")

        except Exception as e:
            logger.exception(f"Erreur lors de l'envoi de l'alerte spam: {e}")
        finally:
            # Retirer de la liste après un délai pour éviter le spam d'alertes
            await discord.utils.sleep_until(datetime.utcnow() + timedelta(seconds=30))
            self.pending_spam_alerts.discard(user.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Écoute tous les messages pour la détection de scam et spam."""
        # Ignorer les DMs
        if not message.guild:
            return

        # Ignorer les bots
        if message.author.bot:
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

    # Créer le channel_service
    channel_service = ChannelConfigurationService(bot.db)

    await bot.add_cog(AutoMod(bot, moderation_service, channel_service, automod_service))
    logger.info("AutoMod Cog chargé avec succès.")
