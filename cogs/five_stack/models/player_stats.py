# cogs/voice_management/models/player_stats.py
"""
Dataclass représentant les statistiques de matchmaking d'un joueur.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class PlayerStats:
    """
    Statistiques de matchmaking d'un joueur.

    Attributs:
        discord_id: ID Discord du joueur
        server_id: ID interne du serveur
        total_matches: Nombre total de matchs joués
        total_wait_time_seconds: Temps total d'attente en secondes
        matches_as_solo: Nombre de matchs en solo
        matches_in_group: Nombre de matchs en groupe
        last_match_at: Date du dernier match
        preferred_role: Rôle préféré (le plus joué)
    """
    discord_id: int
    server_id: int
    total_matches: int = 0
    total_wait_time_seconds: int = 0
    matches_as_solo: int = 0
    matches_in_group: int = 0
    last_match_at: Optional[datetime] = None
    preferred_role: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'PlayerStats':
        """
        Crée une instance à partir d'un dictionnaire.

        Args:
            data: Dictionnaire avec les données

        Returns:
            Instance de PlayerStats
        """
        return cls(
            discord_id=data.get('discord_id', 0),
            server_id=data.get('server_id', 0),
            total_matches=data.get('total_matches', 0),
            total_wait_time_seconds=data.get('total_wait_time_seconds', 0),
            matches_as_solo=data.get('matches_as_solo', 0),
            matches_in_group=data.get('matches_in_group', 0),
            last_match_at=data.get('last_match_at'),
            preferred_role=data.get('preferred_role'),
        )

    @property
    def avg_wait_time_seconds(self) -> float:
        """Retourne le temps d'attente moyen en secondes."""
        if self.total_matches == 0:
            return 0.0
        return self.total_wait_time_seconds / self.total_matches

    @property
    def solo_ratio(self) -> float:
        """Retourne le ratio de matchs en solo (0-1)."""
        if self.total_matches == 0:
            return 0.0
        return self.matches_as_solo / self.total_matches

    @property
    def group_ratio(self) -> float:
        """Retourne le ratio de matchs en groupe (0-1)."""
        if self.total_matches == 0:
            return 0.0
        return self.matches_in_group / self.total_matches

    def format_avg_wait_time(self) -> str:
        """
        Formate le temps d'attente moyen en chaîne lisible.

        Returns:
            Chaîne formatée (ex: "2m 30s")
        """
        avg = self.avg_wait_time_seconds
        if avg < 60:
            return f"{int(avg)}s"

        minutes = int(avg // 60)
        seconds = int(avg % 60)

        if minutes < 60:
            return f"{minutes}m {seconds}s" if seconds > 0 else f"{minutes}m"

        hours = minutes // 60
        remaining_minutes = minutes % 60
        return f"{hours}h {remaining_minutes}m"

    def __repr__(self) -> str:
        return (
            f"PlayerStats(discord_id={self.discord_id}, "
            f"matches={self.total_matches}, "
            f"avg_wait={self.format_avg_wait_time()})"
        )
