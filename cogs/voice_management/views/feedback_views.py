# cogs/voice_management/views/feedback_views.py
"""
Vues Discord pour le système de feedback post-match.
"""

import logging
from typing import Optional

import discord
from discord import ButtonStyle
from discord.ui import View, Button, button

logger = logging.getLogger(__name__)


class FeedbackRatingButton(Button):
    """Bouton de notation pour le feedback."""

    def __init__(self, rating: int, label: str, style: ButtonStyle, emoji: str):
        super().__init__(
            label=label,
            style=style,
            emoji=emoji,
            custom_id=f"feedback_rating_{rating}"
        )
        self.rating = rating


class MatchFeedbackView(View):
    """
    Vue pour collecter le feedback post-match.

    Affiche 5 boutons de notation (1-5 étoiles) et permet aux joueurs
    de noter leur expérience de match.
    """

    def __init__(self, match_id: int, match_code: str):
        super().__init__(timeout=3600)  # 1 heure
        self.match_id = match_id
        self.match_code = match_code

        # Configurer les boutons de notation
        ratings = [
            (1, "Mauvais", ButtonStyle.danger, "1️⃣"),
            (2, "Passable", ButtonStyle.secondary, "2️⃣"),
            (3, "Correct", ButtonStyle.secondary, "3️⃣"),
            (4, "Bon", ButtonStyle.primary, "4️⃣"),
            (5, "Excellent", ButtonStyle.success, "5️⃣"),
        ]

        for rating, label, style, emoji in ratings:
            btn = FeedbackRatingButton(rating, label, style, emoji)
            btn.callback = self._create_callback(rating)
            self.add_item(btn)

    def _create_callback(self, rating: int):
        """Crée un callback pour un bouton de notation."""
        async def callback(interaction: discord.Interaction):
            await self._handle_rating(interaction, rating)
        return callback

    async def _handle_rating(self, interaction: discord.Interaction, rating: int):
        """Gère la soumission d'une notation."""
        # Importer ici pour éviter les imports circulaires
        from cogs.voice_management.services.five_stack_service import MatchmakingService

        # Déterminer le type de feedback
        if rating >= 4:
            feedback_type = 'positive'
        elif rating <= 2:
            feedback_type = 'negative'
        else:
            feedback_type = 'neutral'

        # Sauvegarder le feedback
        success = await MatchmakingService.save_match_feedback(
            match_id=self.match_id,
            reporter_id=interaction.user.id,
            rating=rating,
            feedback_type=feedback_type
        )

        if success:
            await interaction.response.send_message(
                f"Merci pour votre feedback ! Vous avez noté ce match **{rating}/5**.",
                ephemeral=True
            )
            # Désactiver la vue après soumission
            for item in self.children:
                item.disabled = True
            try:
                await interaction.message.edit(view=self)
            except discord.NotFound:
                pass  # Message supprimé, ignoré
            except discord.HTTPException:
                pass  # Erreur lors de l'édition, non critique
        else:
            await interaction.response.send_message(
                "Une erreur s'est produite lors de l'enregistrement de votre feedback.",
                ephemeral=True
            )

    @staticmethod
    def create_feedback_embed(match_code: str, team_size: int) -> discord.Embed:
        """
        Crée l'embed pour la demande de feedback.

        Args:
            match_code: Code du match
            team_size: Taille de l'équipe

        Returns:
            Embed Discord
        """
        embed = discord.Embed(
            title="Comment s'est passé votre match ?",
            description=(
                f"Vous avez récemment participé au match **{match_code}**.\n"
                "Votre feedback nous aide à améliorer le système de matchmaking !"
            ),
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Notation",
            value="Cliquez sur un bouton ci-dessous pour noter votre expérience.",
            inline=False
        )
        embed.set_footer(text="Ce feedback est anonyme et expire dans 1 heure.")
        return embed


class DetailedFeedbackModal(discord.ui.Modal, title="Feedback détaillé"):
    """
    Modal pour un feedback plus détaillé (optionnel).
    """

    issues = discord.ui.TextInput(
        label="Problèmes rencontrés",
        style=discord.TextStyle.paragraph,
        placeholder="Ex: Écart de niveau, communication difficile...",
        required=False,
        max_length=500
    )

    suggestions = discord.ui.TextInput(
        label="Suggestions d'amélioration",
        style=discord.TextStyle.paragraph,
        placeholder="Comment pouvons-nous améliorer votre expérience ?",
        required=False,
        max_length=500
    )

    def __init__(self, match_id: int, rating: int):
        super().__init__()
        self.match_id = match_id
        self.rating = rating

    async def on_submit(self, interaction: discord.Interaction):
        from cogs.voice_management.services.five_stack_service import MatchmakingService

        # Parser les problèmes mentionnés
        issues_list = []
        issues_text = self.issues.value.lower() if self.issues.value else ""

        if "niveau" in issues_text or "skill" in issues_text or "elo" in issues_text:
            issues_list.append("skill_gap")
        if "communication" in issues_text or "micro" in issues_text:
            issues_list.append("communication")
        if "toxique" in issues_text or "toxic" in issues_text:
            issues_list.append("toxic_player")
        if "rôle" in issues_text or "role" in issues_text:
            issues_list.append("role_mismatch")

        feedback_type = 'positive' if self.rating >= 4 else ('negative' if self.rating <= 2 else 'neutral')

        await MatchmakingService.save_match_feedback(
            match_id=self.match_id,
            reporter_id=interaction.user.id,
            rating=self.rating,
            feedback_type=feedback_type,
            issues=issues_list if issues_list else None,
            comment=self.suggestions.value if self.suggestions.value else None
        )

        await interaction.response.send_message(
            "Merci pour votre feedback détaillé !",
            ephemeral=True
        )


class FeedbackFollowUpView(View):
    """
    Vue de suivi pour demander un feedback plus détaillé après une mauvaise note.
    """

    def __init__(self, match_id: int, rating: int):
        super().__init__(timeout=300)  # 5 minutes
        self.match_id = match_id
        self.rating = rating

    @button(label="Donner plus de détails", style=ButtonStyle.secondary, emoji="📝")
    async def detail_button(self, interaction: discord.Interaction, button: Button):
        modal = DetailedFeedbackModal(self.match_id, self.rating)
        await interaction.response.send_modal(modal)

    @button(label="Non merci", style=ButtonStyle.secondary)
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            "Pas de problème, merci quand même !",
            ephemeral=True
        )
        self.stop()
