# cogs/ranking/services/valorant_pipeline.py
"""
Pipeline de résolution Valorant en 4 étapes:
1. Account Resolution: name/tag -> puuid + region
2. Platform Detection: puuid -> platform (pc/console)
3. Rank Retrieval: puuid + region + platform -> rank + elo
4. Refresh: cycles suivants (seulement get_mmr)
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Optional, Tuple

from integrations.henrikdev.service import HenrikDevService
from integrations.henrikdev.models import RateLimit
from integrations.exceptions import RateLimitError, ApiError, NetworkError

logger = logging.getLogger(__name__)


class LocalRateLimitReached(Exception):
    """Levée quand la limite locale de requêtes/minute est atteinte."""

    def __init__(self, reset_seconds: int = 60):
        self.reset_seconds = reset_seconds
        super().__init__(f"Local rate limit reached, reset in {reset_seconds}s")


class PipelineStep(Enum):
    """État actuel d'un utilisateur dans le pipeline."""
    ACCOUNT_RESOLUTION = auto()   # puuid IS NULL
    PLATFORM_DETECTION = auto()   # platform IS NULL
    RANK_RETRIEVAL = auto()       # Tout est prêt pour récupérer le MMR


@dataclass
class UserPipelineState:
    """État actuel d'un utilisateur pour le traitement pipeline."""
    discord_id: int
    pseudo: str
    tag: str
    puuid: Optional[str]
    region: Optional[str]
    platform: Optional[str]
    rank: Optional[str]
    elo: Optional[int]
    error_count: int
    last_error_at: Optional[datetime]

    @property
    def current_step(self) -> PipelineStep:
        """Détermine l'étape actuelle basée sur les données disponibles."""
        if not self.puuid or not self.region:
            return PipelineStep.ACCOUNT_RESOLUTION
        if not self.platform:
            return PipelineStep.PLATFORM_DETECTION
        return PipelineStep.RANK_RETRIEVAL


@dataclass
class PipelineResult:
    """Résultat d'une exécution d'étape du pipeline."""
    success: bool
    step: PipelineStep
    puuid: Optional[str] = None
    region: Optional[str] = None
    platform: Optional[str] = None
    rank: Optional[str] = None
    elo: Optional[int] = None
    error_message: Optional[str] = None
    should_notify_user: bool = False
    api_name: Optional[str] = None
    api_tag: Optional[str] = None
    current_season: Optional[int] = None
    current_act: Optional[int] = None


class ValorantPipeline:
    """
    Pipeline en 4 étapes pour récupérer et mettre à jour les données Valorant.

    Étapes:
    1. ACCOUNT_RESOLUTION: Obtenir puuid + region depuis name/tag
    2. PLATFORM_DETECTION: Détecter PC vs Console via matchlist
    3. RANK_RETRIEVAL: Obtenir rank + elo actuels
    4. REFRESH: Mises à jour suivantes (seulement MMR)
    """

    # Configuration du backoff exponentiel pour les erreurs
    ERROR_THRESHOLD = 3
    BACKOFF_MINUTES = [5, 15, 60, 240]

    # Limite de requêtes par minute pour ce service (laisser ~20 req/min pour autres services)
    MAX_REQUESTS_PER_MINUTE = 70
    RATE_LIMIT_SAFETY_THRESHOLD = 5  # Pause si remaining < 5

    def __init__(self, service: HenrikDevService):
        self._service = service
        self._requests_this_minute = 0
        self._minute_start = datetime.now(timezone.utc)
        self._last_rate_limit: Optional[RateLimit] = None

    def _check_local_rate_limit(self) -> bool:
        """Vérifie si on a dépassé notre limite locale de 70 req/min."""
        now = datetime.now(timezone.utc)
        if (now - self._minute_start).total_seconds() >= 60:
            self._requests_this_minute = 0
            self._minute_start = now
        return self._requests_this_minute < self.MAX_REQUESTS_PER_MINUTE

    def _increment_request_count(self):
        """Incrémente le compteur de requêtes."""
        self._requests_this_minute += 1

    def should_pause_for_rate_limit(self, rate_limit: RateLimit) -> int:
        """
        Retourne le nombre de secondes à attendre si rate limit bas, sinon 0.

        Args:
            rate_limit: Objet RateLimit retourné par l'API

        Returns:
            Nombre de secondes à attendre (0 si pas besoin)
        """
        self._last_rate_limit = rate_limit
        if rate_limit.remaining < self.RATE_LIMIT_SAFETY_THRESHOLD:
            return rate_limit.reset_seconds
        return 0

    def get_local_rate_limit_reset(self) -> int:
        """Retourne le reset_seconds du dernier rate_limit connu, ou 60 par défaut."""
        if self._last_rate_limit:
            return self._last_rate_limit.reset_seconds
        return 60

    def should_skip_due_to_errors(self, state: UserPipelineState) -> bool:
        """
        Vérifie si l'utilisateur doit être ignoré à cause d'erreurs récentes.

        Utilise un backoff exponentiel: 5min, 15min, 60min, 240min.
        """
        if state.error_count == 0:
            return False

        if not state.last_error_at:
            return False

        # Calcul du temps de backoff basé sur error_count
        backoff_index = min(state.error_count - 1, len(self.BACKOFF_MINUTES) - 1)
        backoff_minutes = self.BACKOFF_MINUTES[backoff_index]

        next_retry = state.last_error_at + timedelta(minutes=backoff_minutes)
        should_skip = datetime.now(timezone.utc) < next_retry

        if should_skip:
            logger.debug(
                f"[Pipeline] Skipping {state.pseudo}#{state.tag} due to backoff "
                f"(error_count={state.error_count}, next_retry={next_retry})"
            )

        return should_skip

    async def execute_step(
        self, state: UserPipelineState
    ) -> Tuple[PipelineResult, Optional[RateLimit]]:
        """
        Exécute l'étape appropriée du pipeline selon l'état de l'utilisateur.

        Args:
            state: État actuel de l'utilisateur

        Returns:
            Tuple (PipelineResult, RateLimit ou None)

        Raises:
            LocalRateLimitReached: Si la limite locale est atteinte
            RateLimitError: Si l'API retourne 429
        """
        # Vérifier la limite locale avant tout appel
        if not self._check_local_rate_limit():
            raise LocalRateLimitReached(self.get_local_rate_limit_reset())

        step = state.current_step

        try:
            if step == PipelineStep.ACCOUNT_RESOLUTION:
                return await self._resolve_account(state)
            elif step == PipelineStep.PLATFORM_DETECTION:
                return await self._detect_platform(state)
            else:  # RANK_RETRIEVAL
                return await self._get_rank(state)

        except RateLimitError:
            # Re-raise pour que le cog puisse gérer
            raise

        except ApiError as e:
            logger.error(f"[Pipeline] ApiError for {state.pseudo}#{state.tag}: {e}")
            return PipelineResult(
                success=False,
                step=step,
                error_message=str(e),
                should_notify_user=(state.error_count >= self.ERROR_THRESHOLD - 1)
            ), self._last_rate_limit

        except NetworkError as e:
            logger.warning(f"[Pipeline] NetworkError for {state.pseudo}#{state.tag}: {e}")
            return PipelineResult(
                success=False,
                step=step,
                error_message=str(e)
            ), self._last_rate_limit

    async def _resolve_account(
        self, state: UserPipelineState
    ) -> Tuple[PipelineResult, Optional[RateLimit]]:
        """
        Étape 1: Résoudre name/tag vers puuid + region.

        Appelle get_account_by_name et extrait puuid et region.
        """
        logger.info(f"[Pipeline] Step 1 - Account Resolution for {state.pseudo}#{state.tag}")

        self._increment_request_count()
        account_resp, rate_limit = await self._service.get_account_by_name(
            state.pseudo, state.tag
        )
        self._last_rate_limit = rate_limit

        if account_resp.status != 200:
            logger.warning(
                f"[Pipeline] Account not found for {state.pseudo}#{state.tag} "
                f"(status={account_resp.status})"
            )
            return PipelineResult(
                success=False,
                step=PipelineStep.ACCOUNT_RESOLUTION,
                error_message=f"Compte introuvable: {state.pseudo}#{state.tag}",
                should_notify_user=True
            ), rate_limit

        data = account_resp.data
        logger.info(
            f"[Pipeline] Account resolved: {state.pseudo}#{state.tag} -> "
            f"puuid={data.puuid[:8]}..., region={data.region}"
        )

        return PipelineResult(
            success=True,
            step=PipelineStep.ACCOUNT_RESOLUTION,
            puuid=data.puuid,
            region=data.region,
            api_name=data.name,
            api_tag=data.tag,
        ), rate_limit

    async def _detect_platform(
        self, state: UserPipelineState
    ) -> Tuple[PipelineResult, Optional[RateLimit]]:
        """
        Étape 2: Détecter la platform (PC ou Console) via matchlist.

        Essaie d'abord PC (plus commun), puis Console.
        Si aucun match trouvé, retourne un échec soft (réessayer plus tard).
        """
        logger.info(f"[Pipeline] Step 2 - Platform Detection for {state.pseudo}#{state.tag}")

        rate_limit = None

        # Essayer PC d'abord (majorité des joueurs)
        try:
            self._increment_request_count()
            matchlist_resp, rate_limit = await self._service.get_matchlist_by_puuid(
                state.region, "pc", state.puuid, size=1
            )
            self._last_rate_limit = rate_limit

            if matchlist_resp.status == 200 and len(matchlist_resp.data) > 0:
                logger.info(f"[Pipeline] Platform detected: PC for {state.pseudo}#{state.tag}")
                return PipelineResult(
                    success=True,
                    step=PipelineStep.PLATFORM_DETECTION,
                    platform="pc"
                ), rate_limit

        except ApiError as e:
            logger.debug(f"[Pipeline] PC matchlist failed for {state.pseudo}#{state.tag}: {e}")

        # Essayer Console
        try:
            self._increment_request_count()
            matchlist_resp, rate_limit = await self._service.get_matchlist_by_puuid(
                state.region, "console", state.puuid, size=1
            )
            self._last_rate_limit = rate_limit

            if matchlist_resp.status == 200 and len(matchlist_resp.data) > 0:
                logger.info(f"[Pipeline] Platform detected: Console for {state.pseudo}#{state.tag}")
                return PipelineResult(
                    success=True,
                    step=PipelineStep.PLATFORM_DETECTION,
                    platform="console"
                ), rate_limit

        except ApiError as e:
            logger.debug(f"[Pipeline] Console matchlist failed for {state.pseudo}#{state.tag}: {e}")

        # Aucun match trouvé sur aucune platform
        # Pas de match = pas de rang possible, on réessaie plus tard
        logger.info(
            f"[Pipeline] No matches found for {state.pseudo}#{state.tag}, "
            f"will retry later (no rank without matches)"
        )
        return PipelineResult(
            success=False,
            step=PipelineStep.PLATFORM_DETECTION,
            error_message="Aucune partie trouvée, réessai ultérieur",
            should_notify_user=False  # Pas de notif, c'est normal pour un nouveau joueur
        ), rate_limit

    async def _get_rank(
        self, state: UserPipelineState
    ) -> Tuple[PipelineResult, Optional[RateLimit]]:
        """
        Étape 3/4: Récupérer le rank et l'elo actuels.

        Appelé quand puuid, region et platform sont tous disponibles.
        """
        logger.info(f"[Pipeline] Step 3/4 - Rank Retrieval for {state.pseudo}#{state.tag}")

        self._increment_request_count()
        mmr_resp, rate_limit = await self._service.get_mmr_by_puuid(
            state.region, state.platform, state.puuid
        )
        self._last_rate_limit = rate_limit

        if mmr_resp.status != 200:
            logger.warning(
                f"[Pipeline] MMR not available for {state.pseudo}#{state.tag} "
                f"(status={mmr_resp.status})"
            )
            return PipelineResult(
                success=False,
                step=PipelineStep.RANK_RETRIEVAL,
                error_message="Données MMR non disponibles"
            ), rate_limit

        current_data = mmr_resp.data.current
        rank_name = current_data.tier.name if current_data.tier else "Unrated"
        elo = current_data.elo

        # Extraire name/tag depuis account
        account = mmr_resp.data.account
        api_name = account.name
        api_tag = account.tag

        # Extraire season/act depuis seasonal
        current_season: Optional[int] = None
        current_act: Optional[int] = None
        if mmr_resp.data.seasonal:
            latest = mmr_resp.data.seasonal[0]
            short = latest.season.short
            m = re.match(r"e(\d+)a(\d+)", short, re.I)
            if m:
                current_season, current_act = map(int, m.groups())

        logger.info(
            f"[Pipeline] Rank retrieved: {state.pseudo}#{state.tag} -> "
            f"{rank_name} (elo={elo}, season=e{current_season}a{current_act})"
        )

        return PipelineResult(
            success=True,
            step=PipelineStep.RANK_RETRIEVAL,
            rank=rank_name,
            elo=elo,
            api_name=api_name,
            api_tag=api_tag,
            current_season=current_season,
            current_act=current_act,
        ), rate_limit
