from __future__ import annotations

import discord


class FileCounterView(discord.ui.View):
    def __init__(self, cog) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.green, custom_id="file_counter:ajouter")
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.handle_counter_increment(interaction, "add")

    @discord.ui.button(label="Terminer", style=discord.ButtonStyle.blurple, custom_id="file_counter:terminer")
    async def complete_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.handle_counter_increment(interaction, "complete")
