# cogs/utilities/views.py

import discord
from discord import Interaction
from discord.ui import View, Button
import logging
from typing import List, Dict, Any

logger = logging.getLogger('discord.utilities.views')

class VoteView(View):
    """Vue pour permettre aux joueurs de voter pour l'heure des scrims."""

    def __init__(self, scrim_registration, rank: str, list_index: int):
        super().__init__(timeout=180)  # Timeout de 3 minutes
        self.scrim_registration = scrim_registration
        self.rank = rank
        self.list_index = list_index

    @discord.ui.button(label="18:00", style=discord.ButtonStyle.primary, custom_id="vote_18")
    async def vote_18(self, interaction: Interaction, button: Button):
        await self.scrim_registration.on_vote(interaction, self.rank, self.list_index, 18)
        self.stop()

    @discord.ui.button(label="19:00", style=discord.ButtonStyle.primary, custom_id="vote_19")
    async def vote_19(self, interaction: Interaction, button: Button):
        await self.scrim_registration.on_vote(interaction, self.rank, self.list_index, 19)
        self.stop()

    @discord.ui.button(label="20:00", style=discord.ButtonStyle.primary, custom_id="vote_20")
    async def vote_20(self, interaction: Interaction, button: Button):
        await self.scrim_registration.on_vote(interaction, self.rank, self.list_index, 20)
        self.stop()

class ResultView(View):
    """Vue pour afficher les résultats des scrims et proposer des actions."""

    def __init__(self, scrim_registration, rank: str, list_index: int, team_1: List[Dict[str, Any]], team_2: List[Dict[str, Any]], channel_1_id: int, channel_2_id: int):
        super().__init__(timeout=None)  # Pas de timeout
        self.scrim_registration = scrim_registration
        self.rank = rank
        self.list_index = list_index
        self.team_1 = team_1
        self.team_2 = team_2
        self.channel_1_id = channel_1_id
        self.channel_2_id = channel_2_id

    @discord.ui.button(label="Terminer Scrim", style=discord.ButtonStyle.success, custom_id="finish_scrim")
    async def finish_scrim(self, interaction: Interaction, button: Button):
        """Bouton pour terminer le scrim et enregistrer les résultats."""
        await self.finish_scrim_action(interaction)
        self.stop()

    async def finish_scrim_action(self, interaction: discord.Interaction):
        """Action à exécuter lors de la terminaison du scrim."""
        # Implémentez la logique pour terminer le scrim, enregistrer les résultats, etc.
        await interaction.response.send_message("Scrim terminé et salons supprimés.", ephemeral=True)
        logger.info(f"Scrim terminé pour {self.rank} - Liste {self.list_index + 1}.")
        # Supprimer les salons
        channel_1 = self.scrim_registration.bot.get_channel(self.channel_1_id)
        channel_2 = self.scrim_registration.bot.get_channel(self.channel_2_id)
        if channel_1:
            try:
                await channel_1.delete()
                logger.info(f"Salon vocal {channel_1.name} supprimé.")
            except discord.Forbidden:
                logger.error(f"Permission refusée pour supprimer le salon vocal {channel_1.name}.")
            except discord.HTTPException as e:
                logger.error(f"Erreur HTTP lors de la suppression du salon vocal {channel_1.name}: {e}")
        if channel_2:
            try:
                await channel_2.delete()
                logger.info(f"Salon vocal {channel_2.name} supprimé.")
            except discord.Forbidden:
                logger.error(f"Permission refusée pour supprimer le salon vocal {channel_2.name}.")
            except discord.HTTPException as e:
                logger.error(f"Erreur HTTP lors de la suppression du salon vocal {channel_2.name}: {e}")

class ScrimsPreparationView(View):
    """Vue pour préparer les scrims après l'inscription."""

    def __init__(self, scrim_registration, rank: str, list_index: int):
        super().__init__(timeout=180)  # Timeout de 3 minutes
        self.scrim_registration = scrim_registration
        self.rank = rank
        self.list_index = list_index

    @discord.ui.button(label="Valider Présence", style=discord.ButtonStyle.green, custom_id="validate_presence")
    async def validate_presence(self, interaction: Interaction, button: Button):
        """Bouton pour valider la présence d'un joueur."""
        # Implémentez la logique pour valider la présence
        await interaction.response.send_message("Présence validée.", ephemeral=True)
        logger.info(f"{interaction.user} a validé sa présence pour {self.rank} - Liste {self.list_index + 1}.")
