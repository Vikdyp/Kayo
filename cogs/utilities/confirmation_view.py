# cogs/utilities/confirmation_view.py

import discord
from discord import Interaction, TextChannel
from discord.ui import View, Button
import logging
from typing import Optional

from .utils import load_json, save_json

logger = logging.getLogger('discord.utilities.confirmation_view')


class ConfirmationView(discord.ui.View):
    """Vue pour la confirmation des actions de nettoyage."""

    def __init__(self, interaction: discord.Interaction, target_channel: discord.TextChannel, count: Optional[int]):
        super().__init__(timeout=30)  # Temps d'attente de 30 secondes
        self.interaction = interaction
        self.target_channel = target_channel
        self.count = count

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Vérifie si l'utilisateur a le rôle requis pour interagir avec les boutons."""
        if any(role.name == "Admin" for role in interaction.user.roles):
            return True
        await interaction.response.send_message(
            "Vous n'avez pas la permission d'interagir avec cette commande.",
            ephemeral=True
        )
        return False

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.green)
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ) -> None:
        """Confirme l'action de nettoyage."""
        if self.count is None:
            # Nettoyage complet du salon
            try:
                deleted = await self.target_channel.purge(limit=None)
                await interaction.response.send_message(
                    f"Tous les messages dans {self.target_channel.mention} ont été supprimés.",
                    ephemeral=True
                )
                logger.info(f"{interaction.user} a nettoyé tous les messages dans {self.target_channel.name}.")
            except discord.Forbidden:
                await interaction.response.send_message(
                    "Le bot n'a pas les permissions nécessaires pour supprimer les messages.",
                    ephemeral=True
                )
                logger.error(f"Permission refusée pour nettoyer {self.target_channel.name}.")
            except Exception as e:
                await interaction.response.send_message(
                    "Une erreur est survenue lors de la suppression des messages.",
                    ephemeral=True
                )
                logger.exception(f"Erreur lors du nettoyage de {self.target_channel.name}: {e}")
        else:
            # Nettoyage d'un nombre spécifique de messages
            try:
                deleted = await self.target_channel.purge(limit=self.count + 1)  # +1 pour inclure la commande de nettoyage
                await interaction.response.send_message(
                    f"{len(deleted) - 1} messages dans {self.target_channel.mention} ont été supprimés.",
                    ephemeral=True
                )
                logger.info(f"{interaction.user} a nettoyé {len(deleted) - 1} messages dans {self.target_channel.name}.")
            except discord.Forbidden:
                await interaction.response.send_message(
                    "Le bot n'a pas les permissions nécessaires pour supprimer les messages.",
                    ephemeral=True
                )
                logger.error(f"Permission refusée pour nettoyer {self.target_channel.name}.")
            except discord.HTTPException as e:
                await interaction.response.send_message(
                    "Une erreur est survenue lors de la suppression des messages.",
                    ephemeral=True
                )
                logger.exception(f"Erreur HTTP lors du nettoyage de {self.target_channel.name}: {e}")
            except Exception as e:
                await interaction.response.send_message(
                    "Une erreur est survenue lors de la suppression des messages.",
                    ephemeral=True
                )
                logger.exception(f"Erreur lors du nettoyage de {self.target_channel.name}: {e}")
        self.stop()

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.grey)
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ) -> None:
        """Annule l'action de nettoyage."""
        try:
            await interaction.response.send_message("Action annulée.", ephemeral=True)
            await interaction.message.delete()
            logger.info(f"{interaction.user} a annulé l'action de nettoyage dans {self.target_channel.name}.")
        except discord.Forbidden:
            logger.warning(f"Impossible de supprimer le message de confirmation dans {self.target_channel.name}.")
        except Exception as e:
            logger.exception(f"Erreur lors de l'annulation de l'action de nettoyage dans {self.target_channel.name}: {e}")
        self.stop()

    async def on_timeout(self) -> None:
        """Gère le délai d'attente de la vue."""
        try:
            await self.interaction.delete_original_response()
            logger.info(f"Vue de confirmation expirée pour {self.target_channel.name}.")
        except discord.Forbidden:
            logger.warning(f"Impossible de supprimer le message de confirmation dans {self.target_channel.name}.")
        except Exception as e:
            logger.exception(f"Erreur lors de la suppression du message de confirmation dans {self.target_channel.name}: {e}")
        self.stop()