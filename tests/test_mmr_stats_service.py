from datetime import date, datetime, timezone
from types import SimpleNamespace

from cogs.ranking.services.mmr_stats_service import calculate_mmr_stats, parse_mmr_period


def _row(day: int, elo: int, **metadata) -> SimpleNamespace:
    return SimpleNamespace(
        recorded_at=datetime(2026, 5, day, tzinfo=timezone.utc),
        elo=elo,
        **metadata,
    )


def _row_at(hour: int, minute: int, elo: int, **metadata) -> SimpleNamespace:
    return SimpleNamespace(
        recorded_at=datetime(2026, 5, 8, hour, minute, tzinfo=timezone.utc),
        elo=elo,
        **metadata,
    )


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


def test_calculate_mmr_stats_prefers_henrik_matches_over_tracker_snapshots() -> None:
    history = [
        _row_at(10, 0, 1010, match_id="m1", rr_delta=10, source="henrik_live"),
        _row_at(10, 5, 1010, rr_delta=10, source="tracker_snapshot"),
        _row_at(11, 0, 1000, match_id="m2", rr_delta=-10, source="henrik_live"),
        _row_at(11, 5, 1000, rr_delta=-10, source="tracker_snapshot"),
        _row_at(12, 0, 1025, match_id="m3", rr_delta=25, source="henrik_live"),
        _row_at(12, 5, 1025, rr_delta=25, source="tracker_snapshot"),
        _row_at(13, 0, 1041, match_id="m4", rr_delta=16, source="henrik_live"),
        _row_at(13, 5, 1041, rr_delta=16, source="tracker_snapshot"),
    ]

    stats = calculate_mmr_stats(history, start_date=date(2026, 5, 8))

    assert stats is not None
    assert stats.total_games == 4
    assert stats.total_change == 41
    assert stats.avg_win == 17
    assert stats.avg_loss == -10
    assert stats.last_diff == 16
    assert stats.elos_plot == [1010, 1000, 1025, 1041]


def test_calculate_mmr_stats_keeps_tracker_snapshots_after_imports() -> None:
    history = [
        _row_at(10, 0, 1010, match_id="m1", rr_delta=10, source="henrik_live"),
        _row_at(10, 5, 1010, rr_delta=10, source="tracker_snapshot"),
        _row_at(11, 0, 1030, rr_delta=20, source="tracker_snapshot"),
    ]

    stats = calculate_mmr_stats(history, start_date=date(2026, 5, 8))

    assert stats is not None
    assert stats.total_games == 2
    assert stats.total_change == 30
    assert stats.elos_plot == [1010, 1030]


def test_calculate_mmr_stats_dedupes_aggregated_tracker_snapshot_after_imports() -> None:
    history = [
        _row_at(10, 0, 1010, match_id="m1", rr_delta=10, source="henrik_live"),
        _row_at(10, 30, 1025, match_id="m2", rr_delta=15, source="henrik_live"),
        _row_at(11, 0, 1025, rr_delta=25, source="tracker_snapshot"),
    ]

    stats = calculate_mmr_stats(history, start_date=date(2026, 5, 8))

    assert stats is not None
    assert stats.total_games == 2
    assert stats.total_change == 25
    assert stats.elos_plot == [1010, 1025]


def test_calculate_mmr_stats_ignores_first_filtered_legacy_delta() -> None:
    stats = calculate_mmr_stats(
        [
            _row(7, 1000, rr_delta=35, source="legacy"),
            _row(8, 1015, rr_delta=15, source="legacy"),
        ],
        start_date=None,
    )

    assert stats is not None
    assert stats.total_games == 1
    assert stats.total_change == 15
    assert stats.elos_plot == [1000, 1015]


def test_calculate_mmr_stats_keeps_baseline_for_single_metadata_change() -> None:
    stats = calculate_mmr_stats(
        [
            _row(7, 1000, rr_delta=None, source="legacy"),
            _row(8, 1020, rr_delta=20, source="legacy"),
        ],
        start_date=None,
    )

    assert stats is not None
    assert stats.total_games == 1
    assert stats.total_change == 20
    assert stats.elos_plot == [1000, 1020]


def test_calculate_mmr_stats_returns_none_without_enough_filtered_points() -> None:
    stats = calculate_mmr_stats(
        [_row(6, 100), _row(7, 120)],
        start_date=date(2026, 5, 7),
    )

    assert stats is None
