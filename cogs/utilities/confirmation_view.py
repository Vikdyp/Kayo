import discord
from discord import TextChannel, Interaction
from discord.ui import View, Button
import logging
from typing import Optional, Callable, Any

logger = logging.getLogger('discord.utilities.confirmation_view')


class PurgeConfirmationView(View):
    """Vue pour la confirmation des actions de nettoyage."""

    def __init__(self, interaction: Interaction, target_channel: TextChannel, count: Optional[int]):
        super().__init__(timeout=30)  # Temps d'attente de 30 secondes
        self.interaction = interaction
        self.target_channel = target_channel
        self.count = count
        self.value = None  # Initialise l'attribut value

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Vérifie si l'utilisateur a le rôle requis pour interagir avec les boutons."""
        if any(role.name == "Modérateur" for role in interaction.user.roles):
            return True
        await interaction.response.send_message(
            "Vous n'avez pas la permission d'interagir avec cette commande.",
            ephemeral=True
        )
        return False

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.green)
    async def confirm(
        self,
        interaction: Interaction,
        button: discord.ui.Button
    ) -> None:
        """Confirme l'action de nettoyage."""
        self.value = True  # Marque l'action comme confirmée
        await interaction.response.defer()  # Déférer l'interaction pour éviter les délais d'attente
        self.stop()  # Arrête la vue

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.grey)
    async def cancel(
        self,
        interaction: Interaction,
        button: discord.ui.Button
    ) -> None:
        """Annule l'action de nettoyage."""
        self.value = False  # Marque l'action comme annulée
        try:
            await interaction.response.edit_message(
                content="Action annulée.",
                embed=None,
                view=None
            )
            logger.info(f"{interaction.user} a annulé l'action de nettoyage dans {self.target_channel.name}.")
        except discord.Forbidden:
            logger.warning(f"Impossible de modifier le message de confirmation dans {self.target_channel.name}.")
        except Exception as e:
            logger.exception(f"Erreur lors de l'annulation de l'action de nettoyage dans {self.target_channel.name}: {e}")
        self.stop()

    async def on_timeout(self) -> None:
        """Gère le délai d'attente de la vue."""
        self.value = None  # Marque l'expiration comme non résolue
        try:
            await self.interaction.edit_original_response(
                content="La confirmation a expiré.",
                embed=None,
                view=None
            )
            logger.info(f"Vue de confirmation expirée pour {self.target_channel.name}.")
        except discord.Forbidden:
            logger.warning(f"Impossible de modifier le message de confirmation dans {self.target_channel.name}.")
        except Exception as e:
            logger.exception(f"Erreur lors de la modification du message de confirmation dans {self.target_channel.name}: {e}")
        self.stop()


class ModerationConfirmationView(View):
    """Vue générique pour la confirmation des actions de modération."""

    def __init__(self, interaction: Interaction, callback: Callable[[Interaction], Any]):
        super().__init__(timeout=30)
        self.interaction = interaction
        self.callback = callback
        self.value: Optional[bool] = None

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: Interaction, button: discord.ui.Button):
        """Confirme l'action de modération."""
        if interaction.user.id != self.interaction.user.id:
            return await interaction.response.send_message("Vous n'êtes pas l'auteur de cette commande.", ephemeral=True)
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: Interaction, button: discord.ui.Button):
        """Annule l'action de modération."""
        if interaction.user.id != self.interaction.user.id:
            return await interaction.response.send_message("Vous n'êtes pas l'auteur de cette commande.", ephemeral=True)
        self.value = False
        await interaction.response.defer()
        self.stop()

    async def on_timeout(self) -> None:
        """Gère le délai d'attente de la vue générique de confirmation."""
        self.value = None
        try:
            await self.interaction.edit_original_response(
                content="La confirmation a expiré.",
                embed=None,
                view=None
            )
            logger.info(f"Vue de confirmation expirée pour l'utilisateur {self.interaction.user}.")
        except discord.Forbidden:
            logger.warning("Impossible de modifier le message de confirmation générique.")
        except Exception as e:
            logger.exception(f"Erreur lors de la gestion du timeout de la vue générique de confirmation: {e}")
        self.stop()
