# cogs/moderation/views/confirmation_view.py
"""Vue de confirmation avec boutons Confirmer/Annuler."""

import discord
from typing import Any, Callable, Optional


class ConfirmationView(discord.ui.View):
    """Vue de confirmation avec boutons Confirmer/Annuler."""

    def __init__(
        self,
        interaction: discord.Interaction,
        callback: Callable[[Optional[bool]], Any],
        confirm_label: str = "Confirmer",
        confirm_style: discord.ButtonStyle = discord.ButtonStyle.green,
        cancel_label: str = "Annuler",
        cancel_style: discord.ButtonStyle = discord.ButtonStyle.grey,
        is_ephemeral: bool = False,
        timeout: float = 60.0,
    ):
        super().__init__(timeout=timeout)
        self.original_interaction = interaction
        self.callback = callback
        self.value: Optional[bool] = None
        self.is_ephemeral = is_ephemeral
        self.message: Optional[discord.Message] = None

        # Configurer les boutons dynamiquement
        self.confirm_button.label = confirm_label
        self.confirm_button.style = confirm_style
        self.cancel_button.label = cancel_label
        self.cancel_button.style = cancel_style

    async def _disable_buttons(self, interaction: discord.Interaction) -> None:
        """Désactive tous les boutons après une action."""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(view=self)

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.green)
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.value = True
        await self._disable_buttons(interaction)
        await self.callback(True)
        self.stop()

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.grey)
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.value = False
        await self._disable_buttons(interaction)
        await self.callback(False)
        self.stop()

    async def on_timeout(self):
        self.value = None
        # Désactiver les boutons sur timeout si possible
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await self.callback(None)
