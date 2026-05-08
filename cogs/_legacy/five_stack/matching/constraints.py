# cogs/voice_management/matching/constraints.py
"""
Gestion des contraintes de matching et relaxation progressive.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Seuil ELO par défaut
DEFAULT_ELO_THRESHOLD = 300


@dataclass
class MatchConstraints:
    """
    Contraintes pour la formation d'un match.
    Ces contraintes peuvent être relaxées au fil du temps.
    """
    elo_threshold: int = DEFAULT_ELO_THRESHOLD
    allow_role_duplicates: bool = False
    any_team_size: bool = False
    min_role_diversity: int = 2
    require_mmr_extended_for_large_gap: bool = True

    def validate_elo(self, elos: List[int], all_mmr_extended: bool) -> Tuple[bool, str]:
        """
        Vérifie si les ELOs respectent les contraintes.

        Returns:
            (is_valid, reason)
        """
        if not elos or len(elos) < 2:
            return True, "OK"

        spread = max(elos) - min(elos)

        if spread <= self.elo_threshold:
            return True, "OK"

        if self.require_mmr_extended_for_large_gap and all_mmr_extended:
            return True, "OK (mmr_extended)"

        return False, f"ELO spread {spread} > threshold {self.elo_threshold}"

    def validate_roles(self, roles: List[str], team_size: int) -> Tuple[bool, str]:
        """
        Vérifie si les rôles respectent les contraintes de diversité.

        Returns:
            (is_valid, reason)
        """
        if self.allow_role_duplicates:
            return True, "OK (duplicates allowed)"

        meaningful_roles = [r for r in roles if r.lower() != 'fill']
        unique_roles = len(set(meaningful_roles))

        if unique_roles >= self.min_role_diversity:
            return True, "OK"

        # Pour les petites équipes, être plus permissif
        if team_size <= 3 and unique_roles >= 1:
            return True, "OK (small team)"

        # On autorise quand même le match, mais on log un avertissement
        logger.warning(
            f"Faible diversité de rôles: {unique_roles} unique(s) sur {len(roles)} total"
        )
        return True, "OK (low diversity warning)"

    def is_team_size_compatible(self, desired_size: int, actual_count: int) -> bool:
        """Vérifie si la taille d'équipe est compatible."""
        if self.any_team_size:
            return actual_count in [2, 3, 5]
        return desired_size == actual_count


class QueueTimeoutManager:
    """
    Gère la relaxation progressive des contraintes en fonction du temps d'attente.

    Les seuils par défaut:
    - 3 min: ELO threshold +50
    - 5 min: ELO threshold +100
    - 7 min: Autoriser les doublons de rôles
    - 10 min: Accepter n'importe quelle taille d'équipe compatible
    """

    # (seconds, constraint_overrides)
    DEFAULT_THRESHOLDS: List[Tuple[int, Dict]] = [
        (180, {'elo_threshold': 350}),           # 3 min
        (300, {'elo_threshold': 400}),           # 5 min
        (420, {'allow_role_duplicates': True}),  # 7 min
        (600, {'any_team_size': True}),          # 10 min
    ]

    def __init__(self, thresholds: Optional[List[Tuple[int, Dict]]] = None):
        """
        Initialise le manager avec des seuils personnalisés ou par défaut.

        Args:
            thresholds: Liste de (seconds, overrides) triée par secondes croissantes
        """
        self.thresholds = thresholds or self.DEFAULT_THRESHOLDS

    def get_relaxed_constraints(
        self,
        wait_seconds: float,
        base_constraints: Optional[MatchConstraints] = None
    ) -> MatchConstraints:
        """
        Retourne les contraintes relaxées en fonction du temps d'attente.

        Args:
            wait_seconds: Temps d'attente en secondes
            base_constraints: Contraintes de base (par défaut: MatchConstraints())

        Returns:
            MatchConstraints avec les relaxations appliquées
        """
        if base_constraints is None:
            base_constraints = MatchConstraints()

        # Créer une copie des contraintes de base
        relaxed = MatchConstraints(
            elo_threshold=base_constraints.elo_threshold,
            allow_role_duplicates=base_constraints.allow_role_duplicates,
            any_team_size=base_constraints.any_team_size,
            min_role_diversity=base_constraints.min_role_diversity,
            require_mmr_extended_for_large_gap=base_constraints.require_mmr_extended_for_large_gap
        )

        # Appliquer les relaxations progressives
        for threshold_seconds, overrides in self.thresholds:
            if wait_seconds >= threshold_seconds:
                for key, value in overrides.items():
                    if hasattr(relaxed, key):
                        setattr(relaxed, key, value)

        return relaxed

    def get_max_wait_time(self, timestamps: List[datetime]) -> float:
        """
        Retourne le temps d'attente maximum parmi une liste de timestamps.

        Args:
            timestamps: Liste des timestamps d'entrée en queue

        Returns:
            Temps d'attente maximum en secondes
        """
        if not timestamps:
            return 0.0

        now = datetime.now(timezone.utc)
        max_wait = 0.0

        for ts in timestamps:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            wait = (now - ts).total_seconds()
            if wait > max_wait:
                max_wait = wait

        return max_wait

    def should_force_match(
        self,
        timestamps: List[datetime],
        force_threshold_seconds: int = 600
    ) -> bool:
        """
        Détermine si on doit forcer un match à cause d'un temps d'attente trop long.

        Args:
            timestamps: Timestamps des entrées
            force_threshold_seconds: Seuil pour forcer le match

        Returns:
            True si on doit forcer le match
        """
        max_wait = self.get_max_wait_time(timestamps)
        return max_wait >= force_threshold_seconds

    def get_current_relaxation_level(self, wait_seconds: float) -> int:
        """
        Retourne le niveau de relaxation actuel (0 = aucune relaxation).

        Args:
            wait_seconds: Temps d'attente en secondes

        Returns:
            Niveau de relaxation (0 à len(thresholds))
        """
        level = 0
        for threshold_seconds, _ in self.thresholds:
            if wait_seconds >= threshold_seconds:
                level += 1
        return level
