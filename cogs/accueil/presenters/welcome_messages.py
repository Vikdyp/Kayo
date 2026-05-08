# cogs/accueil/presenters/welcome_messages.py
"""Welcome message embeds."""

from __future__ import annotations

import discord


def build_welcome_embed(
    *,
    username: str,
    rules_mention: str,
    introductions_mention: str,
    member_avatar_url: str,
    bot_avatar_url: str | None,
) -> discord.Embed:
    embed = discord.Embed(
        title="🎉 Bienvenue sur le serveur ! 🎉",
        description=(
            f"Salut **{username}** ! Nous sommes ravis de t'accueillir parmi nous. 🎉\n\n"
            "Pour bien démarrer, voici quelques informations importantes :\n"
            f"• **Règles du serveur** : Assure-toi de lire {rules_mention}.\n"
            f"• **Découvre le serveur** : Va dans {introductions_mention} pour en apprendre davantage sur notre communauté.\n\n"
        ),
        color=discord.Color.blue(),
    )
    embed.set_thumbnail(url=member_avatar_url)
    if bot_avatar_url:
        embed.set_footer(
            text="N'hésite pas à demander de l'aide si tu as des questions !",
            icon_url=bot_avatar_url,
        )
    return embed
