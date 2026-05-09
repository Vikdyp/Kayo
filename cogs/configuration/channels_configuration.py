# cogs/configuration/channels_configuration.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import List, Optional

from cogs.configuration.presenters import (
    build_channels_list_embed,
    build_channels_status_embed,
    get_channel_display_name,
)
from cogs.configuration.services.channel_service import ChannelConfigurationService, normalize_key

logger = logging.getLogger(__name__)


class ChannelsConfiguration(commands.Cog):
    """Cog pour gérer la configuration des salons."""

    PREDEFINED_ACTIONS = [
        ("demande-deban", "Demande de déban"),
        ("conflict", "Gestion des conflits"),
        ("teams_forum_id", "Forum de présentation des équipes"),
        ("inscription_tournament_channel_id", "Salon d'inscription aux tournois"),
        ("tournament_channel_id", "Salon des tournois"),
        ("fer", "Salon rang fer"),
        ("bronze", "Salon rang bronze"),
        ("argent", "Salon rang argent"),
        ("or", "Salon rang or"),
        ("platine", "Salon rang platine"),
        ("diamant", "Salon rang diamant"),
        ("ascendant", "Salon rang ascendant"),
        ("immortel", "Salon rang immortel"),
        ("radiant", "Salon rang radiant"),
        ("welcome", "Salon d'acceuil"),
        ("stat_embed", "Salon embed statistiques"),
        ("rules", "Salon des regle du serveur"),
        ("introductions", "salon pour la presentation du serveur"),
        ("modération", "salon de modération"),
        ("rang", "salon pour definir les rang"),
        ("twitch", "salon des notif twitch"),
        ("valorant_shop", "Salon des shops Valorant"),
        ("file_counter", "Salon compteur de fichiers"),
        ("temp_vocal_category", "Categorie des vocaux temporaires"),
        ("temp_vocal_lobby", "Salon lobby vocal (creation VC)"),
        ("voice_cleaner_category", "Categorie nettoyee (voice cleaner)"),
        ("voice_cleaner_afk", "Salon AFK a exclure (voice cleaner)"),
        ("matchmaking_voice_category", "Categorie vocale matchmaking"),
        ("deban_category", "Categorie des demande de deban"),
        ("rank_up", "Salon de notif de rang"),
    ]

    ACTION_CHOICES = [
        app_commands.Choice(name="Afficher ce qu'il manque", value="status"),
        app_commands.Choice(name="Afficher les salons configurés", value="get"),
        app_commands.Choice(name="Configurer un salon", value="set"),
        app_commands.Choice(name="Supprimer un salon", value="remove"),
    ]

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        service = getattr(bot, "channel_configuration_service", None)
        if service is None:
            raise RuntimeError("bot.channel_configuration_service is not set.")

        self.service = service

        # petit cache local pour display name
        self._display_by_key = {k: d for k, d in self.PREDEFINED_ACTIONS}

        logger.info("ChannelsConfiguration initialisé.")

    @app_commands.command(name="salon", description="Gérer la configuration des salons.")
    @app_commands.describe(
        action="Action à effectuer",
        salon_action="Clé du salon (ex: welcome, rules, ...)",
        channel="Salon Discord (nécessaire pour 'set')",
    )
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def channels_execute(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        salon_action: Optional[str] = None,
        channel: Optional[discord.abc.GuildChannel] = None,
    ):
        try:
            await interaction.response.defer(thinking=True)

            if not interaction.guild:
                await interaction.followup.send("Cette commande doit être exécutée dans un serveur.", ephemeral=True)
                return

            guild = interaction.guild
            guild_id = guild.id
            guild_name = guild.name
            action_lower = action.value.lower()

            # ---------- GET ----------
            if action_lower == "get":
                channels = await self.service.get_all(guild_id)
                if not channels:
                    await interaction.followup.send("Aucun salon configuré.", ephemeral=True)
                    return

                embed = build_channels_list_embed(guild, channels, self._display_by_key)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # ---------- STATUS ----------
            if action_lower == "status":
                channels = await self.service.get_all(guild_id)
                embed = build_channels_status_embed(
                    guild,
                    channels,
                    self.PREDEFINED_ACTIONS,
                    self._display_by_key,
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # ---------- SET ----------
            if action_lower == "set":
                if not salon_action or channel is None:
                    await interaction.followup.send(
                        "Veuillez spécifier `salon_action` et `channel`.", ephemeral=True
                    )
                    return

                if channel.guild.id != guild_id:
                    await interaction.followup.send("Le salon doit appartenir à ce serveur.", ephemeral=True)
                    return

                key = normalize_key(salon_action)
                await self.service.set_one(guild_id, guild_name, key, channel.id)

                await interaction.followup.send(
                    f"Salon {channel.mention} configuré pour **{self.get_action_display_name(key)}** (`{key}`).",
                    ephemeral=True,
                )
                return

            # ---------- REMOVE ----------
            if action_lower == "remove":
                if not salon_action:
                    await interaction.followup.send("Veuillez spécifier `salon_action`.", ephemeral=True)
                    return

                key = normalize_key(salon_action)
                existing = await self.service.get_one(guild_id, key)
                if existing is None:
                    await interaction.followup.send(
                        f"Aucune configuration trouvée pour **{self.get_action_display_name(key)}** (`{key}`).",
                        ephemeral=True,
                    )
                    return

                success = await self.service.remove_one(guild_id, key)
                if success:
                    await interaction.followup.send(
                        f"Configuration supprimée pour **{self.get_action_display_name(key)}** (`{key}`).",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send("Suppression échouée (DB).", ephemeral=True)
                return

            await interaction.followup.send(f"Action non prise en charge : **{action.value}**.", ephemeral=True)

        except Exception as e:
            logger.exception(f"Erreur dans /salon ({action.value=}): {e}")
            # Si defer déjà fait, followup marche
            await interaction.followup.send("Une erreur est survenue.", ephemeral=True)

    def get_action_display_name(self, action_key: str) -> str:
        return get_channel_display_name(action_key, self._display_by_key)

    @channels_execute.autocomplete("salon_action")
    async def salon_action_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        current_lower = current.lower()
        matches: List[app_commands.Choice[str]] = []
        for action, description in self.PREDEFINED_ACTIONS:
            if current_lower in action.lower() or current_lower in description.lower():
                matches.append(app_commands.Choice(name=description, value=action))
        return matches[:25]


async def setup(bot: commands.Bot):
    try:
        cog = ChannelsConfiguration(bot)
    except RuntimeError as exc:
        logger.error("ChannelsConfiguration non chargé: %s", exc)
        return

    await bot.add_cog(cog)
    logger.info("ChannelsConfiguration Cog chargé.")
