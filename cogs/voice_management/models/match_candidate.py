# cogs/voice_management/models/match_candidate.py
"""
Dataclass représentant un match candidat formé par l'algorithme.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class MatchCandidate:
    """
    Représente un match candidat avec ses métriques de qualité.

    Attributs:
        blocks: Liste des entrées de queue formant le match
        player_ids: Liste des IDs Discord de tous les joueurs
        elos: Liste des ELOs des joueurs
        roles: Liste des rôles sélectionnés
        timestamps: Liste des timestamps d'entrée en queue
        team_size: Taille d'équipe cible
        total_entry_type: Somme des entry_type (doit égaler team_size)
        quality_score: Score de qualité du match (0-1)
        elo_spread: Écart entre le plus haut et le plus bas ELO
        avg_elo: ELO moyen du match
        all_mmr_extended: True si tous les joueurs acceptent le MMR étendu
    """
    blocks: List[dict] = field(default_factory=list)
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

    @property
    def is_complete(self) -> bool:
        """Vérifie si le match est complet (taille atteinte)."""
        return self.total_entry_type == self.team_size

    @property
    def player_count(self) -> int:
        """Retourne le nombre de joueurs uniques."""
        return len(set(self.player_ids))

    @property
    def role_diversity(self) -> float:
        """
        Calcule la diversité des rôles (0-1).
        1 = tous les rôles différents
        """
        meaningful_roles = [r for r in self.roles if r.lower() != 'fill']
        if not meaningful_roles:
            return 1.0
        unique = len(set(meaningful_roles))
        return unique / len(meaningful_roles)

    @property
    def max_wait_seconds(self) -> Optional[float]:
        """Retourne le temps d'attente maximum en secondes."""
        if not self.timestamps:
            return None
        from datetime import timezone
        now = datetime.now(timezone.utc)
        max_wait = 0.0
        for ts in self.timestamps:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            wait = (now - ts).total_seconds()
            if wait > max_wait:
                max_wait = wait
        return max_wait

    def get_block_ids(self) -> List[int]:
        """Retourne les IDs des blocs de queue."""
        return [b.get('id') for b in self.blocks if b.get('id')]

    def __repr__(self) -> str:
        return (
            f"MatchCandidate(players={self.player_count}, "
            f"size={self.team_size}, quality={self.quality_score:.2f}, "
            f"elo_spread={self.elo_spread})"
        )
