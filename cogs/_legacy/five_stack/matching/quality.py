# cogs/voice_management/matching/quality.py
"""
Calcul des scores de qualité pour les matchs.
"""

from datetime import datetime, timezone
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Seuil ELO par défaut (peut être relaxé)
DEFAULT_ELO_THRESHOLD = 300


class MatchQualityCalculator:
    """
    Calcule les scores de qualité pour les combinaisons de joueurs candidates.

    Les poids par défaut sont:
    - elo_spread (35%): Un écart ELO faible donne un meilleur score
    - role_diversity (25%): Plus de rôles uniques = meilleur score
    - wait_time (25%): Les joueurs qui attendent depuis longtemps sont prioritaires
    - preference_match (15%): Bonus pour les coéquipiers préférés (futur)
    """

    WEIGHTS = {
        'elo_spread': 0.35,
        'role_diversity': 0.25,
        'wait_time': 0.25,
        'preference_match': 0.15
    }

    MAX_ELO_SPREAD = DEFAULT_ELO_THRESHOLD
    MAX_WAIT_TIME_SECONDS = 600  # 10 minutes pour score max

    @classmethod
    def calculate_elo_score(cls, elos: List[int], threshold: int = DEFAULT_ELO_THRESHOLD) -> float:
        """
        Calcule un score de 0.0 à 1.0 basé sur l'écart ELO.

        Args:
            elos: Liste des ELO des joueurs
            threshold: Seuil ELO maximum acceptable

        Returns:
            Score de 0.0 (mauvais) à 1.0 (parfait)
        """
        if not elos or len(elos) < 2:
            return 1.0  # Un seul joueur = pas d'écart

        spread = max(elos) - min(elos)
        if spread == 0:
            return 1.0

        # Score linéaire inversé: 0 spread = 1.0, threshold spread = 0.0
        score = max(0.0, 1.0 - (spread / threshold))
        return score

    @classmethod
    def calculate_role_diversity_score(
        cls,
        roles: List[str],
        team_size: int,
        required_unique: int = 3
    ) -> float:
        """
        Calcule un score basé sur la diversité des rôles.

        Args:
            roles: Liste des rôles de tous les joueurs
            team_size: Taille de l'équipe cible
            required_unique: Nombre minimum de rôles uniques souhaités

        Returns:
            Score de 0.0 à 1.0
        """
        if not roles:
            return 0.0

        # Exclure "fill" du calcul de diversité
        meaningful_roles = [r for r in roles if r.lower() != 'fill']
        unique_roles = len(set(meaningful_roles))

        if team_size == 0:
            return 0.5  # Taille "any" = score neutre

        # Pour une équipe de 5, on veut idéalement 4 rôles uniques
        ideal_unique = min(team_size, 4)

        if unique_roles >= ideal_unique:
            return 1.0
        elif unique_roles >= required_unique:
            return 0.75
        elif unique_roles >= 2:
            return 0.5
        else:
            return 0.25

    @classmethod
    def calculate_wait_time_score(
        cls,
        timestamps: List[datetime],
        now: Optional[datetime] = None
    ) -> float:
        """
        Calcule un score de priorité basé sur le temps d'attente.
        Les joueurs qui attendent depuis longtemps ont un score plus élevé.

        Args:
            timestamps: Liste des timestamps d'entrée en queue
            now: Moment actuel (par défaut: maintenant)

        Returns:
            Score de 0.0 à 1.0
        """
        if not timestamps:
            return 0.0

        if now is None:
            now = datetime.now(timezone.utc)

        total_wait = 0.0
        for ts in timestamps:
            # Gérer les timestamps naïfs
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            wait_seconds = (now - ts).total_seconds()
            total_wait += max(0, wait_seconds)

        avg_wait = total_wait / len(timestamps)

        # Score basé sur le temps d'attente moyen
        # 0s = 0.0, MAX_WAIT_TIME_SECONDS = 1.0
        return min(1.0, avg_wait / cls.MAX_WAIT_TIME_SECONDS)

    @classmethod
    def calculate_preference_score(cls, player_ids: List[int], preferences: Dict) -> float:
        """
        Calcule un bonus basé sur les préférences de coéquipiers.

        Args:
            player_ids: IDs des joueurs dans le match potentiel
            preferences: Dict de préférences {user_id: {'preferred': [...], 'avoided': [...]}}

        Returns:
            Score de 0.0 à 1.0 (0.5 = neutre)
        """
        if not preferences:
            return 0.5  # Score neutre si pas de préférences

        score = 0.5
        player_set = set(player_ids)

        for player_id in player_ids:
            if player_id not in preferences:
                continue

            prefs = preferences[player_id]
            preferred = set(prefs.get('preferred', []))
            avoided = set(prefs.get('avoided', []))

            # Bonus pour coéquipiers préférés présents
            preferred_present = len(player_set & preferred)
            if preferred_present > 0:
                score += 0.1 * preferred_present

            # Malus pour joueurs évités présents
            avoided_present = len(player_set & avoided)
            if avoided_present > 0:
                score -= 0.2 * avoided_present

        return max(0.0, min(1.0, score))

    @classmethod
    def calculate_total_score(
        cls,
        elos: List[int],
        roles: List[str],
        timestamps: List[datetime],
        team_size: int,
        player_ids: Optional[List[int]] = None,
        preferences: Optional[Dict] = None,
        elo_threshold: int = DEFAULT_ELO_THRESHOLD,
        weights: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Calcule le score total pondéré pour un match candidat.

        Args:
            elos: Liste des ELO des joueurs
            roles: Liste des rôles des joueurs
            timestamps: Liste des timestamps d'entrée
            team_size: Taille cible de l'équipe
            player_ids: IDs des joueurs (pour les préférences)
            preferences: Préférences de coéquipiers
            elo_threshold: Seuil ELO à utiliser
            weights: Poids personnalisés (optionnel)

        Returns:
            Score total de 0.0 à 1.0
        """
        if weights is None:
            weights = cls.WEIGHTS

        scores = {
            'elo_spread': cls.calculate_elo_score(elos, elo_threshold),
            'role_diversity': cls.calculate_role_diversity_score(roles, team_size),
            'wait_time': cls.calculate_wait_time_score(timestamps),
            'preference_match': cls.calculate_preference_score(
                player_ids or [],
                preferences or {}
            )
        }

        total = sum(scores[k] * weights.get(k, 0) for k in scores)

        logger.debug(
            f"Quality scores: elo={scores['elo_spread']:.2f}, "
            f"roles={scores['role_diversity']:.2f}, "
            f"wait={scores['wait_time']:.2f}, "
            f"prefs={scores['preference_match']:.2f} -> total={total:.2f}"
        )

        return total

    @classmethod
    def get_elo_spread(cls, elos: List[int]) -> int:
        """Retourne l'écart entre ELO max et min."""
        if not elos or len(elos) < 2:
            return 0
        return max(elos) - min(elos)

    @classmethod
    def get_avg_elo(cls, elos: List[int]) -> int:
        """Retourne l'ELO moyen."""
        if not elos:
            return 0
        return sum(elos) // len(elos)
