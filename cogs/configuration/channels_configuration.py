# cogs/configuration/channels_configuration.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
from typing import Dict

from cogs.utilities.request_manager import enqueue_request
from cogs.utilities.data_manager import DataManager

# Configurer le logger pour ce cog
logger = logging.getLogger('configuration.channel')

class ChannelsConfiguration(commands.Cog):
    """Cog pour gérer la configuration des salons."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.config: Dict[str, int] = {}
        asyncio.create_task(self.load_config())
        logger.info("ChannelsConfiguration initialisé.")

    async def load_config(self):
        """Charge la configuration des salons depuis la base de données."""
        try:
            full_config = await self.data.get_config()
            self.config = full_config.get("channels", {})
            logger.info("Configuration des salons chargée : %s", self.config)
        except Exception as e:
            logger.error("Erreur lors du chargement de la configuration des salons : %s", e)
            self.config = {}

    async def save_config(self):
        """Sauvegarde la configuration des salons dans la base de données."""
        try:
            full_config = await self.data.get_config()
            full_config["channels"] = self.config
            await self.data.save_config(full_config)
            logger.info("Configuration des salons sauvegardée : %s", self.config)
        except Exception as e:
            logger.error("Erreur lors de la sauvegarde de la configuration des salons : %s", e)

    # Liste prédéfinie des actions et leurs descriptions
    PREDEFINED_ACTIONS = [
        ("demande-deban", "Demande de déban"),
        ("conflict", "Gestion des conflits"),
        ("teams_forum_id", "Forum de présentation des équipes"),
        ("inscription_tournament_channel_id", "Salon d'inscription aux tournois"),
        ("tournament_channel_id", "Salon des tournois")
    ]

    # Création des choix pour les actions prédéfinies
    ACTION_CHOICES = [
        app_commands.Choice(name=description, value=action)
        for action, description in PREDEFINED_ACTIONS
    ]

    # Groupe de commandes /channel
    channel_group = app_commands.Group(
        name="channel",
        description="Gérer la configuration des salons",
        default_permissions=discord.Permissions(administrator=True)  # Restriction aux administrateurs
    )

    @channel_group.command(name="get", description="Affiche les salons configurés.")
    @enqueue_request()
    async def channels_get(self, interaction: discord.Interaction):
        """Commande /channel get : Affiche les salons configurés."""
        try:
            logger.debug(f"Executing channels_get for interaction={interaction.id}")
            if not interaction.guild:
                await interaction.followup.send(
                    "Cette commande doit être exécutée dans un serveur.", ephemeral=True
                )
                return

            channels = self.config
            logger.debug(f"Channels config: {channels}")
            if not channels:
                await interaction.followup.send("Aucun salon configuré.", ephemeral=True)
                return

            embed = discord.Embed(title="Salons Configurés", color=discord.Color.green())
            for action, channel_id in channels.items():
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    embed.add_field(name=self.get_action_display_name(action), value=channel.mention, inline=False)
                else:
                    embed.add_field(name=self.get_action_display_name(action), value="Salon non trouvé", inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.debug(f"channels_get exécuté avec succès pour interaction={interaction.id}")
        except Exception as e:
            logger.exception(f"Erreur dans channels_get pour interaction={interaction.id}: {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors du traitement de votre requête.", ephemeral=True
            )

    @channel_group.command(name="set", description="Configure un salon pour une action spécifique.")
    @app_commands.describe(action="Action à configurer", channel="Salon Discord")
    @app_commands.choices(action=ACTION_CHOICES)
    @enqueue_request()
    async def channels_set(self, interaction: discord.Interaction, action: app_commands.Choice[str], channel: discord.TextChannel):
        """Commande /channel set : Configure un salon pour une action spécifique."""
        try:
            logger.debug(f"Executing channels_set pour interaction={interaction.id} avec action={action.value}, channel={channel.id}")
            if not interaction.guild:
                await interaction.followup.send(
                    "Cette commande doit être exécutée dans un serveur.", ephemeral=True
                )
                return

            if channel.guild.id != interaction.guild.id:
                await interaction.followup.send(
                    "Le salon doit appartenir à ce serveur.", ephemeral=True
                )
                return

            action_lower = action.value.lower()
            valid_actions = [a[0] for a in self.PREDEFINED_ACTIONS]
            if action_lower not in valid_actions:
                await interaction.followup.send(
                    f"Action invalide. Choisissez parmi les suivantes : {', '.join(valid_actions)}.", ephemeral=True
                )
                return

            self.config[action_lower] = channel.id
            await self.save_config()
            await interaction.followup.send(
                f"Salon {channel.name} configuré pour l'action {self.get_action_display_name(action_lower)}.", ephemeral=True
            )
            logger.debug(f"channels_set exécuté avec succès pour interaction={interaction.id}")
        except Exception as e:
            logger.exception(f"Erreur dans channels_set pour interaction={interaction.id}: {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors du traitement de votre requête.", ephemeral=True
            )

    @channel_group.command(name="remove", description="Supprime la configuration d'un salon pour une action.")
    @app_commands.describe(action="Action à supprimer")
    @app_commands.choices(action=ACTION_CHOICES)
    @enqueue_request()
    async def channels_remove(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        """Commande /channel remove : Supprime la configuration d'un salon pour une action."""
        try:
            logger.debug(f"Executing channels_remove pour interaction={interaction.id} avec action={action.value}")
            if not interaction.guild:
                await interaction.followup.send(
                    "Cette commande doit être exécutée dans un serveur.", ephemeral=True
                )
                return

            action_lower = action.value.lower()
            if action_lower not in self.config:
                await interaction.followup.send(
                    f"Aucune configuration trouvée pour l'action {self.get_action_display_name(action_lower)}.", ephemeral=True
                )
                logger.warning(f"{interaction.user} a tenté de supprimer un mapping inexistant: {action.value}")
                return

            del self.config[action_lower]
            await self.save_config()
            await interaction.followup.send(
                f"Configuration pour l'action {self.get_action_display_name(action_lower)} supprimée.", ephemeral=True
            )
            logger.debug(f"channels_remove exécuté avec succès pour interaction={interaction.id}")
        except Exception as e:
            logger.exception(f"Erreur dans channels_remove pour interaction={interaction.id}: {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors du traitement de votre requête.", ephemeral=True
            )

    def get_action_display_name(self, action_key: str) -> str:
        """Retourne le nom affiché de l'action."""
        for key, description in self.PREDEFINED_ACTIONS:
            if key == action_key:
                return description
        return action_key.capitalize()

async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelsConfiguration(bot))
    logger.info("ChannelsConfiguration Cog chargé.")
