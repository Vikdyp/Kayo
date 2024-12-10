# cogs/ranking/link_valorant.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
import re
from urllib.parse import unquote
from typing import Optional, Any

from cogs.utilities.utils import load_json, save_json
from cogs.utilities.data_manager import DataManager
from cogs.utilities.request_manager import enqueue_request
from cogs.utilities.confirmation_view import ConfirmationView

logger = logging.getLogger('discord.ranking.link_valorant')

class LinkValorant(commands.Cog):
    """Cog pour la commande de liaison de compte Valorant."""

    dependencies = []

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.valorant_api_key = bot.valorant_api_key
        self.user_data_file = 'data/user_data.json'
        self.config_file = 'data/config.json'
        self.config = {}
        self.user_data = {}
        self.data = DataManager()
        self.bot.loop.create_task(self.load_all_data())

    async def load_all_data(self) -> None:
        self.config = await self.data.get_config()
        self.user_data = await self.data.load_json(self.user_data_file)
        logger.info("LinkValorant: Configuration et données utilisateur chargées avec succès.")

    async def save_all_data(self) -> None:
        await self.data.save_json(self.user_data_file, self.user_data)
        logger.info("LinkValorant: Données utilisateur sauvegardées avec succès.")

    def extract_valorant_username(self, tracker_url: str) -> Optional[str]:
        decoded_url = unquote(tracker_url)
        match = re.search(r'riot/([^/]+)/overview', decoded_url)
        if match:
            return match.group(1)
        else:
            return None

    async def ask_confirmation(self, interaction: Any, message: str):
        view = ConfirmationView(interaction, None)
        await interaction.followup.send(message, view=view, ephemeral=True)
        await view.wait()
        return view.value

    @app_commands.command(
        name="link_valorant",
        description="Lier un compte Valorant à votre compte Discord en utilisant l'URL tracker.gg"
    )
    @enqueue_request()
    async def link_valorant(self, interaction: Any, tracker_url: str):
        valorant_username = self.extract_valorant_username(tracker_url)
        if not valorant_username:
            await interaction.response.send_message(
                "URL invalide. Veuillez fournir une URL valide de tracker.gg.",
                ephemeral=True
            )
            logger.warning(f"Utilisateur {interaction.user} URL invalide: {tracker_url}")
            return

        await interaction.response.defer(ephemeral=True)

        if not await self.ask_confirmation(interaction, f"Confirmez-vous la liaison du compte Valorant `{valorant_username}` à votre compte Discord ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)

        logger.info(f"Demande de liaison Valorant: {valorant_username}")
        discord_user_id = str(interaction.user.id)
        existing_user_id = self.find_user_by_valorant_name(valorant_username)

        if existing_user_id and existing_user_id != discord_user_id:
            await self.bot.get_cog("ConflictResolution").handle_conflict(
                selected_user_id=discord_user_id,
                other_user_id=existing_user_id,
                valorant_username=valorant_username
            )
            await interaction.followup.send(
                "Ce pseudo Valorant est déjà lié à un autre compte. Un conflit a été détecté.",
                ephemeral=True
            )
            logger.warning(
                f"Conflit détecté {valorant_username} entre {discord_user_id} et {existing_user_id}"
            )
        else:
            self.user_data[discord_user_id] = valorant_username
            await self.save_all_data()
            logger.info(f"Compte Valorant {valorant_username} lié à {discord_user_id}.")
            try:
                valorant_nickname = valorant_username.split('#')[0]
                await interaction.user.edit(nick=valorant_nickname)
                assign_cog = self.bot.get_cog("AssignRankRole")
                if assign_cog:
                    await assign_cog.assign_rank_role(interaction.user, valorant_username)
                await interaction.followup.send(
                    f"Compte Valorant `{valorant_username}` lié avec succès, pseudo mis à jour.",
                    ephemeral=True
                )
                logger.info(f"Pseudo {interaction.user} -> {valorant_nickname}")
            except discord.Forbidden:
                await interaction.followup.send(
                    "Le bot n'a pas la permission de changer votre pseudo.",
                    ephemeral=True
                )
                logger.error(f"Permission refusée pour changer le pseudo de {interaction.user}")
            except Exception as e:
                await interaction.followup.send(
                    "Une erreur est survenue lors de la mise à jour de votre pseudo.",
                    ephemeral=True
                )
                logger.exception(f"Erreur mise à jour pseudo {interaction.user}: {e}")

    def find_user_by_valorant_name(self, valorant_username: str) -> Optional[str]:
        for user_id, username in self.user_data.items():
            if username.lower() == valorant_username.lower():
                return user_id
        return None

    @link_valorant.error
    async def link_valorant_error(self, interaction: Any, error: Exception):
        await interaction.followup.send("Une erreur est survenue.", ephemeral=True)
        logger.exception(f"Erreur link_valorant {interaction.user}: {error}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LinkValorant(bot))
    logger.info("LinkValorant Cog chargé avec succès.")
