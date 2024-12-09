import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional

from cogs.utilities.utils import load_json, save_json
from cogs.utilities.confirmation_view import ConfirmationView

logger = logging.getLogger('discord.moderation.clean_number')

class CleanNumber(commands.Cog):
    """Cog pour la commande de nettoyage d'un nombre spécifique de messages dans un salon."""

    dependencies = []

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.config = {}
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration depuis le fichier JSON."""
        self.config = await load_json(self.config_file)
        logger.info("CleanNumber: Configuration chargée avec succès.")

    @app_commands.command(name="clean_number", description="Supprime un nombre spécifié de messages")
    @app_commands.describe(count="Le nombre de messages à supprimer", channel="Le salon à nettoyer (optionnel)")
    @app_commands.default_permissions(administrator=True)
    async def clean_number(self, interaction: discord.Interaction, count: int, channel: Optional[discord.TextChannel] = None) -> None:
        """Supprime un nombre spécifié de messages dans un salon après confirmation."""
        if count < 1 or count > 100:
            return await interaction.response.send_message(
                "Le nombre de messages à supprimer doit être entre 1 et 100.",
                ephemeral=True
            )
        target_channel = channel or interaction.channel
        await interaction.response.send_message(
            f"Êtes-vous sûr de vouloir supprimer {count} messages dans {target_channel.mention} ?",
            view=ConfirmationView(interaction, target_channel=target_channel, count=count)
        )
        logger.info(f"{interaction.user} a demandé de nettoyer {count} messages dans {target_channel.name}.")

    @clean_number.error
    async def clean_number_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Gère les erreurs liées à la commande clean_number."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté d'utiliser /clean_number sans les permissions requises.")
        elif isinstance(error, app_commands.BadArgument):
            await interaction.response.send_message(
                "Veuillez spécifier un nombre valide de messages à supprimer.",
                ephemeral=True
            )
            logger.warning(f"Argument invalide fourni pour la commande /clean_number par {interaction.user}.")
        else:
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors de l'exécution de la commande clean_number par {interaction.user}: {error}")

async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog CleanNumber au bot."""
    if bot.get_cog("CleanNumber"):
        logger.warning("CleanNumber Cog déjà chargé. Ignoré.")
        return
    await bot.add_cog(CleanNumber(bot))
    logger.info("CleanNumber Cog chargé avec succès.")
