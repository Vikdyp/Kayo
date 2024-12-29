# cogs/utilities/confirmation_view.py
import discord
from discord import Interaction
from discord.ui import View, Button
from typing import Optional, Callable, Any
import logging

logger = logging.getLogger('discord.utilities.confirmation_view')


class ConfirmationView(View):
    """Vue générique pour la confirmation des actions avec modification du message après interaction."""

    def __init__(
        self, 
        interaction: Interaction, 
        callback: Callable[[Optional[bool]], Any],
        timeout: int = 30,
        confirm_label: str = "Confirmer",
        confirm_style: discord.ButtonStyle = discord.ButtonStyle.green,
        cancel_label: str = "Annuler",
        cancel_style: discord.ButtonStyle = discord.ButtonStyle.grey,
        is_ephemeral: bool = False  # Indique si le message est éphémère
    ):
        super().__init__(timeout=timeout)
        self.interaction = interaction
        self.callback = callback
        self.value: Optional[bool] = None
        self.confirm_label = confirm_label
        self.confirm_style = confirm_style
        self.cancel_label = cancel_label
        self.cancel_style = cancel_style
        self.is_ephemeral = is_ephemeral
        self.handled = False  # Flag pour éviter les doubles traitements

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: Interaction, button: discord.ui.Button):
        """Confirme l'action et modifie le message de confirmation."""
        if interaction.user.id != self.interaction.user.id:
            return await interaction.response.send_message(
                "Vous n'êtes pas l'auteur de cette commande.",
                ephemeral=True
            )
        
        if self.handled:
            return  # Éviter les traitements multiples

        self.value = True
        self.handled = True
        self.stop()
        
        # Modifier le message pour indiquer la confirmation
        try:
            if self.is_ephemeral:
                await interaction.response.edit_message(
                    content="Action confirmée.",
                    view=None  # Retire les boutons
                )
            else:
                await interaction.message.delete()
        except discord.NotFound:
            logger.warning("Le message est introuvable ou a déjà été supprimé.")
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la modification du message : {e}")
        
        # Appeler le callback après avoir modifié le message
        await self.callback(self.value)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: Interaction, button: discord.ui.Button):
        """Annule l'action et modifie le message de confirmation."""
        if interaction.user.id != self.interaction.user.id:
            return await interaction.response.send_message(
                "Vous n'êtes pas l'auteur de cette commande.",
                ephemeral=True
            )
        
        if self.handled:
            return  # Éviter les traitements multiples

        self.value = False
        self.handled = True
        self.stop()
        
        # Modifier le message pour indiquer l'annulation
        try:
            if self.is_ephemeral:
                await interaction.response.edit_message(
                    content="Action annulée.",
                    view=None  # Retire les boutons
                )
            else:
                await interaction.message.delete()
        except discord.NotFound:
            logger.warning("Le message est introuvable ou a déjà été supprimé.")
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la modification du message : {e}")
        
        # Appeler le callback après avoir modifié le message
        await self.callback(self.value)

    async def on_timeout(self) -> None:
        """Modifie le message pour indiquer l'expiration et retire les boutons."""
        if self.handled:
            return  # Éviter les traitements multiples

        self.value = None
        self.handled = True
        try:
            if self.is_ephemeral:
                await self.interaction.edit_original_response(
                    content="La confirmation a expiré.",
                    embed=None,
                    view=None  # Retire les boutons
                )
            else:
                await self.interaction.message.edit(
                    content="La confirmation a expiré.",
                    embed=None,
                    view=None  # Retire les boutons
                )
            logger.info(f"Vue de confirmation expirée pour l'utilisateur {self.interaction.user}.")
        except discord.Forbidden:
            logger.warning("Impossible de modifier le message de confirmation générique.")
        except discord.NotFound:
            logger.warning("Le message d'origine est introuvable ou déjà supprimé.")
        except Exception as e:
            logger.exception(f"Erreur lors de la gestion du timeout de la vue générique de confirmation: {e}")
        await self.callback(self.value)
