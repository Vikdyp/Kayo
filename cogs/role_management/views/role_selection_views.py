from __future__ import annotations

import discord


class GameRolesView(discord.ui.View):
    def __init__(self, cog) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Initiator", style=discord.ButtonStyle.primary, custom_id="role_button:initiator")
    async def initiator_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.handle_role_selection(interaction, "initiator")

    @discord.ui.button(label="Controller", style=discord.ButtonStyle.primary, custom_id="role_button:controller")
    async def controller_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.handle_role_selection(interaction, "controller")

    @discord.ui.button(label="Duelist", style=discord.ButtonStyle.primary, custom_id="role_button:duelist")
    async def duelist_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.handle_role_selection(interaction, "duelist")

    @discord.ui.button(label="Sentinel", style=discord.ButtonStyle.primary, custom_id="role_button:sentinel")
    async def sentinel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.handle_role_selection(interaction, "sentinel")

    @discord.ui.button(label="Fill", style=discord.ButtonStyle.primary, custom_id="role_button:fill")
    async def fill_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.handle_role_selection(interaction, "fill")


class LanguageRolesView(discord.ui.View):
    def __init__(self, cog) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Francais", style=discord.ButtonStyle.primary, custom_id="role_button:francais")
    async def francais_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.handle_role_selection(interaction, "francais")

    @discord.ui.button(label="Anglais", style=discord.ButtonStyle.primary, custom_id="role_button:anglais")
    async def anglais_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.handle_role_selection(interaction, "anglais")

    @discord.ui.button(label="Espagnol", style=discord.ButtonStyle.primary, custom_id="role_button:espagnol")
    async def espagnol_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.handle_role_selection(interaction, "espagnol")
