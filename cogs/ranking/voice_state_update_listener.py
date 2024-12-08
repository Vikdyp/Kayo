# cogs/ranking/voice_state_update_listener.py

import discord
from discord.ext import commands
import logging

from ..utilities.utils import load_json, save_json

logger = logging.getLogger('discord.ranking.voice_state_update_listener')


class VoiceStateUpdateListener(commands.Cog):
    """Cog pour écouter les mises à jour d'état vocal et attribuer des rôles de rang."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_data_file = 'data/user_data.json'
        self.config_file = 'data/config.json'
        self.config = {}
        self.user_data = {}
        self.bot.loop.create_task(self.load_all_data())

    async def load_all_data(self) -> None:
        """Charge la configuration et les données utilisateur depuis les fichiers JSON."""
        self.config = await load_json(self.config_file)
        self.user_data = await load_json(self.user_data_file)
        logger.info("VoiceStateUpdateListener: Configuration et données utilisateur chargées avec succès.")

    async def save_all_data(self) -> None:
        """Sauvegarde les données utilisateur dans le fichier JSON."""
        await save_json(self.user_data, self.user_data_file)
        logger.info("VoiceStateUpdateListener: Données utilisateur sauvegardées avec succès.")

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ) -> None:
        """Listener pour l'événement on_voice_state_update."""
        logger.info(f"Mise à jour de l'état vocal pour {member.name}.")
        user_id = str(member.id)
        if user_id in self.user_data:
            valorant_username = self.user_data[user_id]
            logger.info(f"User {member.name} is linked to Valorant account {valorant_username}. Updating rank role.")
            await self.bot.get_cog("AssignRankRole").assign_rank_role(member, valorant_username)
        else:
            logger.info(f"User {member.name} is not linked to a Valorant account.")


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog VoiceStateUpdateListener au bot."""
    await bot.add_cog(VoiceStateUpdateListener(bot))
    logger.info("VoiceStateUpdateListener Cog chargé avec succès.")
