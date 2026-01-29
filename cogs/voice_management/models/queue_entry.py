# cogs/voice_management/models/queue_entry.py
"""
Dataclass représentant une entrée dans la queue de matchmaking.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class QueueEntry:
    """
    Représente une entrée dans la queue de matchmaking.

    Attributs:
        id: ID unique de l'entrée en base
        server_id: ID interne du serveur
        entry_type: Type d'entrée (1=solo, 2=duo, etc.)
        discord_member_id: ID Discord du membre principal
        team_member_ids: Liste des IDs des membres de l'équipe (pour les groupes)
        langue: Langue préférée
        region: Région de jeu
        platform: Plateforme (PC, Console, etc.)
        team_size: Taille d'équipe recherchée (2, 3, 5 ou 0 pour any)
        mmr_extended: Si le joueur accepte un écart MMR étendu
        elo: ELO du joueur/leader
        elo_high: ELO le plus élevé de l'équipe
        elo_low: ELO le plus bas de l'équipe
        roles: Rôles préférés
        timestamp: Horodatage d'entrée en queue
    """
    id: int
    server_id: int
    entry_type: int
    discord_member_id: int
    team_member_ids: List[int] = field(default_factory=list)
    langue: str = "FR"
    region: str = "EU"
    platform: str = "PC"
    team_size: int = 0
    mmr_extended: bool = False
    elo: int = 0
    elo_high: int = 0
    elo_low: int = 0
    roles: List[str] = field(default_factory=list)
    timestamp: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'QueueEntry':
        """
        Crée une QueueEntry à partir d'un dictionnaire (row de la BDD).

        Args:
            data: Dictionnaire avec les données

        Returns:
            Instance de QueueEntry
        """
        return cls(
            id=data.get('id', 0),
            server_id=data.get('server_id', 0),
            entry_type=data.get('entry_type', 1),
            discord_member_id=data.get('discord_member_id', 0),
            team_member_ids=data.get('team_member_ids') or [],
            langue=data.get('langue', 'FR'),
            region=data.get('region', 'EU'),
            platform=data.get('platform', 'PC'),
            team_size=data.get('team_size', 0),
            mmr_extended=data.get('mmr_extended', False),
            elo=data.get('elo', 0),
            elo_high=data.get('elo_high', 0),
            elo_low=data.get('elo_low', 0),
            roles=data.get('roles') or [],
            timestamp=data.get('timestamp'),
        )

    def to_dict(self) -> dict:
        """
        Convertit l'entrée en dictionnaire.

        Returns:
            Dictionnaire représentant l'entrée
        """
        return {
            'id': self.id,
            'server_id': self.server_id,
            'entry_type': self.entry_type,
            'discord_member_id': self.discord_member_id,
            'team_member_ids': self.team_member_ids,
            'langue': self.langue,
            'region': self.region,
            'platform': self.platform,
            'team_size': self.team_size,
            'mmr_extended': self.mmr_extended,
            'elo': self.elo,
            'elo_high': self.elo_high,
            'elo_low': self.elo_low,
            'roles': self.roles,
            'timestamp': self.timestamp,
        }

    @property
    def all_member_ids(self) -> List[int]:
        """
        Retourne tous les IDs des membres (incluant le leader).
        """
        if self.team_member_ids:
            return list(set(self.team_member_ids))
        return [self.discord_member_id]

    @property
    def is_solo(self) -> bool:
        """Vérifie si c'est une entrée solo."""
        return self.entry_type == 1

    @property
    def is_team(self) -> bool:
        """Vérifie si c'est une entrée d'équipe."""
        return self.entry_type > 1

    def __repr__(self) -> str:
        return (
            f"QueueEntry(id={self.id}, type={self.entry_type}, "
            f"member={self.discord_member_id}, elo={self.elo}, "
            f"team_size={self.team_size})"
        )
