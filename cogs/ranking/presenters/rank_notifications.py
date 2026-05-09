from __future__ import annotations


def format_top_percentile(value: float) -> str:
    if value < 1:
        return f"{value:.2f}".replace(".", ",")
    return f"{value:.0f}"


def build_rank_change_message(
    *,
    member_mention: str,
    old_rank: str,
    new_rank: str,
    top_percentile: float,
    emoji: str = "",
) -> str:
    rank_text = f"**{new_rank.capitalize()}**"
    if emoji:
        rank_text = f"{rank_text} {emoji}"

    stats = f"Tu fais partie du top {format_top_percentile(top_percentile)}% des membres !"
    if _rank_value(new_rank) < _rank_value(old_rank):
        return f"{member_mention} vient de passer {rank_text}. {stats}"
    return f"{member_mention} a derank {rank_text}. Force a toi !"


def _rank_value(rank: str) -> int:
    order = {
        "radiant": 1,
        "immortel": 2,
        "ascendant": 3,
        "diamant": 4,
        "platine": 5,
        "or": 6,
        "argent": 7,
        "bronze": 8,
        "fer": 9,
    }
    return order.get(rank, 99)
