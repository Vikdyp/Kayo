from __future__ import annotations

from collections.abc import Sequence

import discord

from cogs.economy.services import DailyShopItem
from database.services.economy_service import EconomyInventoryItemInfo, EconomyProfileInfo


def build_shop_embed(items: Sequence[DailyShopItem]) -> discord.Embed:
    embed = discord.Embed(title="Boutique du jour", color=discord.Color.gold())
    for item in items:
        embed.add_field(name=item.name, value=f"Prix: {item.price} pieces", inline=False)
    return embed


def build_inventory_embed(
    *,
    display_name: str,
    profile: EconomyProfileInfo,
    items: Sequence[EconomyInventoryItemInfo],
) -> discord.Embed:
    embed = discord.Embed(title=f"Inventaire de {display_name}", color=discord.Color.gold())
    embed.add_field(name="Balance", value=f"{profile.balance} pieces", inline=False)
    if not items:
        embed.add_field(name="Items", value="Aucun item", inline=False)
        return embed

    lines = [f"{item.item_name} x{item.quantity}" for item in items]
    embed.add_field(name="Items", value="\n".join(lines), inline=False)
    return embed
