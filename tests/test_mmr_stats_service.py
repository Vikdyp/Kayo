from datetime import date, datetime, timezone
from types import SimpleNamespace

from cogs.ranking.services.mmr_stats_service import calculate_mmr_stats, parse_mmr_period


def _row(day: int, elo: int) -> SimpleNamespace:
    return SimpleNamespace(recorded_at=datetime(2026, 5, day, tzinfo=timezone.utc), elo=elo)


def test_parse_mmr_period_standard_values() -> None:
    today = date(2026, 5, 8)

    assert parse_mmr_period(None, today=today).start_date == today
    assert parse_mmr_period("week", today=today).start_date == date(2026, 5, 1)
    assert parse_mmr_period("all", today=today).start_date is None


def test_parse_mmr_period_episode_act() -> None:
    selection = parse_mmr_period("e9a2", today=date(2026, 5, 8))

    assert selection.period == "e9a2"
    assert selection.season_num == 9
    assert selection.act_num == 2
    assert selection.start_date is None


def test_calculate_mmr_stats_filters_and_calculates_diffs() -> None:
    stats = calculate_mmr_stats(
        [_row(6, 100), _row(7, 120), _row(8, 110), _row(8, 140)],
        start_date=date(2026, 5, 7),
    )

    assert stats is not None
    assert stats.total_games == 3
    assert stats.total_change == 40
    assert stats.avg_win == 25
    assert stats.avg_loss == -10
    assert stats.last_diff == 30
    assert stats.elos_plot == [120, 110, 140]


def test_calculate_mmr_stats_returns_none_without_enough_filtered_points() -> None:
    stats = calculate_mmr_stats(
        [_row(6, 100), _row(7, 120)],
        start_date=date(2026, 5, 7),
    )

    assert stats is None
