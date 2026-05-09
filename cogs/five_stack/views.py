from __future__ import annotations

import discord


TEAM_SIZE_OPTIONS = [
    discord.SelectOption(label="Any", value="0", description="Le bot choisit la meilleure taille disponible."),
    discord.SelectOption(label="2v2", value="2"),
    discord.SelectOption(label="3v3", value="3"),
    discord.SelectOption(label="5v5", value="5"),
]


class QueueView(discord.ui.View):
    def __init__(self, cog) -> None:
        super().__init__(timeout=None)
        self._cog = cog

    @discord.ui.button(label="Solo", style=discord.ButtonStyle.primary, custom_id="join_solo_button")
    async def join_solo(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message(
            "Choisissez la taille souhaitee.",
            view=QueueSizeView(self._cog, mode="solo"),
            ephemeral=True,
        )

    @discord.ui.button(label="Equipe", style=discord.ButtonStyle.success, custom_id="join_team_button")
    async def join_team(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message(
            "Choisissez la taille souhaitee.",
            view=QueueSizeView(self._cog, mode="team"),
            ephemeral=True,
        )

    @discord.ui.button(label="Quitter", style=discord.ButtonStyle.danger, custom_id="leave_queue_button")
    async def leave_queue(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._cog.handle_leave_queue(interaction)


class QueueSizeView(discord.ui.View):
    def __init__(self, cog, *, mode: str) -> None:
        super().__init__(timeout=60)
        self.add_item(QueueSizeSelect(cog, mode=mode))


class QueueSizeSelect(discord.ui.Select):
    def __init__(self, cog, *, mode: str) -> None:
        super().__init__(
            placeholder="Taille de match",
            min_values=1,
            max_values=1,
            options=TEAM_SIZE_OPTIONS,
        )
        self._cog = cog
        self._mode = mode

    async def callback(self, interaction: discord.Interaction) -> None:
        size = int(self.values[0])
        if self._mode == "solo":
            await self._cog.handle_join_solo_queue(interaction, desired_team_size=size)
        else:
            await self._cog.handle_join_team_queue(interaction, desired_team_size=size)


class TeamPublicView(discord.ui.View):
    def __init__(self, cog, code: str) -> None:
        super().__init__(timeout=None)
        self._cog = cog
        self._code = code
        self.add_item(JoinTeamButton(cog, code))


class JoinTeamButton(discord.ui.Button):
    def __init__(self, cog, code: str) -> None:
        super().__init__(
            label="Rejoindre",
            style=discord.ButtonStyle.success,
            custom_id=f"join_team_{code}",
        )
        self._cog = cog
        self._code = code

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._cog.handle_join_team(interaction, code=self._code)
