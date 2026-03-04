# cogs/troll/quoicoubeh.py

import asyncio
import logging
import random
import re
import time

import discord
from discord import app_commands
from discord.ext import commands

from cogs.troll.services.quoicoubeh_service import QuoicoubehService

logger = logging.getLogger(__name__)


class QuoiResponder(commands.Cog):
    """Cog pour répondre automatiquement aux messages se terminant par 'quoi'."""

    def __init__(self, bot: commands.Bot, service: QuoicoubehService):
        self.bot = bot
        self._service = service

        self.responses = ["feur !", "coubeh !", "de neuf ?", "de beau ?"]
        self.special_response = f"easter egg ! contact <@{812367371570118756}>"
        self.special_probability = 0.00000001

        # Rate limiting
        self.max_responses_per_user = 5
        self.time_window = 60
        self.user_quoi_timestamps: dict[int, list[float]] = {}
        self.lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Listener
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if not re.search(r'\bquoi\s*\?*$', message.content, re.IGNORECASE):
            return

        current_time = time.time()
        user_id = message.author.id

        async with self.lock:
            timestamps = self.user_quoi_timestamps.get(user_id, [])
            timestamps = [t for t in timestamps if current_time - t < self.time_window]
            if len(timestamps) >= self.max_responses_per_user:
                return
            timestamps.append(current_time)
            self.user_quoi_timestamps[user_id] = timestamps

        if random.random() < self.special_probability:
            response = self.special_response
        else:
            response = random.choice(self.responses)

        emoji_obj = discord.utils.get(message.guild.emojis, name="pepe_clown")
        if emoji_obj:
            response += " " + str(emoji_obj)
        else:
            response += " :pepe_clown:"

        await message.channel.send(response)

        try:
            await self._service.record_trigger(
                message.guild.id, message.guild.name, message.author.id
            )
        except Exception as e:
            logger.error(f"Erreur enregistrement quoicoubeh: {e}")

    # ------------------------------------------------------------------
    # Slash command
    # ------------------------------------------------------------------

    @app_commands.command(
        name="quoiclassement",
        description="Affiche le classement des membres ayant déclenché le 'quoi' le plus souvent.",
    )
    async def quoiclassement(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Commande serveur uniquement.", ephemeral=True)
            return

        try:
            entries = await self._service.get_leaderboard(guild.id, limit=10)
            if not entries:
                await interaction.response.send_message("Aucune donnée disponible.", ephemeral=True)
                return

            medal_emojis = ["🥇", "🥈", "🥉"]
            description = ""
            top3_ids = {e.discord_user_id for e in entries[:3]}

            for idx, e in enumerate(entries, start=1):
                medal = medal_emojis[idx - 1] if idx <= 3 else ""
                description += f"{medal} **{idx}. <@{e.discord_user_id}>** - {e.trigger_count} quoicoubeh\n"

            embed = discord.Embed(
                title="Classement Quoi",
                description=description,
                color=discord.Color.blurple(),
            )

            # Mise à jour du rôle top 3
            top3_role_id = await self._service.get_top3_role_id(guild.id)
            top3_role = guild.get_role(top3_role_id) if top3_role_id else None

            if top3_role:
                for member in top3_role.members:
                    if member.id not in top3_ids:
                        try:
                            await member.remove_roles(top3_role, reason="Hors du top 3 quoicoubeh")
                        except Exception as e:
                            logger.error(f"Erreur retrait rôle top3 {member}: {e}")

                for uid in top3_ids:
                    member = guild.get_member(uid)
                    if member and top3_role not in member.roles:
                        try:
                            await member.add_roles(top3_role, reason="Top 3 quoicoubeh")
                        except Exception as e:
                            logger.error(f"Erreur ajout rôle top3 {member}: {e}")

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.exception(f"Erreur /quoiclassement: {e}")
            await interaction.response.send_message("Erreur lors de la récupération du classement.", ephemeral=True)

    async def cog_unload(self):
        self.user_quoi_timestamps.clear()


async def setup(bot: commands.Bot):
    from database.services.quoi_responses_service import QuoiResponsesService
    quoi_svc = QuoiResponsesService(bot.db)
    service = QuoicoubehService(quoi_svc, bot.role_config_svc)
    await bot.add_cog(QuoiResponder(bot, service))
    logger.info("QuoiResponder chargé.")
