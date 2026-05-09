from __future__ import annotations

import discord


class CreateScrimView(discord.ui.View):
    def __init__(self, cog) -> None:
        super().__init__(timeout=None)
        self._cog = cog

    @discord.ui.button(label="Creer un scrim", style=discord.ButtonStyle.primary, custom_id="create_scrim")
    async def create_scrim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ScrimModal(self._cog))


class ScrimModal(discord.ui.Modal, title="Creer un scrim"):
    date = discord.ui.TextInput(label="Date (JJ/MM/YYYY)", placeholder="Ex: 25/12/2026", required=True)
    time = discord.ui.TextInput(label="Heure (HH:MM)", placeholder="Ex: 20:00", required=True)
    map_name = discord.ui.TextInput(label="Map", placeholder="Nom de la map", required=True)
    rank_name = discord.ui.TextInput(label="Rang", placeholder="Ex: Bronze, Argent, Or...", required=True)
    notes = discord.ui.TextInput(
        label="Autres precisions",
        placeholder="Informations supplementaires",
        style=discord.TextStyle.paragraph,
        required=False,
    )

    def __init__(self, cog) -> None:
        super().__init__()
        self._cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._cog.handle_create_scrim_submit(interaction, self)


class ScrimView(discord.ui.View):
    def __init__(self, cog, scrim_id: int) -> None:
        super().__init__(timeout=None)
        self._cog = cog
        self._scrim_id = scrim_id

    @discord.ui.button(label="Rejoindre Equipe 1", style=discord.ButtonStyle.success, custom_id="join_team1")
    async def join_team1(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._cog.handle_join_team(interaction, self._scrim_id, "team1")

    @discord.ui.button(label="Rejoindre Equipe 2", style=discord.ButtonStyle.success, custom_id="join_team2")
    async def join_team2(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._cog.handle_join_team(interaction, self._scrim_id, "team2")

    @discord.ui.button(label="Quitter le scrim", style=discord.ButtonStyle.danger, custom_id="leave_scrim")
    async def leave_scrim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._cog.handle_leave_scrim(interaction, self._scrim_id)
