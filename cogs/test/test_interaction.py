#cogs\configuration\channels_configuration.py
import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
from typing import Dict

from cogs.utilities.request_manager import enqueue_request, request_manager
from cogs.utilities.data_manager import DataManager

logger = logging.getLogger('discord.configuration.channels')

class ChannelsConfiguration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.config: Dict[str, Dict[str, int]] = {}
        asyncio.create_task(self.load_config())
        logger.info("ChannelsConfiguration initialisé.")

    async def load_config(self):
        try:
            self.config = await self.data.get_config()
            logger.info("Configuration chargée : %s", self.config)
        except Exception as e:
            logger.error("Erreur lors du chargement de la configuration : %s", e)
            self.config = {}

    async def save_config(self):
        try:
            await self.data.save_config(self.config)
            logger.info("Configuration sauvegardée : %s", self.config)
        except Exception as e:
            logger.error("Erreur lors de la sauvegarde de la configuration : %s", e)

    channels_group = app_commands.Group(
        name="channels",
        description="Gérer la configuration des salons"
    )

    @channels_group.command(name="get", description="Affiche les salons configurés.")
    @enqueue_request()
    async def channels_get(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(
                "Cette commande doit être exécutée dans un serveur.", ephemeral=True
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

    @channels_group.command(name="set", description="Configure un salon pour une action spécifique.")
    @app_commands.describe(action="Nom de l'action", channel="Salon Discord")
    @enqueue_request()
    async def channels_set(self, interaction: discord.Interaction, action: str, channel: discord.TextChannel):
        if not interaction.guild:
            await interaction.response.send_message(
                "Cette commande doit être exécutée dans un serveur.", ephemeral=True
            )
            return

        if channel.guild.id != interaction.guild.id:
            await interaction.response.send_message(
                "Le salon doit appartenir à ce serveur.", ephemeral=True
            )
            return

        self.config.setdefault("channels", {})
        self.config["channels"][action.lower()] = channel.id
        await self.save_config()
        await interaction.response.send_message(
            f"Salon `{channel.name}` configuré pour l'action `{action}`.", ephemeral=True
        )

    @channels_group.command(name="remove", description="Supprime la configuration d'un salon pour une action.")
    @app_commands.describe(action="Nom de l'action")
    @enqueue_request()
    async def channels_remove(self, interaction: discord.Interaction, action: str):
        if not interaction.guild:
            await interaction.response.send_message(
                "Cette commande doit être exécutée dans un serveur.", ephemeral=True
            )
            return

        channels = self.config.get("channels", {})
        action_lower = action.lower()
        if action_lower not in channels:
            await interaction.response.send_message(
                f"Aucune configuration trouvée pour l'action `{action}`.", ephemeral=True
            )
            return

        del self.config["channels"][action_lower]
        await self.save_config()
        await interaction.response.send_message(
            f"Configuration pour l'action `{action}` supprimée.", ephemeral=True
        )


    @channels_group.command(name="test_process", description="Test direct command execution.")
    async def test_process(self, interaction: discord.Interaction):
        await interaction.response.send_message("Commande exécutée immédiatement.", ephemeral=True)
        logger.info(f"Command test_process executed for interaction={interaction.id}")

        
    @channels_group.command(name="test_queue", description="Test command queuing.")
    @enqueue_request()
    async def test_queue(self, interaction: discord.Interaction):
        logger.info(f"Simulating a long task for interaction={interaction.id}")
        await asyncio.sleep(5)  # Simule un traitement long
        await interaction.followup.send("Commande exécutée après traitement en file.", ephemeral=True)
        logger.info(f"Completed simulated task for interaction={interaction.id}")


    @app_commands.command(name="check_queue", description="Check the request queue.")
    async def check_queue(self, interaction: discord.Interaction):
        queue_size = len(request_manager.queue)
        await interaction.response.send_message(f"Queue size: {queue_size}", ephemeral=True)
        logger.info(f"Queue size reported: {queue_size}")


    @channels_group.command(name="simulate_task", description="Simulate a long task execution.")
    @enqueue_request()
    async def simulate_task(self, interaction: discord.Interaction):
        logger.info(f"Simulating a task for interaction={interaction.id}")
        await asyncio.sleep(5)  # Simule une tâche longue
        await interaction.followup.send(f"Task completed for interaction {interaction.id}.", ephemeral=True)
        logger.info(f"Simulated task completed for interaction={interaction.id}")

    @channels_group.command(name="restart_processing", description="Restart the request processing loop.")
    async def restart_processing(self, interaction: discord.Interaction):
        if request_manager.processing_task is None or request_manager.processing_task.done():
            request_manager.start(self.bot)
            await interaction.response.send_message("Request processing loop restarted.", ephemeral=True)
            logger.info("Request processing loop restarted manually.")
        else:
            await interaction.response.send_message("Request processing loop is already running.", ephemeral=True)
            logger.info("Request processing loop is already running.")



async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelsConfiguration(bot))
