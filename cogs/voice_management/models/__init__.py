# cogs/voice_management/models/__init__.py
"""
Modèles de données pour le système de matchmaking.
"""

from .queue_entry import QueueEntry
from .match_candidate import MatchCandidate
from .player_stats import PlayerStats

__all__ = [
    "QueueEntry",
    "MatchCandidate",
    "PlayerStats",
]
