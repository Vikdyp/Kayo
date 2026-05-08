# cogs/ranking/renderers/mmr_history_chart.py
"""Matplotlib rendering for MMR history charts."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Sequence

from matplotlib.collections import LineCollection
from matplotlib.patches import PathPatch
from matplotlib.path import Path
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np


def get_mmr_period_title(
    period: str,
    season_num: int | None = None,
    act_num: int | None = None,
) -> str:
    return {
        "today": "Aujourd'hui",
        "week": "7 derniers jours",
        "all": "Total",
    }.get(period, f"Episode {season_num} • Act {act_num}")


def build_mmr_history_chart(
    dates_plot: Sequence[datetime],
    elos_plot: Sequence[int],
    *,
    period: str,
    title: str,
) -> io.BytesIO:
    if len(dates_plot) < 2 or len(elos_plot) < 2:
        raise ValueError("MMR history chart requires at least two points")
    if len(dates_plot) != len(elos_plot):
        raise ValueError("dates_plot and elos_plot must have the same length")

    mpl_dates = mdates.date2num(dates_plot)
    cmap_fill = "Greens" if elos_plot[-1] > elos_plot[0] else "Reds"

    points = np.array([mpl_dates, elos_plot]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    segment_colors = [
        "green" if elos_plot[index + 1] > elos_plot[index] else "red"
        for index in range(len(elos_plot) - 1)
    ]

    buffer = io.BytesIO()
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(10, 4), dpi=150)

    ymin = min(elos_plot) - 10
    gradient = np.linspace(1, 0, 256).reshape(256, 1)
    image = ax.imshow(
        gradient,
        extent=[mpl_dates.min(), mpl_dates.max(), ymin, max(elos_plot)],
        origin="lower",
        cmap=plt.get_cmap(cmap_fill),
        alpha=0.5,
        aspect="auto",
        zorder=1,
    )
    polygon = np.vstack(
        [
            [mpl_dates[0], ymin],
            np.column_stack([mpl_dates, elos_plot]),
            [mpl_dates[-1], ymin],
            [mpl_dates[0], ymin],
        ]
    )
    image.set_clip_path(PathPatch(Path(polygon), transform=ax.transData))

    line_collection = LineCollection(segments, colors=segment_colors, linewidths=2.5, zorder=3)
    ax.add_collection(line_collection)

    for segment, color in zip(segments, segment_colors):
        ax.plot(
            segment[:, 0],
            segment[:, 1],
            linewidth=8,
            solid_capstyle="round",
            color=color,
            alpha=0.2,
            zorder=2,
        )

    date_format = "%H:%M" if period == "today" else "%Y-%m-%d"
    ax.xaxis.set_major_formatter(mdates.DateFormatter(date_format))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.set_title(f"Évolution MMR ({title})", fontsize=14, fontweight="bold")
    ax.set_xlabel("Heure" if period != "all" else "Date", fontsize=12)
    ax.set_ylabel("ELO", fontsize=12)

    ax.grid(False)
    ax.xaxis.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylim(ymin, max(elos_plot) + 10)

    fig.tight_layout()
    fig.savefig(buffer, format="png")
    buffer.seek(0)
    plt.close(fig)
    return buffer
