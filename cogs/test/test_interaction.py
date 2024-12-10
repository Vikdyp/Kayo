#cogs\configuration\channels_configuration.py
import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
from typing import Any, Dict

from cogs.utilities.request_manager import enqueue_request
from cogs.utilities.data_manager import DataManager

logger = logging.getLogger('discord.configuration.channels')

class ChannelsConfiguration(commands.Cog):
    """Cog pour gérer la configuration des salons liés aux actions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.config: Dict[str, Dict[str, int]] = {}
        asyncio.create_task(self.load_config())
        logger.info("ChannelsConfiguration initialisé.")

    async def load_config(self) -> None:
        self.config = await self.data.get_config()
        logger.info("Configuration chargée : %s", self.config)

    async def save_config(self) -> None:
        await self.data.save_config(self.config)
        logger.info("Configuration sauvegardée : %s", self.config)

    # Groupe de commandes pour gérer les salons
    channels_group = app_commands.Group(
        name="channels",
        description="Gérer la configuration des salons"
    )

    @channels_group.command(name="get", description="Affiche les salons configurés")
    async def channels_get(self, interaction):  # Suppression de l'annotation
        logger.info("Commande 'channels_get' appelée par %s", interaction.user)

        if not interaction.guild:
            await interaction.response.send_message(
                "Cette commande doit être exécutée dans un serveur.",
                ephemeral=True
            )
            return

        channels = self.config.get("channels", {})
        if not channels:
            await interaction.response.send_message("Aucun salon configuré.", ephemeral=True)
            return

        embed = discord.Embed(title="Salons Configurés", color=discord.Color.green())
        for action, channel_id in channels.items():
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                embed.add_field(name=action.capitalize(), value=channel.mention, inline=False)
            else:
                embed.add_field(name=action.capitalize(), value="Salon non trouvé", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info("Configuration des salons affichée à %s", interaction.user)

    @channels_group.command(name="set", description="Configure un salon pour une action spécifique")
    @app_commands.describe(action="Nom de l'action", channel="Salon Discord")
    async def channels_set(self, interaction, action: str, channel: discord.TextChannel):  # Pas d'annotation Interaction
        logger.info("Commande 'channels_set' appelée par %s pour l'action '%s'", interaction.user, action)

        if not interaction.guild:
            await interaction.response.send_message(
                "Cette commande doit être exécutée dans un serveur.",
                ephemeral=True
            )
            return

        if channel.guild.id != interaction.guild.id:
            await interaction.response.send_message(
                "Le salon doit appartenir à ce serveur.",
                ephemeral=True
            )
            return

        self.config.setdefault("channels", {})
        self.config["channels"][action.lower()] = channel.id
        await self.save_config()
        await interaction.response.send_message(
            f"Salon `{channel.name}` configuré pour l'action `{action}`.",
            ephemeral=True
        )
        logger.info("Salon configuré : action=%s, channel=%s (%s)", action, channel.name, channel.id)

    @channels_group.command(name="remove", description="Supprime la configuration d'un salon pour une action")
    @app_commands.describe(action="Nom de l'action")
    async def channels_remove(self, interaction, action: str):  # Pas d'annotation Interaction
        logger.info("Commande 'channels_remove' appelée par %s pour l'action '%s'", interaction.user, action)

        if not interaction.guild:
            await interaction.response.send_message(
                "Cette commande doit être exécutée dans un serveur.",
                ephemeral=True
            )
            return

        channels = self.config.get("channels", {})
        action_lower = action.lower()
        if action_lower not in channels:
            await interaction.response.send_message(
                f"Aucune configuration trouvée pour l'action `{action}`.",
                ephemeral=True
            )
            logger.warning("Aucune configuration trouvée pour l'action '%s'", action)
            return

        del self.config["channels"][action_lower]
        await self.save_config()
        await interaction.response.send_message(
            f"Configuration pour l'action `{action}` supprimée.",
            ephemeral=True
        )
        logger.info("Configuration supprimée pour l'action '%s'", action)

async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelsConfiguration(bot))
    logger.info("ChannelsConfiguration chargé.")
