# cogs/ranking/services/mmr_tracker_service.py
"""
Service metier pour le suivi MMR.
Aucun acces DB direct - delegue au ValorantDbService.
Aucun appel HTTP direct - delegue au HenrikDevService.
"""

import re
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database.services.valorant_db_service import EloHistoryRow, ValorantDbService
from integrations.henrikdev.service import HenrikDevService
from integrations.exceptions import RateLimitError

logger = logging.getLogger(__name__)


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

    async def get_last_history_row(self, user_id: int) -> Optional[EloHistoryRow]:
        return await self._valo_db.get_last_history_row(user_id)

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
        current_elo = row["elo"]

        if current_elo is None or current_elo == 0:
            return False

        last = await self.get_last_history_row(user_id)
        prev_elo = last.elo if last else None
        if prev_elo is not None and current_elo == prev_elo:
            return False

        season = row.get("current_season")
        act = row.get("current_act")
        if season is None or act is None:
            partition = await self.get_latest_partition()
            if partition is None:
                logger.warning(
                    f"[record_current_mmr_snapshot] Pas de partition disponible pour user_id={user_id}, skip"
                )
                return False
            season, act = partition

        rr = 0 if prev_elo is None else current_elo - prev_elo
        entry = {
            "date": datetime.now(timezone.utc).isoformat(),
            "elo": current_elo,
            "rr": rr,
            "season": {"short": f"e{season}a{act}"},
        }
        await self.insert_history_entry(user_id, entry)
        return True

    # ==================== history writes ====================

    async def insert_history_entry(
        self, user_id: int, entry: dict[str, Any]
    ) -> None:
        """
        Parse une entree d'historique et l'insere en DB.
        L'entree doit contenir: date, elo, rr, season.short.
        """
        raw_date = entry.get("date")
        elo = entry.get("elo")
        rr = entry.get("rr", 0)
        is_win = rr >= 0

        season_info = entry.get("season") or {}
        season_short = season_info.get("short", "")
        if not season_short:
            logger.warning(
                f"[insert_history_entry] Pas de season.short pour user_id={user_id}. Ignore."
            )
            return

        m = re.match(r"e(\d+)a(\d+)", season_short)
        if not m:
            logger.warning(
                f"[insert_history_entry] Format invalide: '{season_short}' pour user_id={user_id}. Ignore."
            )
            return
        season_num, act_num = map(int, m.groups())

        if not raw_date:
            logger.warning(f"[insert_history_entry] Pas de date pour user_id={user_id}")
            return

        if isinstance(raw_date, str):
            recorded_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        else:
            recorded_at = raw_date

        await self._valo_db.ensure_partitions(season_num, act_num)
        await self._valo_db.insert_history_entry(
            user_id, season_num, act_num, recorded_at, elo, is_win,
        )

    # ==================== full history backfill ====================

    async def fetch_full_history(self, discord_id: int) -> None:
        """
        Recupere l'historique complet MMR depuis l'API et l'insere en DB.
        Utilise stored-mmr-history (archivee) avec fallback sur mmr-history (live).
        """
        logger.info(f"[fetch_full_history] Demarrage pour discord_id={discord_id}")

        info = await self._valo_db.get_valorant_info_by_discord_id(discord_id)
        if not info:
            logger.warning(f"[fetch_full_history] Pas de valorant_info pour discord_id={discord_id}")
            return

        if not info.puuid or not info.region or not info.platform:
            logger.warning(
                f"[fetch_full_history] Donnees incompletes pour discord_id={discord_id}: "
                f"puuid={info.puuid}, region={info.region}, platform={info.platform}"
            )
            return

        # Tentative historique stocke
        history_entries: list[dict] = []
        try:
            stored_resp, _ = await self._henrik.get_stored_mmr_history_by_puuid(
                info.region, info.platform, info.puuid,
            )
            if stored_resp.status == 200 and stored_resp.data:
                for entry in stored_resp.data:
                    history_entries.append({
                        "date": entry.date,
                        "season": {"short": entry.season.short},
                        "elo": entry.elo,
                        "rr": entry.rr,
                    })
        except RateLimitError:
            logger.error("[fetch_full_history] RateLimit sur stored history")
            return
        except Exception as e:
            logger.error(f"[fetch_full_history] Erreur stored history: {e}")

        # Fallback sur live history si vide
        if not history_entries:
            logger.info("[fetch_full_history] Pas d'historique stocke, fallback live")
            try:
                live_resp, _ = await self._henrik.get_mmr_history_by_puuid(
                    info.region, info.platform, info.puuid,
                )
                if live_resp.status == 200 and live_resp.data.history:
                    for entry in live_resp.data.history:
                        history_entries.append({
                            "date": entry.date,
                            "season": {"short": entry.season.short},
                            "elo": entry.elo,
                            "rr": entry.rr,
                        })
            except RateLimitError:
                logger.error("[fetch_full_history] RateLimit sur live history")
                return
            except Exception as e:
                logger.error(f"[fetch_full_history] Erreur live history: {e}")
                return

        if not history_entries:
            logger.warning(f"[fetch_full_history] Aucun historique pour discord_id={discord_id}")
            return

        logger.info(f"[fetch_full_history] Insertion de {len(history_entries)} entrees")
        for entry in history_entries:
            await self.insert_history_entry(info.user_id, entry)

        logger.info(f"[fetch_full_history] Termine pour discord_id={discord_id}")
