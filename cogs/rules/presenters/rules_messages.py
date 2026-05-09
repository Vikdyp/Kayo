from __future__ import annotations

from typing import Optional

import discord


def build_rules_embed(*, bot_avatar_url: Optional[str]) -> discord.Embed:
    embed = discord.Embed(
        title="Reglement du Serveur",
        color=discord.Color.green(),
    )
    embed.add_field(
        name="1. Respect et courtoisie",
        value=(
            "> - Traitez tous les membres avec respect.\n"
            "> - Utilisez un langage adapte et evitez les provocations.\n"
            "> - Les propos discriminatoires, haineux ou agressifs sont interdits.\n"
            "> - En cas de conflit, contactez le staff plutot que d'alimenter la tension."
        ),
        inline=False,
    )
    embed.add_field(
        name="2. Contenu interdit",
        value=(
            "> - Aucun contenu NSFW, violent ou choquant.\n"
            "> - Harcelement, intimidation et spam sont interdits.\n"
            "> - Signalez tout contenu problematique a un moderateur."
        ),
        inline=False,
    )
    embed.add_field(
        name="3. Equipe de moderation",
        value=(
            "> - Respectez les decisions du staff.\n"
            "> - Les contestations doivent rester privees et courtoises.\n"
            "> - Votre cooperation aide a garder une bonne ambiance."
        ),
        inline=False,
    )
    embed.add_field(
        name="4. Utilisation des salons",
        value=(
            "> - Chaque salon a une vocation precise.\n"
            "> - Evitez les hors-sujets et l'abus des salons dedies.\n"
            "> - Suivez les demandes des moderateurs si une discussion doit etre deplacee."
        ),
        inline=False,
    )
    embed.add_field(
        name="5. Publicite et promotion",
        value=(
            "> - Toute publicite non autorisee est interdite.\n"
            "> - Les promotions doivent etre validees par l'administration.\n"
            "> - Les messages promotionnels non autorises seront supprimes."
        ),
        inline=False,
    )
    embed.set_footer(
        text=(
            "En cliquant sur 'Accepter le reglement', vous acceptez les conditions "
            "du serveur. Contactez le staff si vous avez des questions."
        ),
        icon_url=bot_avatar_url,
    )
    return embed
