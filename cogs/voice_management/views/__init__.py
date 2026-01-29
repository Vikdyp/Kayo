# cogs/voice_management/views/__init__.py
"""
Module de vues Discord pour le système de matchmaking.

Note: Les vues queue_views et team_views restent à leur emplacement d'origine
pour éviter de casser les imports existants. Elles peuvent être importées via:
- from cogs.voice_management.queue_views import QueueView
- from cogs.voice_management.team_views import TeamForumJoinButtonView

Les nouvelles vues (feedback) sont dans ce module views/.
"""

from .feedback_views import (
    MatchFeedbackView,
    FeedbackRatingButton,
    DetailedFeedbackModal,
    FeedbackFollowUpView,
)

__all__ = [
    # Feedback views
    "MatchFeedbackView",
    "FeedbackRatingButton",
    "DetailedFeedbackModal",
    "FeedbackFollowUpView",
]
