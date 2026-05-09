from __future__ import annotations

import discord


def calculate_completion_percentage(*, added_count: int, completed_count: int) -> float:
    if added_count <= 0:
        return 0.0
    return round(min((completed_count / added_count) * 100, 100), 1)


def build_file_counter_embed(*, added_count: int, completed_count: int) -> discord.Embed:
    percentage = calculate_completion_percentage(
        added_count=added_count,
        completed_count=completed_count,
    )
    return discord.Embed(
        title="Suivi des fichiers",
        color=discord.Color.blue(),
        description=(
            f"**Fichiers ajoutes**: {added_count}\n"
            f"**Fichiers termines**: {completed_count}\n"
            f"**Completion**: {percentage}%"
        ),
    )
