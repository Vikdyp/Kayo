import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Dict, Any

from cogs.utilities.request_manager import enqueue_request
from cogs.utilities.data_manager import DataManager

logger = logging.getLogger('discord.configuration.channels')

class ChannelsConfiguration(commands.Cog):
    """Cog pour gérer la configuration des salons liés aux actions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.config: Dict[str, Any] = {}
        # Charger la config quand le bot sera prêt
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        self.config = await self.data.get_config()
        logger.info("ChannelsConfiguration: config chargée avec succès.")

    async def save_config(self) -> None:
        await self.data.save_config(self.config)
        logger.info("ChannelsConfiguration: config sauvegardée avec succès.")

    channels_group = app_commands.Group(
        name="channels",
        description="Gérer la configuration des salons",
        default_permissions=discord.Permissions(administrator=True)
    )

    @channels_group.command(name="get", description="Affiche les salons configurés")
    @enqueue_request()
    async def channels_get(self, interaction: discord.Interaction):
        channels = self.config.get("channels", {})
        if not channels:
            await interaction.followup.send("Aucun salon configuré.", ephemeral=True)
            return

        embed = discord.Embed(title="Salons Configurés", color=discord.Color.green())
        for action, channel_id in channels.items():
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                embed.add_field(name=action.capitalize(), value=channel.mention, inline=False)
            else:
                embed.add_field(name=action.capitalize(), value="Salon non trouvé", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"{interaction.user} a demandé d'afficher les salons configurés.")

    @channels_group.command(name="set", description="Configure un salon pour une action spécifique")
    @app_commands.describe(action="Nom de l'action (ex: report, notify)", channel="Salon Discord")
    @enqueue_request()
    async def channels_set(self, interaction: discord.Interaction, action: str, channel: discord.TextChannel):
        self.config.setdefault("channels", {})
        self.config["channels"][action.lower()] = channel.id
        await self.save_config()
        await interaction.followup.send(
            f"Salon `{channel.name}` configuré pour l'action `{action}` avec succès.",
            ephemeral=True
        )
        logger.info(f"Action `{action}` -> Salon `{channel.name}` ({channel.id}) configuré.")

    @channels_group.command(name="remove", description="Supprime la configuration d'un salon pour une action")
    @app_commands.describe(action="Nom de l'action (ex: report, notify)")
    @enqueue_request()
    async def channels_remove(self, interaction: discord.Interaction, action: str):
        channels = self.config.get("channels", {})
        action_lower = action.lower()
        if action_lower not in channels:
            await interaction.followup.send(
                f"Aucune configuration trouvée pour l'action `{action}`.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté de supprimer une configuration inexistante pour l'action: {action}")
            return

        del self.config["channels"][action_lower]
        await self.save_config()
        await interaction.followup.send(
            f"Configuration pour l'action `{action}` supprimée avec succès.",
            ephemeral=True
        )
        logger.info(f"Configuration de salon supprimée pour l'action `{action}`")

    @channels_get.error
    @channels_set.error
    @channels_remove.error
    async def channels_command_error(self, interaction: discord.Interaction, error: Exception):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.followup.send(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté d'utiliser une commande channels sans les permissions requises.")
        else:
            await interaction.followup.send(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors de l'exécution d'une commande channels par {interaction.user}: {error}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelsConfiguration(bot))
    logger.info("ChannelsConfiguration Cog chargé avec succès.")
