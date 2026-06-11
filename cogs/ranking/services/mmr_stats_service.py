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
class _DiffRow:
    row: MmrHistoryRow
    diff: int


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
    period_rows = [
        row
        for row in history
        if not start_date or row.recorded_at.date() >= start_date
    ]
    if not period_rows:
        return None

    if any(_row_attr(row, "rr_delta") is not None for row in period_rows):
        diffs, plot_rows = _metadata_diffs(history, start_date)
    else:
        diffs, plot_rows = _legacy_diffs(history, start_date), period_rows

    if not diffs or len(plot_rows) < 2:
        return None

    wins = [diff for _, diff in diffs if diff > 0]
    losses = [diff for _, diff in diffs if diff < 0]

    return MmrStats(
        total_games=len(diffs),
        total_change=sum(diff for _, diff in diffs),
        avg_win=round(sum(wins) / len(wins)) if wins else 0,
        avg_loss=round(sum(losses) / len(losses)) if losses else 0,
        last_diff=diffs[-1][1],
        dates_plot=[row.recorded_at for row in plot_rows],
        elos_plot=[row.elo for row in plot_rows],
    )


def _legacy_diffs(
    history: Sequence[MmrHistoryRow],
    start_date: date | None,
) -> list[tuple[datetime, int]]:
    diffs: list[tuple[datetime, int]] = []
    for index in range(1, len(history)):
        recorded_at = history[index].recorded_at
        if start_date and recorded_at.date() < start_date:
            continue

        diff = history[index].elo - history[index - 1].elo
        diffs.append((recorded_at, diff))
    return diffs


def _metadata_diffs(
    history: Sequence[MmrHistoryRow],
    start_date: date | None,
) -> tuple[list[tuple[datetime, int]], list[MmrHistoryRow]]:
    diff_rows: list[_DiffRow] = []
    previous: MmrHistoryRow | None = None

    for row in history:
        in_period = not start_date or row.recorded_at.date() >= start_date
        if not in_period:
            previous = row
            continue

        rr_delta = _row_attr(row, "rr_delta")
        if previous is None and _row_attr(row, "source") == "legacy":
            previous = row
            continue
        if rr_delta is None and previous is not None:
            rr_delta = row.elo - previous.elo
        if rr_delta is None:
            previous = row
            continue

        if rr_delta != 0 or _row_attr(row, "match_id"):
            diff_rows.append(_DiffRow(row, rr_delta))

        previous = row

    deduped_rows = _dedupe_imported_matches_and_snapshots(diff_rows)
    diffs = [(item.row.recorded_at, item.diff) for item in deduped_rows]
    plot_rows = _metadata_plot_rows(history, start_date, deduped_rows)
    return diffs, plot_rows


def _dedupe_imported_matches_and_snapshots(diff_rows: list[_DiffRow]) -> list[_DiffRow]:
    deduped: list[_DiffRow] = []
    last_import: _DiffRow | None = None

    for item in diff_rows:
        if _row_attr(item.row, "match_id"):
            deduped.append(item)
            last_import = item
            continue

        if last_import and item.row.elo == last_import.row.elo:
            continue

        deduped.append(item)
        last_import = None

    return deduped


def _metadata_plot_rows(
    history: Sequence[MmrHistoryRow],
    start_date: date | None,
    diff_rows: list[_DiffRow],
) -> list[MmrHistoryRow]:
    if not diff_rows:
        return []

    selected_rows = [item.row for item in diff_rows]
    first_change = selected_rows[0]
    baseline = _find_plot_baseline(history, start_date, first_change)
    if baseline is not None and baseline is not first_change:
        return [baseline, *selected_rows]
    return selected_rows


def _find_plot_baseline(
    history: Sequence[MmrHistoryRow],
    start_date: date | None,
    first_change: MmrHistoryRow,
) -> MmrHistoryRow | None:
    previous: MmrHistoryRow | None = None

    for row in history:
        if row is first_change:
            if previous is not None:
                return previous
            return first_change
        if not start_date or row.recorded_at.date() >= start_date:
            previous = row

    return first_change


def _row_attr(row: MmrHistoryRow, name: str):
    return getattr(row, name, None)
