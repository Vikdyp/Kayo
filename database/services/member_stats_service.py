# database/services/member_stats_service.py
"""
Gestion des transactions pour les stats membres.
Orchestration multi-repos. Méthodes globales réutilisables.
"""

from datetime import date, timedelta, timezone
from dataclasses import dataclass
from typing import Optional

from database.repos.guilds_repo import GuildsRepo
from database.repos.member_daily_stats_repo import MemberDailyStatsRepo, MemberDailyStatsRow


@dataclass(frozen=True)
class PeriodStats:
    join_count: int
    leave_count: int
    ratio: str  # "N/A", "∞", ou valeur numérique


class MemberStatsService:
    """
    Service DB pour les statistiques de membres.
    Transactions uniquement ici, pas dans les repos.
    """

    def __init__(self, db):
        self._db = db

    @staticmethod
    def _get_today_utc() -> date:
        """Retourne la date du jour en UTC."""
        from datetime import datetime
        return datetime.now(timezone.utc).date()

    async def record_join(self, guild_id: int, guild_name: Optional[str] = None) -> None:
        """Enregistre un join pour aujourd'hui (UTC)."""
        today = self._get_today_utc()
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await MemberDailyStatsRepo.increment_join(conn, guild_id, today)

    async def record_leave(self, guild_id: int, guild_name: Optional[str] = None) -> None:
        """Enregistre un départ pour aujourd'hui (UTC)."""
        today = self._get_today_utc()
        async with self._db.transaction() as conn:
            await GuildsRepo.ensure_exists(conn, guild_id, guild_name)
            await MemberDailyStatsRepo.increment_leave(conn, guild_id, today)

    async def get_period_stats(self, guild_id: int, days: Optional[int]) -> PeriodStats:
        """
        Retourne les stats agrégées sur une période.
        days=None → tout l'historique (total)
        days=7 → 7 derniers jours
        """
        today = self._get_today_utc()
        from_date = None if days is None else today - timedelta(days=days)

        async with self._db.acquire() as conn:
            total_joins, total_leaves = await MemberDailyStatsRepo.sum_range(
                conn, guild_id, from_date, today
            )

        # Calcul du ratio
        if total_leaves == 0:
            ratio = "∞" if total_joins > 0 else "N/A"
        else:
            ratio = str(round(total_joins / total_leaves, 2))

        return PeriodStats(
            join_count=total_joins,
            leave_count=total_leaves,
            ratio=ratio,
        )

    async def get_evolution_data(
        self,
        guild_id: int,
        days: Optional[int],
    ) -> list[MemberDailyStatsRow]:
        """
        Retourne les données brutes pour l'évolution sur une période.
        days=None → tout l'historique
        """
        today = self._get_today_utc()
        from_date = None if days is None else today - timedelta(days=days)

        async with self._db.acquire() as conn:
            return await MemberDailyStatsRepo.list_range(conn, guild_id, from_date, today)
