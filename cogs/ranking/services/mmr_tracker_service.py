# cogs/ranking/services/mmr_tracker_service.py
"""
Service metier pour le suivi MMR.
Aucun acces DB direct - delegue au ValorantDbService.
Aucun appel HTTP direct - delegue au HenrikDevService.
"""

import re
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database.services.valorant_db_service import EloHistoryRow, ValorantDbService
from integrations.henrikdev.service import HenrikDevService
from integrations.exceptions import RateLimitError

logger = logging.getLogger(__name__)

BACKFILL_RETRY_INTERVAL = timedelta(hours=6)


@dataclass(frozen=True)
class MmrHistoryBackfillResult:
    status: str
    inserted_count: int = 0
    source: str | None = None
    error: str | None = None


class MmrTrackerService:

    def __init__(
        self,
        valorant_db_svc: ValorantDbService,
        henrik_svc: HenrikDevService,
    ):
        self._valo_db = valorant_db_svc
        self._henrik = henrik_svc

    # ==================== tracking on/off ====================

    async def enable_tracking(self, discord_id: int) -> None:
        await self._valo_db.enable_tracking(discord_id)

    async def disable_tracking(self, discord_id: int) -> None:
        await self._valo_db.disable_tracking(discord_id)

    # ==================== tracked players ====================

    async def get_tracked_players(self) -> list[dict]:
        return await self._valo_db.get_tracked_players()

    # ==================== history reads ====================

    async def get_last_history_row(
        self, user_id: int, puuid: str | None = None
    ) -> Optional[EloHistoryRow]:
        return await self._valo_db.get_last_history_row(user_id, puuid)

    async def get_history(
        self, discord_id: int, season: int | None = None, act: int | None = None
    ) -> list[EloHistoryRow]:
        return await self._valo_db.get_history(discord_id, season, act)

    async def get_partitions(self, discord_id: int) -> list[tuple[int, int]]:
        return await self._valo_db.get_partitions(discord_id)

    async def get_latest_partition(self) -> Optional[tuple[int, int]]:
        return await self._valo_db.get_latest_partition()

    async def record_current_mmr_snapshot(self, row: dict[str, Any]) -> bool:
        """
        Enregistre un point MMR courant si l'ELO a change.
        Retourne True si une insertion a ete faite.
        """
        user_id = row["user_id"]
        puuid = row.get("puuid")
        region = row.get("region")
        platform = row.get("platform")
        current_elo = row["elo"]

        if puuid and region and platform:
            await self._maybe_backfill_tracked_row(row)

        if not puuid or current_elo is None or current_elo == 0:
            return False

        season = row.get("current_season")
        act = row.get("current_act")
        if season is None or act is None:
            latest_partition = await self.get_latest_partition()
            if latest_partition is None:
                logger.warning(
                    f"[record_current_mmr_snapshot] Donnees saison/acte incompletes pour user_id={user_id}, skip"
                )
                return False
            season, act = latest_partition

        last = await self.get_last_history_row(user_id, puuid)
        prev_elo = last.elo if last else None
        if prev_elo is not None and current_elo == prev_elo:
            return False

        rr_delta = 0 if prev_elo is None else current_elo - prev_elo
        entry = {
            "date": datetime.now(timezone.utc).isoformat(),
            "elo": current_elo,
            "rr_delta": rr_delta,
            "season": {"short": f"e{season}a{act}"},
        }
        return await self.insert_history_entry(
            user_id, entry, puuid=puuid, source="tracker_snapshot"
        )

    # ==================== history writes ====================

    async def insert_history_entry(
        self,
        user_id: int,
        entry: dict[str, Any],
        *,
        puuid: str | None = None,
        source: str = "tracker_snapshot",
    ) -> bool:
        """
        Parse une entree d'historique et l'insere en DB.
        L'entree doit contenir: date, elo, rr_delta/last_change, season.short.
        """
        raw_date = entry.get("date")
        elo = entry.get("elo")
        rr_delta = entry.get("rr_delta", entry.get("last_change", entry.get("rr", 0)))
        match_id = entry.get("match_id")
        if rr_delta is None:
            rr_delta = 0
        is_win = rr_delta > 0

        if elo is None:
            logger.warning(f"[insert_history_entry] Pas d'elo pour user_id={user_id}")
            return False

        season_info = entry.get("season") or {}
        season_short = season_info.get("short", "")
        if not season_short:
            logger.warning(
                f"[insert_history_entry] Pas de season.short pour user_id={user_id}. Ignore."
            )
            return False

        m = re.match(r"e(\d+)a(\d+)", season_short)
        if not m:
            logger.warning(
                f"[insert_history_entry] Format invalide: '{season_short}' pour user_id={user_id}. Ignore."
            )
            return False
        season_num, act_num = map(int, m.groups())

        if not raw_date:
            logger.warning(f"[insert_history_entry] Pas de date pour user_id={user_id}")
            return False

        if isinstance(raw_date, str):
            recorded_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        else:
            recorded_at = raw_date

        await self._valo_db.ensure_partitions(season_num, act_num)
        return await self._valo_db.insert_history_entry(
            user_id,
            season_num,
            act_num,
            recorded_at,
            elo,
            is_win,
            puuid=puuid,
            rr_delta=rr_delta,
            match_id=match_id,
            source=source,
        )

    # ==================== full history backfill ====================

    async def fetch_full_history(self, discord_id: int) -> MmrHistoryBackfillResult:
        """
        Recupere l'historique complet MMR depuis l'API et l'insere en DB.
        Utilise stored-mmr-history (archivee) avec fallback sur mmr-history (live).
        """
        logger.info(f"[fetch_full_history] Demarrage pour discord_id={discord_id}")

        info = await self._valo_db.get_valorant_info_by_discord_id(discord_id)
        if not info:
            logger.warning(f"[fetch_full_history] Pas de valorant_info pour discord_id={discord_id}")
            return MmrHistoryBackfillResult(status="pending_sync")

        if not info.puuid or not info.region or not info.platform:
            logger.warning(
                f"[fetch_full_history] Donnees incompletes pour discord_id={discord_id}: "
                f"puuid={info.puuid}, region={info.region}, platform={info.platform}"
            )
            return MmrHistoryBackfillResult(status="pending_sync")

        return await self._fetch_full_history_for_account(
            user_id=info.user_id,
            puuid=info.puuid,
            region=info.region,
            platform=info.platform,
            backfilled_at=info.mmr_history_backfilled_at,
        )

    async def _maybe_backfill_tracked_row(
        self, row: dict[str, Any]
    ) -> MmrHistoryBackfillResult | None:
        if row.get("mmr_history_backfilled_at") is not None:
            return None

        attempted_at = row.get("mmr_history_backfill_attempted_at")
        if not self._backfill_retry_due(attempted_at):
            return None

        result = await self._fetch_full_history_for_account(
            user_id=row["user_id"],
            puuid=row["puuid"],
            region=row["region"],
            platform=row["platform"],
            backfilled_at=None,
        )
        if result.status not in {"imported", "already_present"}:
            logger.info(
                "[_maybe_backfill_tracked_row] Backfill MMR non finalise pour user_id=%s: %s",
                row["user_id"],
                result.status,
            )
        return result

    async def _fetch_full_history_for_account(
        self,
        *,
        user_id: int,
        puuid: str,
        region: str,
        platform: str,
        backfilled_at: datetime | None,
    ) -> MmrHistoryBackfillResult:
        if backfilled_at is not None:
            return MmrHistoryBackfillResult(status="already_present")

        await self._valo_db.mark_mmr_history_backfill_attempt(user_id)

        # Tentative historique stocke
        history_entries: list[tuple[dict, str]] = []
        try:
            stored_resp, _ = await self._henrik.get_stored_mmr_history_by_puuid(
                region, platform, puuid,
            )
            if stored_resp.status == 200 and stored_resp.data:
                for entry in stored_resp.data:
                    history_entries.append((
                        self._history_entry_to_dict(entry),
                        "henrik_stored",
                    ))
        except RateLimitError:
            logger.error("[fetch_full_history] RateLimit sur stored history")
            await self._valo_db.mark_mmr_history_backfill_attempt(user_id, "rate_limited")
            return MmrHistoryBackfillResult(status="rate_limited", error="rate_limited")
        except Exception as e:
            logger.error(f"[fetch_full_history] Erreur stored history: {e}")

        # Fallback sur live history si vide
        if not history_entries:
            logger.info("[fetch_full_history] Pas d'historique stocke, fallback live")
            try:
                live_resp, _ = await self._henrik.get_mmr_history_by_puuid(
                    region, platform, puuid,
                )
                if live_resp.status == 200 and live_resp.data.history:
                    for entry in live_resp.data.history:
                        history_entries.append((
                            self._history_entry_to_dict(entry),
                            "henrik_live",
                        ))
            except RateLimitError:
                logger.error("[fetch_full_history] RateLimit sur live history")
                await self._valo_db.mark_mmr_history_backfill_attempt(user_id, "rate_limited")
                return MmrHistoryBackfillResult(status="rate_limited", error="rate_limited")
            except Exception as e:
                logger.error(f"[fetch_full_history] Erreur live history: {e}")
                error = self._short_error(e)
                await self._valo_db.mark_mmr_history_backfill_attempt(user_id, error)
                return MmrHistoryBackfillResult(status="error", error=error)

        if not history_entries:
            logger.warning(f"[fetch_full_history] Aucun historique pour user_id={user_id}")
            await self._valo_db.mark_mmr_history_backfill_attempt(user_id, "empty")
            return MmrHistoryBackfillResult(status="empty")

        logger.info(f"[fetch_full_history] Insertion de {len(history_entries)} entrees")
        inserted_count = 0
        imported_source = history_entries[0][1]
        for entry, source in history_entries:
            inserted = await self.insert_history_entry(
                user_id, entry, puuid=puuid, source=source
            )
            if inserted:
                inserted_count += 1

        await self._valo_db.mark_mmr_history_backfilled(user_id)

        logger.info(f"[fetch_full_history] Termine pour user_id={user_id}")
        return MmrHistoryBackfillResult(
            status="imported",
            inserted_count=inserted_count,
            source=imported_source,
        )

    @staticmethod
    def _history_entry_to_dict(entry: Any) -> dict[str, Any]:
        return {
            "date": entry.date,
            "season": {"short": entry.season.short},
            "elo": entry.elo,
            "rr_delta": entry.last_change,
            "match_id": getattr(entry, "match_id", None),
        }

    @staticmethod
    def _backfill_retry_due(attempted_at: datetime | None) -> bool:
        if attempted_at is None:
            return True
        if attempted_at.tzinfo is None:
            attempted_at = attempted_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - attempted_at >= BACKFILL_RETRY_INTERVAL

    @staticmethod
    def _short_error(exc: Exception) -> str:
        message = str(exc) or exc.__class__.__name__
        return message[:500]
