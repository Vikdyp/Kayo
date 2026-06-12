# cogs/ranking/services/mmr_stats_service.py
"""Pure MMR history period parsing and stat calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
from typing import Protocol, Sequence
from zoneinfo import ZoneInfo


PARIS_TZ = ZoneInfo("Europe/Paris")


class MmrHistoryRow(Protocol):
    recorded_at: datetime
    elo: int


@dataclass(frozen=True)
class _DiffRow:
    row: MmrHistoryRow
    diff: int


@dataclass(frozen=True)
class _SyntheticPlotRow:
    recorded_at: datetime
    elo: int


@dataclass(frozen=True)
class MmrPeriodSelection:
    period: str
    season_num: int | None
    act_num: int | None
    start_date: date | None
    start_at: datetime | None = None


@dataclass(frozen=True)
class MmrStats:
    total_games: int
    total_change: int
    avg_win: int
    avg_loss: int
    last_diff: int
    dates_plot: list[datetime]
    elos_plot: list[int]


def parse_mmr_period(
    period: str | None,
    *,
    today: date | None = None,
    now: datetime | None = None,
) -> MmrPeriodSelection:
    selected_period = period or "today"
    reference_now = _reference_now(now)
    reference_day = today or reference_now.date()

    if selected_period == "today":
        if today is not None:
            return MmrPeriodSelection(selected_period, None, None, reference_day)
        return MmrPeriodSelection(
            selected_period,
            None,
            None,
            None,
            datetime.combine(reference_day, time.min, tzinfo=PARIS_TZ),
        )
    if selected_period == "week":
        if today is not None:
            return MmrPeriodSelection(selected_period, None, None, reference_day - timedelta(days=7))
        return MmrPeriodSelection(selected_period, None, None, None, reference_now - timedelta(days=7))
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
    start_date: date | None = None,
    start_at: datetime | None = None,
) -> MmrStats | None:
    period_rows = [
        row
        for row in history
        if _is_in_period(row, start_date, start_at)
    ]
    if not period_rows:
        return None

    if any(_row_attr(row, "rr_delta") is not None for row in period_rows):
        diffs, plot_rows = _metadata_diffs(history, start_date, start_at)
    else:
        diffs, plot_rows = _legacy_diffs(history, start_date, start_at), period_rows

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
    start_at: datetime | None,
) -> list[tuple[datetime, int]]:
    diffs: list[tuple[datetime, int]] = []
    for index in range(1, len(history)):
        recorded_at = history[index].recorded_at
        if not _is_in_period(history[index], start_date, start_at):
            continue

        diff = history[index].elo - history[index - 1].elo
        diffs.append((recorded_at, diff))
    return diffs


def _metadata_diffs(
    history: Sequence[MmrHistoryRow],
    start_date: date | None,
    start_at: datetime | None,
) -> tuple[list[tuple[datetime, int]], list[MmrHistoryRow]]:
    diff_rows: list[_DiffRow] = []
    previous: MmrHistoryRow | None = None

    for row in history:
        in_period = _is_in_period(row, start_date, start_at)
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
    plot_rows = _metadata_plot_rows(history, start_date, start_at, deduped_rows)
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
    start_at: datetime | None,
    diff_rows: list[_DiffRow],
) -> list[MmrHistoryRow]:
    if not diff_rows:
        return []

    selected_rows = [item.row for item in diff_rows]
    first_change = selected_rows[0]
    baseline = _find_plot_baseline(history, start_date, start_at, first_change)
    if baseline is not None and baseline is not first_change:
        return [baseline, *selected_rows]
    boundary_baseline = _period_boundary_baseline(diff_rows[0], start_at)
    if boundary_baseline is not None:
        return [boundary_baseline, *selected_rows]
    imported_baseline = _imported_plot_baseline(diff_rows[0])
    if imported_baseline is not None:
        return [imported_baseline, *selected_rows]
    return selected_rows


def _find_plot_baseline(
    history: Sequence[MmrHistoryRow],
    start_date: date | None,
    start_at: datetime | None,
    first_change: MmrHistoryRow,
) -> MmrHistoryRow | None:
    previous: MmrHistoryRow | None = None

    for row in history:
        if row is first_change:
            if previous is not None:
                return previous
            return first_change
        if _is_in_period(row, start_date, start_at):
            previous = row

    return first_change


def _period_boundary_baseline(diff_row: _DiffRow, start_at: datetime | None) -> _SyntheticPlotRow | None:
    if start_at is None or diff_row.row.recorded_at <= start_at:
        return None
    return _SyntheticPlotRow(
        recorded_at=start_at,
        elo=diff_row.row.elo - diff_row.diff,
    )


def _imported_plot_baseline(diff_row: _DiffRow) -> _SyntheticPlotRow | None:
    if not _row_attr(diff_row.row, "match_id"):
        return None
    return _SyntheticPlotRow(
        recorded_at=diff_row.row.recorded_at - timedelta(seconds=1),
        elo=diff_row.row.elo - diff_row.diff,
    )


def _row_attr(row: MmrHistoryRow, name: str):
    return getattr(row, name, None)


def _reference_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(PARIS_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=PARIS_TZ)
    return now.astimezone(PARIS_TZ)


def _is_in_period(row: MmrHistoryRow, start_date: date | None, start_at: datetime | None) -> bool:
    if start_at is not None:
        return _recorded_at_for_compare(row.recorded_at, start_at) >= start_at
    return not start_date or row.recorded_at.date() >= start_date


def _recorded_at_for_compare(recorded_at: datetime, start_at: datetime) -> datetime:
    if recorded_at.tzinfo is None and start_at.tzinfo is not None:
        return recorded_at.replace(tzinfo=start_at.tzinfo)
    if recorded_at.tzinfo is not None and start_at.tzinfo is None:
        return recorded_at.replace(tzinfo=None)
    return recorded_at
