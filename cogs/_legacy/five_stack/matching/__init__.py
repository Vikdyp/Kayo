# cogs/voice_management/matching/__init__.py
"""
Module de matching amélioré pour le système de matchmaking Valorant.

Ce module contient:
- quality.py: Calcul des scores de qualité pour les matchs
- constraints.py: Gestion des contraintes et relaxation progressive
- algorithm.py: Algorithme de matching optimisé
"""

from .quality import MatchQualityCalculator
from .constraints import QueueTimeoutManager, MatchConstraints
from .algorithm import OptimizedMatcher, MatchCandidate

__all__ = [
    "MatchQualityCalculator",
    "QueueTimeoutManager",
    "MatchConstraints",
    "OptimizedMatcher",
    "MatchCandidate",
]
