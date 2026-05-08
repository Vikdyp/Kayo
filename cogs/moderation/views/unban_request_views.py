# cogs/moderation/views/unban_request_views.py
"""Persistent Discord views for unban request workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ui import Modal, TextInput, View

if TYPE_CHECKING:
    from cogs.moderation.unban_requests import DebanManager


class DebanManagerView(View):
    """Vue pour l'embed principal de demande de débannissement."""

    def __init__(self, cog: "DebanManager"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Demander un Déban",
        style=discord.ButtonStyle.primary,
        custom_id="deban_manager:open_form",
    )
    async def open_form_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.cog.open_deban_request_modal(interaction)


class DebanRequestModal(Modal):
    """Modal pour le formulaire de demande de débannissement."""

    def __init__(self, cog: "DebanManager", user: discord.User):
        super().__init__(title="Demande de Déban")
        self.cog = cog
        self.user = user

        self.add_item(
            TextInput(
                label="Raison de la demande",
                style=discord.TextStyle.long,
                placeholder="Expliquez pourquoi vous souhaitez être débanni.",
                required=True,
                max_length=1000,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        reason = self.children[0].value
        await interaction.response.defer(ephemeral=True)
        await self.cog.handle_deban_request_submission(interaction, self.user, reason)


class DebanRequestActionView(View):
    """Vue pour les actions des demandes individuelles."""

    def __init__(
        self,
        cog: "DebanManager",
        user_id: int,
        request_id: int,
        channel_id: int,
    ):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.request_id = request_id
        self.channel_id = channel_id

    @discord.ui.button(
        label="Accepter",
        style=discord.ButtonStyle.success,
        custom_id="deban_request:accept",
    )
    async def accept_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.cog.process_accept(interaction, self.user_id, self.request_id)

    @discord.ui.button(
        label="Refuser",
        style=discord.ButtonStyle.danger,
        custom_id="deban_request:reject",
    )
    async def reject_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self.cog.process_reject(interaction, self.user_id, self.request_id)
