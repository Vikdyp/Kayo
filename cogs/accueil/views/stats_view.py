# cogs/accueil/views/stats_view.py
"""Persistent view for member statistics embeds."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from cogs.accueil.stalker import StalkerCog


PERIOD_TO_CUSTOM_ID = {
    "7j": "stats_7j",
    "1m": "stats_1m",
    "default": "stats_1m",
    "1a": "stats_1a",
    "total": "stats_total",
}


class StatsView(discord.ui.View):
    def __init__(
        self,
        cog: "StalkerCog",
        guild: discord.Guild,
        current_period: str = "default",
    ):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild = guild
        self.current_period = current_period
        self._update_button_styles()

    def _update_button_styles(self) -> None:
        """Met à jour les styles des boutons pour montrer la période active."""
        active_custom_id = PERIOD_TO_CUSTOM_ID.get(self.current_period)
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == active_custom_id:
                    item.style = discord.ButtonStyle.success
                elif item.custom_id != "stats_update":
                    item.style = discord.ButtonStyle.secondary

    @discord.ui.button(label="Mettre à jour", style=discord.ButtonStyle.primary, custom_id="stats_update")
    async def update_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer()
        await self.cog.update_stats_embed(interaction.guild, period=self.current_period)
        await interaction.followup.send("Embed mis à jour.", ephemeral=True)

    @discord.ui.button(label="7 jours", style=discord.ButtonStyle.secondary, custom_id="stats_7j")
    async def seven_days(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer()
        await self.cog.update_stats_embed(interaction.guild, period="7j")
        await interaction.followup.send("Affichage des stats sur 7 jours.", ephemeral=True)

    @discord.ui.button(label="1 mois", style=discord.ButtonStyle.secondary, custom_id="stats_1m")
    async def one_month(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer()
        await self.cog.update_stats_embed(interaction.guild, period="1m")
        await interaction.followup.send("Affichage des stats sur 1 mois.", ephemeral=True)

    @discord.ui.button(label="1 an", style=discord.ButtonStyle.secondary, custom_id="stats_1a")
    async def one_year(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer()
        await self.cog.update_stats_embed(interaction.guild, period="1a")
        await interaction.followup.send("Affichage des stats sur 1 an.", ephemeral=True)

    @discord.ui.button(label="Total", style=discord.ButtonStyle.secondary, custom_id="stats_total")
    async def total_stats(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer()
        await self.cog.update_stats_embed(interaction.guild, period="total")
        await interaction.followup.send("Affichage des stats totales.", ephemeral=True)
