# cogs/ranking/services/mmr_stats_service.py
"""Pure MMR history period parsing and stat calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from typing import Protocol, Sequence


class MmrHistoryRow(Protocol):
    recorded_at: datetime
    elo: int


@dataclass(frozen=True)
class MmrPeriodSelection:
    period: str
    season_num: int | None
    act_num: int | None
    start_date: date | None


@dataclass(frozen=True)
class MmrStats:
    total_games: int
    total_change: int
    avg_win: int
    avg_loss: int
    last_diff: int
    dates_plot: list[datetime]
    elos_plot: list[int]


def parse_mmr_period(period: str | None, *, today: date | None = None) -> MmrPeriodSelection:
    selected_period = period or "today"
    reference_day = today or date.today()

    if selected_period == "today":
        return MmrPeriodSelection(selected_period, None, None, reference_day)
    if selected_period == "week":
        return MmrPeriodSelection(selected_period, None, None, reference_day - timedelta(days=7))
    if selected_period == "all":
        return MmrPeriodSelection(selected_period, None, None, None)

    match = re.match(r"e(\d+)a(\d+)", selected_period)
    if match:
        season_num, act_num = map(int, match.groups())
        return MmrPeriodSelection(selected_period, season_num, act_num, None)

    return MmrPeriodSelection(selected_period, None, None, reference_day)


def calculate_mmr_stats(
    history: Sequence[MmrHistoryRow],
    *,
    start_date: date | None,
) -> MmrStats | None:
    diffs: list[tuple[datetime, int]] = []
    for index in range(1, len(history)):
        recorded_at = history[index].recorded_at
        if start_date and recorded_at.date() < start_date:
            continue

        diff = history[index].elo - history[index - 1].elo
        diffs.append((recorded_at, diff))

    if not diffs:
        return None

    dates_plot = [
        row.recorded_at
        for row in history
        if not start_date or row.recorded_at.date() >= start_date
    ]
    elos_plot = [
        row.elo
        for row in history
        if not start_date or row.recorded_at.date() >= start_date
    ]
    if len(dates_plot) < 2:
        return None

    wins = [diff for _, diff in diffs if diff > 0]
    losses = [diff for _, diff in diffs if diff < 0]

    return MmrStats(
        total_games=len(diffs),
        total_change=sum(diff for _, diff in diffs),
        avg_win=round(sum(wins) / len(wins)) if wins else 0,
        avg_loss=round(sum(losses) / len(losses)) if losses else 0,
        last_diff=diffs[-1][1],
        dates_plot=dates_plot,
        elos_plot=elos_plot,
    )
