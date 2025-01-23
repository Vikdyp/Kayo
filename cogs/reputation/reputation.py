# cogs/reputation/reputation.py

import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional
from datetime import datetime

# Import des services
from .service.reputation_service import (
    get_profile_data,
    add_event
)
from .service.profile_service import (
    get_user_profile,
    set_user_profile
)

logger = logging.getLogger("discord.reputation")

# -----------------------------
# Fonctions d'aide
# -----------------------------

async def update_roles(member: discord.Member, profile_data: dict):
    """
    Met à jour les rôles d'un membre en fonction de son ratio (reco+1)/(report+1).
    - Supprime "Bon Joueur" et "Mauvais Joueur" si existants.
    - Si ratio > 1 => Bon Joueur
    - Si ratio = 1 => Bon Joueur (ou rien, au choix)
    - Si ratio < 1 => Mauvais Joueur
    """
    reports_count = profile_data.get("reports", 0)
    recos_count = profile_data.get("recommendations", 0)
    ratio = (recos_count + 1) / (reports_count + 1)
    guild = member.guild

    bon_joueur_role = discord.utils.get(guild.roles, name="Bon Joueur")
    mauvais_joueur_role = discord.utils.get(guild.roles, name="Mauvais Joueur")

    roles_to_remove = []
    if bon_joueur_role in member.roles:
        roles_to_remove.append(bon_joueur_role)
    if mauvais_joueur_role in member.roles:
        roles_to_remove.append(mauvais_joueur_role)

    if roles_to_remove:
        await member.remove_roles(*roles_to_remove, reason="Mise à jour du profil de réputation")

    if ratio >= 1:
        # On considère >=1 => "Bon Joueur"
        if bon_joueur_role:
            await member.add_roles(bon_joueur_role, reason=f"Joueur ratio={ratio:.2f} >= 1")
    else:
        # ratio < 1 => "Mauvais Joueur"
        if mauvais_joueur_role:
            await member.add_roles(mauvais_joueur_role, reason=f"Joueur ratio={ratio:.2f} < 1")

def get_user_rank(member: discord.Member) -> str:
    """
    Exemple: On cherche parmi les rôles du joueur un rang officiel (Fer, Bronze, Argent, etc.).
    """
    rank_roles = ["Fer", "Bronze", "Argent", "Or", "Platine",
                  "Diamant", "Ascendant", "Immortel", "Radiant"]
    for role in member.roles:
        if role.name in rank_roles:
            return role.name
    return "Inconnu"

LANGUAGE_EMOJI = {
    "Français": "🇫🇷",
    "English": "🇬🇧",
    "Español": "🇪🇸",
    # Ajoutez si besoin
}

def get_user_language(member: discord.Member) -> str:
    """
    Ex : on cherche un rôle "Français", "English", "Español", etc. et on lui associe un emoji.
    """
    for role in member.roles:
        name = role.name  # Utiliser le nom exact sans le convertir
        logger.debug(f"Vérification du rôle de langue: {name}")
        if name in LANGUAGE_EMOJI:
            logger.debug(f"Rôle de langue trouvé: {name} -> {LANGUAGE_EMOJI[name]}")
            return f"{LANGUAGE_EMOJI[name]} {name}"
    logger.debug("Aucun rôle de langue correspondant trouvé.")
    return "Non spécifié"

def get_user_platform(member: discord.Member) -> str:
    """
    Ex : on cherche "Pc", "Console", etc.
    """
    possible_platforms = ["Pc", "Console"]
    for role in member.roles:
        if role.name.capitalize() in possible_platforms:
            return role.name
    return "Non spécifié"

# Choix d'actions pour la commande /reputation
ACTION_CHOICES = [
    app_commands.Choice(name="Signaler un utilisateur", value="report"),
    app_commands.Choice(name="Recommander un utilisateur", value="recommend"),
    app_commands.Choice(name="Afficher le profil (résumé)", value="view")
]

class Reputation(commands.Cog):
    """
    Cog pour gérer :
    - La réputation (reports/recommendations).
    - Le profil utilisateur (genre, tracker, etc.).
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="reputation", description="Gérer la réputation des joueurs (report/reco/view).")
    @app_commands.describe(
        action="Action à effectuer",
        user="Utilisateur concerné",
        reason="Raison du signalement (uniquement pour 'report')"
    )
    @app_commands.choices(action=ACTION_CHOICES)
    async def reputation_execute(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        user: discord.Member,
        reason: Optional[str] = None
    ):
        """
        /reputation <report|recommend|view> <@user> [reason?]
        """
        try:
            if not interaction.guild:
                await interaction.response.send_message("Cette commande doit être exécutée dans un serveur.", ephemeral=True)
                return

            action_lower = action.value.lower()

            if action_lower == "report":
                # Empêcher l'auto-signalement
                if user.id == interaction.user.id:
                    return await interaction.response.send_message("Vous ne pouvez pas vous signaler vous-même.", ephemeral=True)

                success = await add_event(interaction.user.id, user.id, 'report')
                if not success:
                    return await interaction.response.send_message(
                        "Vous avez déjà signalé cet utilisateur aujourd'hui ou 5 fois au total.",
                        ephemeral=True
                    )
                await interaction.response.send_message(
                    f"{user.mention} a été signalé pour `{reason or 'Aucune raison fournie'}`.",
                    ephemeral=True
                )

                # Mise à jour des rôles
                profile_data = await get_profile_data(user.id)
                await update_roles(user, profile_data)

            elif action_lower == "recommend":
                # Empêcher l'auto-reco
                if user.id == interaction.user.id:
                    return await interaction.response.send_message("Vous ne pouvez pas vous recommander vous-même.", ephemeral=True)

                success = await add_event(interaction.user.id, user.id, 'recommendation')
                if not success:
                    return await interaction.response.send_message(
                        "Vous avez déjà recommandé cet utilisateur aujourd'hui ou 5 fois au total.",
                        ephemeral=True
                    )
                await interaction.response.send_message(
                    f"{user.mention} a été recommandé !",
                    ephemeral=True
                )

                # Mise à jour des rôles
                profile_data = await get_profile_data(user.id)
                await update_roles(user, profile_data)

            elif action_lower == "view":
                # Affiche un résumé "rapide" (si vous voulez)
                profile_data = await get_profile_data(user.id)
                reports_count = profile_data.get("reports", 0)
                recos_count = profile_data.get("recommendations", 0)
                ratio = (recos_count + 1) / (reports_count + 1)

                embed = discord.Embed(
                    title=f"Profil (résumé) de {user.display_name}",
                    color=discord.Color.blue()
                )
                embed.set_thumbnail(url=user.display_avatar.url)
                embed.add_field(name="Signalements", value=str(reports_count), inline=True)
                embed.add_field(name="Recommandations", value=str(recos_count), inline=True)
                embed.add_field(name="Ratio (Reco+1 / Report+1)", value=f"{ratio:.2f}", inline=True)

                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message("Action non reconnue.", ephemeral=True)

        except Exception as e:
            logger.exception(f"Erreur dans reputation_execute pour action={action.value}: {e}")
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'exécution de cette commande.",
                ephemeral=True
            )

    # ----------------------------------------------------------------
    # Commande pour paramétrer le profil
    # ----------------------------------------------------------------
    @app_commands.command(name="profile_set", description="Paramètre votre profil Valorant (genre, tracker, LFT...).")
    @app_commands.describe(
        genre="Votre genre (Homme, Femme ou Autre)",
        tracker="Lien tracker.gg (format: https://tracker.gg/valorant/profile/riot/.../overview)",
        lft="'LFT', 'Rien' ou le nom de votre équipe",
        note="Un champ libre (sans lien)."
    )
    async def profile_set(
        self,
        interaction: discord.Interaction,
        genre: Optional[str],
        tracker: Optional[str],
        lft: Optional[str],
        note: Optional[str]
    ):
        await interaction.response.defer(ephemeral=True)

        # Vérification du genre
        if genre:
            g_clean = genre.lower()
            if g_clean not in ["homme", "femme", "autre"]:
                return await interaction.followup.send(
                    "Le genre doit être 'Homme', 'Femme' ou 'Autre'.",
                    ephemeral=True
                )
            genre = genre.capitalize()  # pour la cohérence en BDD

        # Récupérer les données actuelles du profil
        current_profile = await get_user_profile(interaction.user.id)
        logger.debug(f"Profil actuel de l'utilisateur {interaction.user.id}: {current_profile}")

        # Fusionner les nouvelles données avec les données existantes
        updated_profile = {
            "genre": genre if genre is not None else current_profile.get("genre"),
            "valorant_tracker": tracker if tracker is not None else current_profile.get("valorant_tracker"),
            "lft": lft if lft is not None else current_profile.get("lft"),
            "note": note if note is not None else current_profile.get("note")
        }
        logger.debug(f"Profil mis à jour de l'utilisateur {interaction.user.id}: {updated_profile}")

        # Appel au service avec les données fusionnées
        success = await set_user_profile(
            discord_id=interaction.user.id,
            genre=updated_profile["genre"],
            valorant_tracker=updated_profile["valorant_tracker"],
            lft=updated_profile["lft"],
            note=updated_profile["note"]
        )
        if not success:
            return await interaction.followup.send(
                "Impossible de mettre à jour votre profil (vérifiez le lien tracker ou la présence de liens dans la note).",
                ephemeral=True
            )

        await interaction.followup.send("Profil mis à jour avec succès !", ephemeral=True)

    # ----------------------------------------------------------------
    # Commande pour afficher le profil complet
    # ----------------------------------------------------------------
    @app_commands.command(name="profile_show", description="Affiche le profil complet d'un joueur.")
    @app_commands.describe(
        member="Le joueur dont vous voulez voir le profil (par défaut: vous-même)"
    )
    async def profile_show(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None
    ):
        await interaction.response.defer(ephemeral=True)
        if member is None:
            member = interaction.user

        # 1) Données reputation
        rep_data = await get_profile_data(member.id)
        reports_count = rep_data.get("reports", 0)
        recos_count = rep_data.get("recommendations", 0)
        ratio = (recos_count + 1) / (reports_count + 1)

        # 2) Données profil perso (genre, tracker, LFT, note)
        prof_data = await get_user_profile(member.id)
        genre = prof_data.get("genre") or "Non spécifié"
        tracker = prof_data.get("valorant_tracker") or "Aucun"
        lft = prof_data.get("lft") or "Rien"
        note = prof_data.get("note") or "Aucune"

        # 3) Rang, Langue, Plateforme via rôles
        rank = get_user_rank(member)
        language = get_user_language(member)
        platform = get_user_platform(member)

        # 4) Embed joliment mis en page
        embed = discord.Embed(
            title=f"Profil de {member.display_name}",
            description="Voici les informations complètes du joueur :",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        # Ligne 1 : Réputation (inline pour avoir un petit tableau)
        embed.add_field(
            name="Signalements",
            value=f"`{reports_count}`",
            inline=True
        )
        embed.add_field(
            name="Recommandations",
            value=f"`{recos_count}`",
            inline=True
        )
        embed.add_field(
            name="Ratio",
            value=f"`{ratio:.2f}`",
            inline=True
        )

        # Ligne 2 : Genre - LFT - Rang
        embed.add_field(
            name="Genre",
            value=genre,
            inline=True
        )
        embed.add_field(
            name="Équipe",
            value=lft,
            inline=True
        )
        embed.add_field(
            name="Rang Actuel",
            value=rank,
            inline=True
        )

        # Ligne 3 : Langue & Plateforme (groupées dans un même field pour harmoniser)
        embed.add_field(
            name="Langue & Plateforme",
            value=f"{language}\n{platform}",
            inline=True
        )

        # Tracker (format lien cliquable si != 'Aucun')
        if tracker == "Aucun":
            tracker_str = "Aucun"
        else:
            tracker_str = f"[Voir mon Tracker]({tracker})"
        embed.add_field(
            name="Valorant Tracker",
            value=tracker_str,
            inline=True
        )

        # On peut laisser la 3e colonne vide pour l'alignement
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        # Note personnelle en bas (large)
        embed.add_field(
            name="Note personnelle",
            value=note,
            inline=False
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

# -------------------------------------------
# Setup du Cog
# -------------------------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Reputation(bot))
    logger.info("Reputation Cog chargé avec succès.")