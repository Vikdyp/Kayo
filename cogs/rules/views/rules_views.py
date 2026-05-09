from __future__ import annotations

import discord


class AcceptRulesView(discord.ui.View):
    def __init__(self, cog) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Accepter le reglement",
        style=discord.ButtonStyle.success,
        custom_id="button:accept_rules",
    )
    async def accept_rules_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.cog.handle_rules_acceptance(interaction)
