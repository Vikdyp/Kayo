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

logger = logging.getLogger(__name__)

# -----------------------------
# Fonctions d'aide
# -----------------------------

async def update_roles(member: discord.Member, profile_data: dict):
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
        if bon_joueur_role:
            await member.add_roles(bon_joueur_role, reason=f"Joueur ratio={ratio:.2f} >= 1")
    else:
        if mauvais_joueur_role:
            await member.add_roles(mauvais_joueur_role, reason=f"Joueur ratio={ratio:.2f} < 1")

def get_user_rank(member: discord.Member) -> str:
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
}

def get_user_language(member: discord.Member) -> str:
    for role in member.roles:
        name = role.name
        logger.debug(f"Vérification du rôle de langue: {name}")
        if name in LANGUAGE_EMOJI:
            logger.debug(f"Rôle de langue trouvé: {name} -> {LANGUAGE_EMOJI[name]}")
            return f"{LANGUAGE_EMOJI[name]} {name}"
    logger.debug("Aucun rôle de langue correspondant trouvé.")
    return "Non spécifié"

def get_user_platform(member: discord.Member) -> str:
    possible_platforms = ["Pc", "Console"]
    for role in member.roles:
        if role.name.capitalize() in possible_platforms:
            return role.name
    return "Non spécifié"

ACTION_CHOICES = [
    app_commands.Choice(name="Signaler un utilisateur", value="report"),
    app_commands.Choice(name="Recommander un utilisateur", value="recommend"),
    app_commands.Choice(name="Afficher le profil (résumé)", value="view")
]

class Reputation(commands.Cog):
    """
    Cog pour gérer la réputation et le profil utilisateur.
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
        try:
            if not interaction.guild:
                await interaction.response.send_message("Cette commande doit être exécutée dans un serveur.", ephemeral=True)
                return

            action_lower = action.value.lower()

            if action_lower == "report":
                if user.id == interaction.user.id:
                    return await interaction.response.send_message("Vous ne pouvez pas vous signaler vous-même.", ephemeral=True)
                
                success, msg = await add_event(interaction.guild.id, interaction.user.id, user.id, 'report')
                if not success:
                    return await interaction.response.send_message(msg, ephemeral=True)
                
                await interaction.response.send_message(f"{user.mention} a été signalé pour `{reason or 'Aucune raison fournie'}`.", ephemeral=True)
                profile_data = await get_profile_data(interaction.guild.id, user.id)
                await update_roles(user, profile_data)

            elif action_lower == "recommend":
                if user.id == interaction.user.id:
                    return await interaction.response.send_message("Vous ne pouvez pas vous recommander vous-même.", ephemeral=True)
                
                success, msg = await add_event(interaction.guild.id, interaction.user.id, user.id, 'recommendation')
                if not success:
                    return await interaction.response.send_message(msg, ephemeral=True)
                
                await interaction.response.send_message(f"{user.mention} a été recommandé !", ephemeral=True)
                profile_data = await get_profile_data(interaction.guild.id, user.id)
                await update_roles(user, profile_data)

            elif action_lower == "view":
                profile_data = await get_profile_data(interaction.guild.id, user.id)
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
            await interaction.response.send_message("Une erreur est survenue lors de l'exécution de cette commande.", ephemeral=True)

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

        if genre:
            g_clean = genre.lower()
            if g_clean not in ["homme", "femme", "autre"]:
                return await interaction.followup.send("Le genre doit être 'Homme', 'Femme' ou 'Autre'.", ephemeral=True)
            genre = genre.capitalize()

        current_profile = await get_user_profile(interaction.user.id)
        updated_profile = {
            "genre": genre if genre is not None else current_profile.get("genre"),
            "valorant_tracker": tracker if tracker is not None else current_profile.get("valorant_tracker"),
            "lft": lft if lft is not None else current_profile.get("lft"),
            "note": note if note is not None else current_profile.get("note")
        }
        success = await set_user_profile(
            discord_id=interaction.user.id,
            genre=updated_profile["genre"],
            valorant_tracker=updated_profile["valorant_tracker"],
            lft=updated_profile["lft"],
            note=updated_profile["note"]
        )
        if not success:
            return await interaction.followup.send("Impossible de mettre à jour votre profil (vérifiez le lien tracker ou la présence de liens dans la note).", ephemeral=True)

        await interaction.followup.send("Profil mis à jour avec succès !", ephemeral=True)

    @app_commands.command(name="profile_show", description="Affiche le profil complet d'un joueur.")
    @app_commands.describe(member="Le joueur dont vous voulez voir le profil (par défaut: vous-même)")
    async def profile_show(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None
    ):
        await interaction.response.defer(ephemeral=True)
        if member is None:
            member = interaction.user

        rep_data = await get_profile_data(interaction.guild.id, member.id)
        reports_count = rep_data.get("reports", 0)
        recos_count = rep_data.get("recommendations", 0)
        ratio = (recos_count + 1) / (reports_count + 1)

        prof_data = await get_user_profile(member.id)
        genre = prof_data.get("genre") or "Non spécifié"
        tracker = prof_data.get("valorant_tracker") or "Aucun"
        lft = prof_data.get("lft") or "Rien"
        note = prof_data.get("note") or "Aucune"

        rank = get_user_rank(member)
        language = get_user_language(member)
        platform = get_user_platform(member)

        embed = discord.Embed(
            title=f"Profil de {member.display_name}",
            description="Voici les informations complètes du joueur :",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Signalements", value=f"`{reports_count}`", inline=True)
        embed.add_field(name="Recommandations", value=f"`{recos_count}`", inline=True)
        embed.add_field(name="Ratio", value=f"`{ratio:.2f}`", inline=True)
        embed.add_field(name="Genre", value=genre, inline=True)
        embed.add_field(name="Équipe", value=lft, inline=True)
        embed.add_field(name="Rang Actuel", value=rank, inline=True)
        embed.add_field(name="Langue & Plateforme", value=f"{language}\n{platform}", inline=True)
        tracker_str = "Aucun" if tracker == "Aucun" else f"[Voir mon Tracker]({tracker})"
        embed.add_field(name="Valorant Tracker", value=tracker_str, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="Note personnelle", value=note, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Reputation(bot))
    logger.info("Reputation Cog chargé avec succès.")
