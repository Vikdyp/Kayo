# cogs/accueil/renderers/member_stats_chart.py
"""Matplotlib rendering for member statistics charts."""

from __future__ import annotations

import io
from datetime import date
from typing import Protocol, Sequence

import matplotlib

matplotlib.use("Agg")

from matplotlib import ticker
import matplotlib.pyplot as plt


class EvolutionPoint(Protocol):
    date: date
    net_change: int


def build_member_evolution_chart(
    evolution_data: Sequence[EvolutionPoint],
    current_member_count: int,
) -> io.BytesIO:
    if not evolution_data:
        raise ValueError("evolution_data must not be empty")

    dates = [point.date.strftime("%d-%m") for point in evolution_data]
    net_changes = [point.net_change for point in evolution_data]

    cumulative = [0] * len(net_changes)
    cumulative[-1] = current_member_count

    for index in range(len(net_changes) - 2, -1, -1):
        cumulative[index] = cumulative[index + 1] - net_changes[index + 1]

    fig, ax = plt.subplots(figsize=(10, 5))
    x_values = range(len(dates))
    ax.plot(x_values, cumulative, marker="o", linestyle="-", color="#2ecc71", markersize=4)
    ax.fill_between(x_values, cumulative, alpha=0.3, color="#2ecc71")
    ax.set_title("Évolution du nombre de membres", fontsize=14, fontweight="bold")
    ax.set_xlabel("Date", fontsize=10)
    ax.set_ylabel("Nombre de membres", fontsize=10)
    ax.set_facecolor("#f8f9fa")
    fig.set_facecolor("#ffffff")

    if len(dates) > 15:
        step = max(1, len(dates) // 10)
        tick_positions = list(range(0, len(dates), step))
        if len(dates) - 1 not in tick_positions:
            tick_positions.append(len(dates) - 1)
    else:
        tick_positions = list(range(len(dates)))

    ax.xaxis.set_major_locator(ticker.FixedLocator(tick_positions))
    ax.set_xticklabels([dates[index] for index in tick_positions], rotation=45, ha="right")

    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=100)
    buffer.seek(0)
    plt.close(fig)
    return buffer
