from datetime import datetime, timedelta, timezone

import pytest

from cogs.ranking.renderers import build_mmr_history_chart, get_mmr_period_title


def test_build_mmr_history_chart_returns_png_buffer() -> None:
    now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
    dates = [now + timedelta(hours=index) for index in range(3)]
    elos = [1000, 1020, 1015]

    buffer = build_mmr_history_chart(dates, elos, period="today", title="Aujourd'hui")

    assert buffer.getvalue().startswith(b"\x89PNG\r\n\x1a\n")
    assert len(buffer.getvalue()) > 1_000


def test_build_mmr_history_chart_rejects_invalid_points() -> None:
    now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError):
        build_mmr_history_chart([now], [1000], period="today", title="Aujourd'hui")

    with pytest.raises(ValueError):
        build_mmr_history_chart(
            [now, now + timedelta(hours=1)],
            [1000],
            period="today",
            title="Aujourd'hui",
        )


def test_get_mmr_period_title() -> None:
    assert get_mmr_period_title("today") == "Aujourd'hui"
    assert get_mmr_period_title("week") == "7 derniers jours"
    assert get_mmr_period_title("all") == "Total"
    assert get_mmr_period_title("e9a2", season_num=9, act_num=2) == "Episode 9 • Act 2"
