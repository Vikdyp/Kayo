# cogs/voice_management/matching/algorithm.py
"""
Algorithme de matching optimisé pour le système de matchmaking Valorant.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations
from typing import List, Dict, Optional, Tuple, Generator
import logging

from .quality import MatchQualityCalculator
from .constraints import MatchConstraints, QueueTimeoutManager

logger = logging.getLogger(__name__)


@dataclass
class MatchCandidate:
    """
    Représente un match candidat avec ses métriques.
    """
    blocks: List[Dict] = field(default_factory=list)
    player_ids: List[int] = field(default_factory=list)
    elos: List[int] = field(default_factory=list)
    roles: List[str] = field(default_factory=list)
    timestamps: List[datetime] = field(default_factory=list)
    team_size: int = 0
    total_entry_type: int = 0
    quality_score: float = 0.0
    elo_spread: int = 0
    avg_elo: int = 0
    all_mmr_extended: bool = False

    @classmethod
    def from_blocks(cls, blocks: List[Dict], team_size: int) -> 'MatchCandidate':
        """
        Crée un MatchCandidate à partir d'une liste de blocs de queue.

        Args:
            blocks: Liste des blocs (entrées de queue)
            team_size: Taille d'équipe cible
        """
        candidate = cls(team_size=team_size)
        candidate.blocks = blocks

        for block in blocks:
            candidate.total_entry_type += block.get('entry_type', 1)

            # Récupérer les IDs des joueurs
            team_member_ids = block.get('team_member_ids')
            if team_member_ids:
                candidate.player_ids.extend(team_member_ids)
            else:
                candidate.player_ids.append(block['discord_member_id'])

            # Récupérer ELO
            if block.get('elo') is not None:
                candidate.elos.append(block['elo'])

            # Récupérer rôles
            candidate.roles.extend(block.get('roles', []))

            # Récupérer timestamp
            ts = block.get('timestamp')
            if ts:
                candidate.timestamps.append(ts)

        # Dédupliquer les player_ids
        candidate.player_ids = list(set(candidate.player_ids))

        # Calculer les métriques
        if candidate.elos:
            candidate.elo_spread = max(candidate.elos) - min(candidate.elos)
            candidate.avg_elo = sum(candidate.elos) // len(candidate.elos)

        # Vérifier mmr_extended
        candidate.all_mmr_extended = all(
            b.get('mmr_extended', False) for b in blocks
        )

        return candidate

    def calculate_quality(
        self,
        constraints: MatchConstraints,
        preferences: Optional[Dict] = None
    ) -> float:
        """
        Calcule et stocke le score de qualité.

        Args:
            constraints: Contraintes actuelles
            preferences: Préférences de coéquipiers

        Returns:
            Score de qualité
        """
        self.quality_score = MatchQualityCalculator.calculate_total_score(
            elos=self.elos,
            roles=self.roles,
            timestamps=self.timestamps,
            team_size=self.team_size,
            player_ids=self.player_ids,
            preferences=preferences,
            elo_threshold=constraints.elo_threshold
        )
        return self.quality_score

    def is_valid(self, constraints: MatchConstraints) -> Tuple[bool, str]:
        """
        Vérifie si le candidat respecte les contraintes.

        Returns:
            (is_valid, reason)
        """
        # Vérifier la taille
        if self.total_entry_type != self.team_size:
            return False, f"Size mismatch: {self.total_entry_type} != {self.team_size}"

        # Vérifier ELO
        elo_valid, elo_reason = constraints.validate_elo(
            self.elos,
            self.all_mmr_extended
        )
        if not elo_valid:
            return False, elo_reason

        # Vérifier rôles
        roles_valid, roles_reason = constraints.validate_roles(
            self.roles,
            self.team_size
        )
        if not roles_valid:
            return False, roles_reason

        return True, "OK"


class OptimizedMatcher:
    """
    Algorithme de matching optimisé qui:
    1. Génère les combinaisons valides de blocs
    2. Score chaque combinaison
    3. Sélectionne la meilleure combinaison
    4. Applique une relaxation progressive des contraintes si nécessaire
    """

    def __init__(
        self,
        min_quality_threshold: float = 0.3,
        timeout_manager: Optional[QueueTimeoutManager] = None
    ):
        """
        Args:
            min_quality_threshold: Score minimum pour accepter un match
            timeout_manager: Manager pour la relaxation des contraintes
        """
        self.min_quality_threshold = min_quality_threshold
        self.timeout_manager = timeout_manager or QueueTimeoutManager()

    def find_best_match(
        self,
        blocks: List[Dict],
        desired_size: int,
        preferences: Optional[Dict] = None,
        force_match_if_long_wait: bool = True
    ) -> Optional[MatchCandidate]:
        """
        Trouve la meilleure combinaison de blocs pour former un match.

        Args:
            blocks: Liste des blocs (entrées de queue)
            desired_size: Taille d'équipe cible (2, 3 ou 5)
            preferences: Préférences de coéquipiers
            force_match_if_long_wait: Forcer un match si attente trop longue

        Returns:
            Le meilleur MatchCandidate ou None si aucun match valide
        """
        if desired_size not in [2, 3, 5]:
            logger.warning(f"Invalid desired_size: {desired_size}")
            return None

        if not blocks:
            return None

        # Calculer le temps d'attente max pour déterminer les contraintes
        all_timestamps = []
        for block in blocks:
            ts = block.get('timestamp')
            if ts:
                all_timestamps.append(ts)

        max_wait = self.timeout_manager.get_max_wait_time(all_timestamps)

        # Obtenir les contraintes relaxées selon le temps d'attente
        constraints = self.timeout_manager.get_relaxed_constraints(max_wait)

        # Générer les candidats valides
        candidates = list(self._generate_candidates(blocks, desired_size, constraints))

        if not candidates:
            logger.debug(f"No valid candidates for size {desired_size}")
            return None

        # Calculer les scores de qualité
        for candidate in candidates:
            candidate.calculate_quality(constraints, preferences)

        # Trier par score décroissant
        candidates.sort(key=lambda c: c.quality_score, reverse=True)

        # Sélectionner le meilleur match
        best = candidates[0]

        # Vérifier le seuil de qualité (sauf si on force à cause de l'attente)
        if best.quality_score < self.min_quality_threshold:
            if force_match_if_long_wait and self.timeout_manager.should_force_match(all_timestamps):
                logger.info(
                    f"Forcing match due to long wait time (score={best.quality_score:.2f})"
                )
                return best
            else:
                logger.debug(
                    f"Best candidate quality {best.quality_score:.2f} "
                    f"below threshold {self.min_quality_threshold}"
                )
                return None

        logger.info(
            f"Best match found: {len(best.blocks)} blocks, "
            f"quality={best.quality_score:.2f}, "
            f"elo_spread={best.elo_spread}, "
            f"players={len(best.player_ids)}"
        )

        return best

    def _generate_candidates(
        self,
        blocks: List[Dict],
        desired_size: int,
        constraints: MatchConstraints
    ) -> Generator[MatchCandidate, None, None]:
        """
        Génère toutes les combinaisons valides de blocs.

        Cette méthode utilise une approche optimisée:
        1. Filtrer les blocs trop gros
        2. Utiliser un algorithme de backtracking pour trouver les combinaisons

        Yields:
            MatchCandidate pour chaque combinaison valide
        """
        # Filtrer les blocs qui peuvent faire partie d'un match de cette taille
        valid_blocks = [
            b for b in blocks
            if b.get('entry_type', 1) <= desired_size
        ]

        if not valid_blocks:
            return

        # Approche gloutonne optimisée avec backtracking
        for candidate in self._find_combinations_greedy(valid_blocks, desired_size, constraints):
            yield candidate

    def _find_combinations_greedy(
        self,
        blocks: List[Dict],
        target_sum: int,
        constraints: MatchConstraints
    ) -> Generator[MatchCandidate, None, None]:
        """
        Trouve les combinaisons de blocs dont la somme des entry_type égale target_sum.
        Utilise une approche de type "subset sum" avec élagage.

        Yields:
            MatchCandidate pour chaque combinaison valide
        """
        # Trier par entry_type décroissant pour une meilleure élagage
        sorted_blocks = sorted(blocks, key=lambda b: b.get('entry_type', 1), reverse=True)

        def backtrack(index: int, current_blocks: List[Dict], current_sum: int):
            """Générateur récursif pour le backtracking."""
            if current_sum == target_sum:
                candidate = MatchCandidate.from_blocks(current_blocks, target_sum)
                is_valid, _ = candidate.is_valid(constraints)
                if is_valid:
                    yield candidate
                return

            if current_sum > target_sum:
                return

            if index >= len(sorted_blocks):
                return

            # Élagage: si même en prenant tous les blocs restants on ne peut pas atteindre target_sum
            remaining_sum = sum(b.get('entry_type', 1) for b in sorted_blocks[index:])
            if current_sum + remaining_sum < target_sum:
                return

            for i in range(index, len(sorted_blocks)):
                block = sorted_blocks[i]
                entry_type = block.get('entry_type', 1)

                if current_sum + entry_type <= target_sum:
                    yield from backtrack(
                        i + 1,
                        current_blocks + [block],
                        current_sum + entry_type
                    )

        yield from backtrack(0, [], 0)

    def find_multiple_matches(
        self,
        blocks: List[Dict],
        desired_sizes: List[int] = None,
        max_matches: int = 5,
        preferences: Optional[Dict] = None
    ) -> List[MatchCandidate]:
        """
        Trouve plusieurs matchs possibles, en évitant de réutiliser les mêmes blocs.

        Args:
            blocks: Liste des blocs
            desired_sizes: Tailles à essayer (par défaut: [5, 3, 2])
            max_matches: Nombre maximum de matchs à former
            preferences: Préférences de coéquipiers

        Returns:
            Liste de MatchCandidate formés
        """
        if desired_sizes is None:
            desired_sizes = [5, 3, 2]

        matches = []
        remaining_blocks = list(blocks)
        used_block_ids = set()

        for _ in range(max_matches):
            best_match = None

            for size in desired_sizes:
                # Filtrer les blocs déjà utilisés
                available = [
                    b for b in remaining_blocks
                    if b.get('id') not in used_block_ids
                ]

                if not available:
                    break

                match = self.find_best_match(available, size, preferences)
                if match is not None:
                    if best_match is None or match.quality_score > best_match.quality_score:
                        best_match = match

            if best_match is None:
                break

            matches.append(best_match)

            # Marquer les blocs comme utilisés
            for block in best_match.blocks:
                used_block_ids.add(block.get('id'))

        return matches
