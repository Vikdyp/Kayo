from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from cogs.accueil.renderers import build_member_evolution_chart


@dataclass(frozen=True)
class FakeEvolutionPoint:
    date: date
    net_change: int


def test_build_member_evolution_chart_returns_png_buffer() -> None:
    today = date(2026, 5, 8)
    points = [
        FakeEvolutionPoint(today - timedelta(days=2), 1),
        FakeEvolutionPoint(today - timedelta(days=1), -2),
        FakeEvolutionPoint(today, 3),
    ]

    buffer = build_member_evolution_chart(points, current_member_count=42)

    assert buffer.getvalue().startswith(b"\x89PNG\r\n\x1a\n")
    assert len(buffer.getvalue()) > 1_000


def test_build_member_evolution_chart_rejects_empty_data() -> None:
    with pytest.raises(ValueError):
        build_member_evolution_chart([], current_member_count=42)
