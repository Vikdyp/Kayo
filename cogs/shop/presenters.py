from __future__ import annotations

from datetime import datetime, timezone

import discord

from cogs.shop.services import ShopBundle, ShopBundleItem, ShopBundleMetadata


def build_bundle_embed(bundle: ShopBundle, metadata: ShopBundleMetadata | None) -> discord.Embed:
    name = _bundle_display_name(metadata, bundle)
    embed = discord.Embed(
        title=f"🛍️ **{name}**",
        description="**Un nouveau bundle est dispo !** 🎉",
        color=discord.Color.red(),
    )
    embed.add_field(name="💰 Prix total", value=f"**{bundle.bundle_price} VP**", inline=True)

    image_url = _best_bundle_image(metadata)
    if image_url:
        embed.set_image(url=image_url)

    embed.set_footer(text=f"⏳ Jusqu’au {_format_expiration(bundle)}")
    return embed


def build_item_embed(item: ShopBundleItem, *, whole_sale_only: bool) -> discord.Embed:
    embed = discord.Embed(title=item.name, color=discord.Color.dark_gold())

    if whole_sale_only:
        embed.add_field(
            name="⚠️ Vente groupée",
            value="Disponible uniquement en bundle complet",
            inline=False,
        )
    else:
        if item.base_price is not None:
            embed.add_field(name="💰 Prix", value=f"**{item.base_price} VP**", inline=False)
        if item.discount_percent > 0:
            discount = _format_discount(item.discount_percent)
            embed.add_field(name="🏷 Réduction", value=f"**{discount}**", inline=False)

    if item.image_url:
        embed.set_image(url=item.image_url)

    return embed


def thread_name_for_bundle(metadata: ShopBundleMetadata | None, bundle: ShopBundle) -> str:
    return f"Détails – {_bundle_display_name(metadata, bundle)}"[:100]


def _bundle_display_name(metadata: ShopBundleMetadata | None, bundle: ShopBundle) -> str:
    return metadata.display_name if metadata else bundle.bundle_uuid


def _best_bundle_image(metadata: ShopBundleMetadata | None) -> str | None:
    if metadata is None:
        return None
    return (
        metadata.display_icon_url
        or metadata.display_icon_2_url
        or metadata.vertical_promo_image_url
    )


def _format_expiration(bundle: ShopBundle) -> str:
    if bundle.expires_at:
        try:
            parsed = datetime.fromisoformat(bundle.expires_at.replace("Z", "+00:00"))
        except ValueError:
            return bundle.expires_at.split("T", maxsplit=1)[0]
        return parsed.astimezone(timezone.utc).strftime("%d/%m/%Y")

    if bundle.seconds_remaining is None:
        return "Inconnue"

    days, remainder = divmod(max(bundle.seconds_remaining, 0), 86400)
    hours = remainder // 3600
    if days:
        return f"{days}j {hours}h"
    return f"{hours}h"


def _format_discount(value: float) -> str:
    percent = value * 100 if 0 < value <= 1 else value
    if percent >= 100:
        return "Gratuit dans le bundle"
    return f"-{int(percent)}% dans le bundle"
