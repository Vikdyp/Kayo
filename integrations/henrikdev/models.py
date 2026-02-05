# integrations/henrikdev/models.py
from __future__ import annotations

from typing import Any, Mapping, Optional, List, Sequence
from pydantic import BaseModel, ConfigDict, Field

from datetime import datetime


# --------------------------------------------------------------------------------------------------------------------------
# Model pour le rate limite en general le meme dans tout les headers                                                       |
# --------------------------------------------------------------------------------------------------------------------------

class RateLimit(BaseModel):
    """Infos rate limit extraites des headers."""
    model_config = ConfigDict(extra="ignore")

    limit: Optional[int] = None
    remaining: Optional[int] = None
    reset_seconds: Optional[int] = None
    bucket: Optional[str] = None
    version: Optional[str] = None


# --------------------------------------------------------------------------------------------------------------------------
# Model pour requete Account avec PUUID https://api.henrikdev.xyz/valorant/v1/by-puuid/account/{puuid}                     |
# --------------------------------------------------------------------------------------------------------------------------

class Card(BaseModel):
    model_config = ConfigDict(extra="ignore")

    small: str
    large: str
    wide: str
    id: str


class AccountDataPuuid(BaseModel):
    model_config = ConfigDict(extra="ignore")

    puuid: str
    region: str
    account_level: int
    name: str
    tag: str
    card: Card
    last_update: str
    last_update_raw: int


class AccountResponsePuuid(BaseModel):
    """
    Account info returned

    - :data.puuid: str
    - :data.region: str
    - :data.account_level: int
    - :data.name: str
    - :data.tag: str
    - :data.card.small: str
    - :data.card.large: str
    - :data.card.wide: str
    - :data.card.id: str
    - :data.last_update: str
    - :data.last_update_raw: str
    """
    model_config = ConfigDict(extra="ignore")

    status: int
    data: AccountDataPuuid


# --------------------------------------------------------------------------------------------------------------------------
# Model pour requete Account avec Name + Tag https://api.henrikdev.xyz/valorant/v2/account/{name}/{tag}                    |
# --------------------------------------------------------------------------------------------------------------------------

class AccountDataName(BaseModel):
    model_config = ConfigDict(extra="ignore")

    puuid: str
    region: str
    account_level: int
    name: str
    tag: str
    card: str
    title: str
    platforms: Sequence[str]
    updated_at: str


class AccountResponseName(BaseModel):
    """
    Account info returned

    - :data.puuid: str
    - :data.region: str
    - :data.account_level: int
    - :data.name: str
    - :data.tag: str
    - :data.card: str
    - :data.title: str
    - :data.platforms: Sequence[str]
    - :data.updated_at: str
    """
    model_config = ConfigDict(extra="ignore")

    status: int
    data: AccountDataName


# --------------------------------------------------------------------------------------------------------------------------
# Model pour requete generique                                                                                             |
# --------------------------------------------------------------------------------------------------------------------------

class HttpResponse(BaseModel):
    """
    Réponse générique du HTTPClient: JSON + headers + status.
    headers est un dict[str, str] simplifié.
    """
    model_config = ConfigDict(extra="ignore")

    status: int
    payload: dict[str, Any]
    headers: dict[str, str] = Field(default_factory=dict)

    def ratelimit(self) -> RateLimit:
        # normalise les clés en lowercase pour rendre les lookups robustes
        h = {k.lower(): v for k, v in self.headers.items()}

        def _to_int(x: str | None) -> int | None:
            if x is None:
                return None
            try:
                return int(x)
            except ValueError:
                return None

        return RateLimit(
            limit=_to_int(h.get("x-ratelimit-limit")),
            remaining=_to_int(h.get("x-ratelimit-remaining")),
            reset_seconds=_to_int(h.get("x-ratelimit-reset")),
            bucket=h.get("x-ratelimit-bucket"),
            version=h.get("x-version"),
        )

# --------------------------------------------------------------------------------------------------------------------------
# Model pour requete MMR avec PUUID https://api.henrikdev.xyz/valorant/v3/by-puuid/mmr/{region}/{platform}/{puuid}         |
# --------------------------------------------------------------------------------------------------------------------------

class MmrAccount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    puuid: str
    name: str
    tag: str


class SeasonRef(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    short: str


class TierRef(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    name: str


class LeaderboardPlacement(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rank: int
    updated_at: str  # ISO string


class PeakData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    season: SeasonRef
    ranking_schema: str
    tier: TierRef
    rr: Optional[int] = None


class CurrentData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tier: TierRef
    rr: int
    last_change: int
    elo: int
    games_needed_for_rating: int
    rank_protection_shields: Optional[int] = None
    leaderboard_placement: Optional[LeaderboardPlacement] = None


class SeasonalEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    season: SeasonRef
    wins: int
    games: int
    end_tier: TierRef
    end_rr: Optional[int] = None
    ranking_schema: str
    leaderboard_placement: Optional[LeaderboardPlacement] = None
    act_wins: List[TierRef] = Field(default_factory=list)


class MmrData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    account: MmrAccount
    peak: PeakData
    current: CurrentData
    seasonal: List[SeasonalEntry] = Field(default_factory=list)


class MmrResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: int
    data: MmrData


# -----------------------------------------------------------------------------------------------------------------------------
# Model pour requete Matchlist avec PUUID https://api.henrikdev.xyz/valorant/v4/by-puuid/matches/{region}/{platform}/{puuid}  |
# -----------------------------------------------------------------------------------------------------------------------------

class PremierInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tournament_id: Optional[str] = None
    matchup_id: Optional[str] = None


class MatchMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    map: Optional[dict] = None
    game_version: Optional[str] = None
    game_length: Optional[int] = None
    game_start: Optional[int] = None
    game_start_patched: Optional[str] = None
    rounds_played: Optional[int] = None
    mode: Optional[str] = None
    mode_id: Optional[str] = None
    queue: Optional[dict] = None
    season_id: Optional[str] = None
    platform: Optional[str] = None
    matchid: Optional[str] = None
    premier_info: Optional[PremierInfo] = None
    region: Optional[str] = None
    cluster: Optional[str] = None


class SessionPlaytime(BaseModel):
    model_config = ConfigDict(extra="ignore")
    minutes: Optional[int] = None
    seconds: Optional[int] = None
    milliseconds: Optional[int] = None


class MatchPlayer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    puuid: str
    name: Optional[str] = None
    tag: Optional[str] = None
    team: Optional[str] = None
    level: Optional[int] = None
    character: Optional[str] = None

    currenttier: Optional[int] = None
    currenttier_patched: Optional[str] = None

    player_card: Optional[str] = None
    player_title: Optional[str] = None
    party_id: Optional[str] = None

    session_playtime: Optional[SessionPlaytime] = None

    # Le endpoint renvoie beaucoup d'autres champs (stats, economy, etc.)
    # On les ignore volontairement (extra="ignore").


class MatchItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    metadata: MatchMetadata
    players: Optional[List[MatchPlayer]] = None
    # La réponse peut contenir aussi teams, rounds, etc. (ignorés)


class MatchlistResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: int
    data: List[MatchItem]
    

# ---------------------------------------------------------------------------------------------------------------------
# Models for /valorant/v2/by-puuid/mmr-history/{region}/{platform}/{puuid}
# ---------------------------------------------------------------------------------------------------------------------

class MmrTier(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    name: str

class MmrMap(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str

class MmrSeason(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    short: str

class MmrHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tier: MmrTier
    match_id: str
    map: MmrMap
    season: MmrSeason
    rr: int
    last_change: int
    elo: int
    refunded_rr: int
    was_derank_protected: bool
    date: datetime

class MmrAccount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    tag: str
    puuid: str

class MmrHistoryData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    account: MmrAccount
    history: List[MmrHistoryEntry]

class MmrHistoryV2Response(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: int
    data: MmrHistoryData


# ---------------------------------------------------------------------------------------------------------------------
# Models for /valorant/v2/by-puuid/stored-mmr-history/{region}/{platform}/{puuid}
# ---------------------------------------------------------------------------------------------------------------------

class StoredMmrResults(BaseModel):
    model_config = ConfigDict(extra="ignore")
    total: int
    returned: int
    before: int
    after: int

class StoredMmrHistoryV2Response(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: int
    results: StoredMmrResults
    data: List[MmrHistoryEntry] # Reuses MmrHistoryEntry
