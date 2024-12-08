# cogs/ranking/link_valorant.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
import re
from urllib.parse import unquote
from typing import Optional

from ..utilities.utils import load_json, save_json

logger = logging.getLogger('discord.ranking.link_valorant')


class LinkValorant(commands.Cog):
    """Cog pour la commande de liaison de compte Valorant."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.valorant_api_key = bot.valorant_api_key
        self.user_data_file = 'data/user_data.json'
        self.config_file = 'data/config.json'
        self.config = {}
        self.user_data = {}
        self.bot.loop.create_task(self.load_all_data())

    async def load_all_data(self) -> None:
        """Charge la configuration et les données utilisateur depuis les fichiers JSON."""
        self.config = await load_json(self.config_file)
        self.user_data = await load_json(self.user_data_file)
        logger.info("LinkValorant: Configuration et données utilisateur chargées avec succès.")

    async def save_all_data(self) -> None:
        """Sauvegarde les données utilisateur dans le fichier JSON."""
        await save_json(self.user_data, self.user_data_file)
        logger.info("LinkValorant: Données utilisateur sauvegardées avec succès.")

    def extract_valorant_username(self, tracker_url: str) -> Optional[str]:
        """
        Extrait le nom d'utilisateur Valorant à partir de l'URL tracker.gg.

        Parameters:
            tracker_url (str): URL tracker.gg.

        Returns:
            Optional[str]: Nom d'utilisateur Valorant ou None si non trouvé.
        """
        decoded_url = unquote(tracker_url)
        match = re.search(r'riot/([^/]+)/overview', decoded_url)
        if match:
            return match.group(1)
        else:
            return None

    @app_commands.command(
        name="link_valorant",
        description="Lier un compte Valorant à votre compte Discord en utilisant l'URL tracker.gg"
    )
    async def link_valorant(
        self,
        interaction: discord.Interaction,
        tracker_url: str
    ) -> None:
        """
        Lie un compte Valorant à votre compte Discord.

        Parameters:
            interaction (discord.Interaction): L'interaction de l'utilisateur.
            tracker_url (str): URL tracker.gg pour le compte Valorant.
        """
        valorant_username = self.extract_valorant_username(tracker_url)
        if not valorant_username:
            await interaction.response.send_message(
                "URL invalide. Veuillez fournir une URL valide de tracker.gg.",
                ephemeral=True
            )
            logger.warning(f"Utilisateur {interaction.user} a fourni une URL de tracker.gg invalide: {tracker_url}")
            return

        logger.info(f"Demande de liaison de compte Valorant reçue: {valorant_username}")
        discord_user_id = str(interaction.user.id)
        existing_user_id = self.find_user_by_valorant_name(valorant_username)

        if existing_user_id and existing_user_id != discord_user_id:
            # Conflit détecté, envoyer un message dans le canal de conflit
            await self.bot.get_cog("ConflictResolution").handle_conflict(
                selected_user_id=discord_user_id,
                other_user_id=existing_user_id,
                valorant_username=valorant_username
            )
            await interaction.response.send_message(
                "Ce pseudo Valorant est déjà lié à un autre compte. Un conflit a été détecté et est en cours de traitement.",
                ephemeral=True
            )
            logger.warning(
                f"Conflit détecté pour le pseudo Valorant {valorant_username} entre {discord_user_id} et {existing_user_id}"
            )
        else:
            self.user_data[discord_user_id] = valorant_username
            await self.save_all_data()
            logger.info(f"Compte Valorant {valorant_username} lié avec succès à {discord_user_id}.")
            try:
                valorant_nickname = valorant_username.split('#')[0]
                await interaction.user.edit(nick=valorant_nickname)
                await self.bot.get_cog("AssignRankRole").assign_rank_role(interaction.user, valorant_username)
                await interaction.response.send_message(
                    f"Compte Valorant `{valorant_username}` lié avec succès et nom d'utilisateur mis à jour.",
                    ephemeral=True
                )
                logger.info(f"Nom d'utilisateur de {interaction.user} mis à jour à {valorant_nickname}")
            except discord.Forbidden:
                await interaction.response.send_message(
                    "Le bot n'a pas les permissions nécessaires pour changer votre pseudo. Veuillez contacter un administrateur.",
                    ephemeral=True
                )
                logger.error(f"Permission refusée pour changer le pseudo de {interaction.user}")
            except Exception as e:
                await interaction.response.send_message(
                    "Une erreur est survenue lors de la mise à jour de votre pseudo.",
                    ephemeral=True
                )
                logger.exception(f"Erreur lors de la mise à jour du pseudo de {interaction.user}: {e}")

    def find_user_by_valorant_name(self, valorant_username: str) -> Optional[str]:
        """
        Recherche un utilisateur Discord par son nom Valorant.

        Parameters:
            valorant_username (str): Nom d'utilisateur Valorant.

        Returns:
            Optional[str]: ID de l'utilisateur Discord ou None si non trouvé.
        """
        for user_id, username in self.user_data.items():
            if username.lower() == valorant_username.lower():
                return user_id
        return None

    @link_valorant.error
    async def link_valorant_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Gère les erreurs liées à la commande link_valorant."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté d'utiliser /link_valorant sans les permissions requises.")
        else:
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors de l'exécution de la commande link_valorant par {interaction.user}: {error}")


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog LinkValorant au bot."""
    await bot.add_cog(LinkValorant(bot))
    logger.info("LinkValorant Cog chargé avec succès.")
