# cogs/ranking/services/mmr_tracker_service.py

from __future__ import annotations

import re
import logging
from datetime import datetime
from typing import Any, Optional

from database.services.valorant_info_service import ValorantInfoService
from database.services.mmr_history_service import MmrHistoryService
from cogs.ranking.services.valorant_service import (
    get_puuid,
    get_mmr_history,
    get_stored_mmr_history,
    RateLimitException,
)

logger = logging.getLogger(__name__)


class MmrTrackerService:
    def __init__(
        self,
        valorant_info_svc: ValorantInfoService,
        mmr_history_svc: MmrHistoryService,
    ):
        self._info = valorant_info_svc
        self._history = mmr_history_svc

    # -- Tracking on/off -----------------------------------------------

    async def enable_tracking(self, discord_id: int) -> None:
        await self._info.enable_tracking(discord_id)
        logger.info(f"[MmrTrackerService] Tracking activé pour discord_id={discord_id}")

    async def disable_tracking(self, discord_id: int) -> None:
        await self._info.disable_tracking(discord_id)
        logger.info(f"[MmrTrackerService] Tracking désactivé pour discord_id={discord_id}")

    # -- Background loop helpers ----------------------------------------

    async def get_tracked_players(self) -> list[dict]:
        return await self._history.get_tracked_players()

    async def get_last_history_row(self, user_id: int) -> Optional[dict]:
        return await self._history.get_last_row(user_id)

    async def record_elo_change(
        self, user_id: int, elo: int, prev_elo: Optional[int], season: int, act: int
    ) -> None:
        rr = 0 if prev_elo is None else (elo - prev_elo)
        is_win = rr >= 0
        recorded_at = datetime.utcnow()
        await self._history.insert_entry(
            user_id, season, act, recorded_at, elo, is_win
        )
        logger.debug(
            f"[MmrTrackerService] Historique ajouté user_id={user_id} elo={elo} rr={rr}"
        )

    async def fetch_current_partition(self, user_id: int) -> tuple[int, int]:
        info = await self._history.get_valorant_info(user_id)
        if info and info.get("puuid"):
            try:
                history = await get_mmr_history(info["region"], info["puuid"])
                if history:
                    first = history[0]
                    season_data = first.get("season") if isinstance(first, dict) else None
                    if season_data:
                        short = season_data.get("short", "")
                        m = re.match(r"e(\d+)a(\d+)", short, re.I)
                        if m:
                            return tuple(map(int, m.groups()))
            except RateLimitException:
                logger.warning("[fetch_current_partition] Rate limited, using DB fallback")

        # Fallback: dernière partition en base
        result = await self._history.get_latest_partition()
        if not result:
            raise ValueError(f"Aucune partition disponible pour user_id={user_id}")
        return result

    # -- Full history fetch --------------------------------------------

    async def fetch_full_history(self, discord_id: int) -> None:
        logger.info(f"[fetch_full_history] Démarrage pour discord_id={discord_id}")

        user_pk = await self._info._get_user_pk(discord_id)
        if not user_pk:
            logger.warning(f"[fetch_full_history] Aucun ID interne pour discord_id={discord_id}")
            return

        info = await self._history.get_valorant_info(user_pk)
        if not info:
            logger.warning(f"[fetch_full_history] Pas de valorant_info pour user_id={user_pk}")
            return

        pseudo, tag, region, puuid = info["pseudo"], info["tag"], info["region"], info["puuid"]

        # Récupérer PUUID si manquant
        if not puuid:
            try:
                result = await get_puuid(pseudo, tag)
            except RateLimitException:
                logger.error("[fetch_full_history] RateLimit sur get_puuid")
                return
            if not result:
                logger.warning(f"[fetch_full_history] Profil introuvable pour {pseudo}#{tag}")
                return
            _, region, puuid = result
            await self._history.update_puuid(user_pk, puuid)

        # Essayer historique stocké
        try:
            history = await get_stored_mmr_history(region, puuid)
        except RateLimitException:
            logger.error("[fetch_full_history] RateLimit sur stored history")
            return

        # Fallback vers live
        if not history:
            try:
                live = await get_mmr_history(region, puuid)
            except RateLimitException:
                logger.error("[fetch_full_history] RateLimit sur live history")
                return
            if not live:
                logger.warning(f"[fetch_full_history] Pas d'historique pour {puuid}")
                return
            history = [
                {"date": e["date"], "season": e["season"], "elo": e["elo"], "rr": e.get("rr", 0)}
                for e in live
                if e.get("elo") and e["elo"] > 0
            ]

        # Insertion des entrées
        logger.info(f"[fetch_full_history] Insertion de {len(history)} entrées")
        for entry in history:
            await self._insert_history_entry(user_pk, entry)

    async def _insert_history_entry(self, user_id: int, entry: dict) -> None:
        elo = entry.get("elo")
        if elo is None or elo <= 0:
            return

        season_info = entry.get("season") or {}
        season_short = season_info.get("short", "")
        m = re.match(r"e(\d+)a(\d+)", season_short)
        if not m:
            return

        season_num, act_num = map(int, m.groups())

        raw_date = entry.get("date")
        if not raw_date:
            return
        recorded_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))

        rr = entry.get("rr", 0)
        is_win = rr >= 0

        await self._history.insert_entry(
            user_id, season_num, act_num, recorded_at, elo, is_win
        )

    # -- Stats / History for display -----------------------------------

    async def get_history(
        self, discord_id: int, season: Optional[int] = None, act: Optional[int] = None
    ) -> list[dict]:
        return await self._history.get_history(discord_id, season, act)

    async def get_partitions(self, discord_id: int) -> list[tuple[int, int]]:
        return await self._history.get_distinct_partitions(discord_id)

    async def account_linked(self, discord_id: int) -> bool:
        return await self._info.account_linked(discord_id)
