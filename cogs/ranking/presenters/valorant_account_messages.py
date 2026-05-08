# cogs/ranking/presenters/valorant_account_messages.py
"""Embeds and display messages for Valorant account linking."""

from __future__ import annotations

from datetime import datetime

import discord


def build_valorant_account_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Gestion de vos informations Valorant",
        description=(
            "Ce message vous permet de **renseigner**, **changer** ou **effacer** "
            "vos donnees Valorant.\n\n"
            "**Instructions :**\n"
            "1. Cliquez sur le bouton bleu pour lier votre compte Valorant.\n"
            "2. Un formulaire s'ouvrira ou vous devrez entrer :\n"
            "   - **Pseudo** : Votre pseudo Valorant (exemple : `globeX`).\n"
            "   - **Tag** : Votre tag Valorant sans le `#` (exemple : `meow`).\n\n"
            "3. Pour changer de compte, utilisez le bouton gris.\n\n"
            "*Note : Vous devez d'abord accepter le reglement.*\n"
        ),
        color=discord.Color.blue(),
    )
    embed.set_footer(text="Tenez a jour vos informations pour obtenir le role correspondant a votre rang.")
    return embed


def build_duplicate_pseudo_tag_embed(
    *,
    existing_user_mention: str,
    existing_user_id: int,
    current_user_mention: str,
    current_user_id: int,
    pseudo: str,
    tag: str,
    timestamp: datetime,
) -> discord.Embed:
    embed = discord.Embed(
        title="Doublon de Pseudo Valorant Detecte",
        description=(
            f"Un doublon a ete detecte pour le pseudo et tag Valorant : **{pseudo}#{tag}**.\n\n"
            f"**Utilisateur 1 :** {existing_user_mention} (ID: {existing_user_id})\n"
            f"**Utilisateur 2 :** {current_user_mention} (ID: {current_user_id})\n\n"
            "Veuillez resoudre ce doublon."
        ),
        color=discord.Color.red(),
        timestamp=timestamp,
    )
    embed.set_footer(text="Gestion des Doublons de Pseudo Valorant")
    return embed


def format_valorant_update_error_message(
    *,
    pseudo: str,
    tag: str,
    error_message: str | None,
    rank_channel_mention: str,
) -> str:
    return (
        "La recuperation de vos informations Valorant a echoue pour "
        f"**{pseudo}#{tag}**.\n"
        f"Erreur: {error_message or 'Inconnue'}\n\n"
        "Veuillez verifier vos identifiants ou modifier vos informations "
        f"dans {rank_channel_mention}."
    )
