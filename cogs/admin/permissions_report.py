from __future__ import annotations

import io

import discord
from discord import app_commands
from discord.ext import commands

from cogs.admin.presenters import build_permissions_csv


class PermissionsReportCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="permissions_report",
        description="Genere un rapport CSV des permissions des roles par salon.",
    )
    @app_commands.default_permissions(administrator=True)
    async def permissions_report(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("Cette commande doit etre executee dans un serveur.", ephemeral=True)
            return

        csv_content = build_permissions_csv(roles=guild.roles, channels=guild.channels)
        file = discord.File(
            fp=io.BytesIO(csv_content.encode("utf-8-sig")),
            filename="rapport_permissions.csv",
        )
        await interaction.followup.send(
            content="Rapport CSV des permissions.",
            file=file,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PermissionsReportCog(bot))
