import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime
from typing import Optional

from cogs.reputation.service.reputation_service import get_profile_data, add_event

logger = logging.getLogger('discord.reputation')

async def update_roles(member: discord.Member, profile_data: dict):
    """
    Met à jour les rôles d'un membre en fonction de son ratio (recommandations + 1) / (reports + 1).
    Si le ratio > 1, le rôle "Bon Joueur" est ajouté, sinon le rôle "Mauvais Joueur" est appliqué.
    Avant d'ajouter un nouveau rôle, les rôles existants liés à la réputation sont retirés.
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
    
    if ratio > 1:
        if bon_joueur_role:
            await member.add_roles(bon_joueur_role, reason=f"Joueur avec un ratio ({ratio:.2f}) > 1")
    elif ratio == 1:
        if bon_joueur_role:
            await member.add_roles(bon_joueur_role, reason=f"Joueur avec un ratio ({ratio:.2f}) = 1")
    else:
        if mauvais_joueur_role:
            await member.add_roles(mauvais_joueur_role, reason=f"Joueur avec un ratio ({ratio:.2f}) < 1")

# Définition des choix d'actions pour la commande
ACTION_CHOICES = [
    app_commands.Choice(name="Signaler un utilisateur", value="report"),
    app_commands.Choice(name="Recommander un utilisateur", value="recommend"),
    app_commands.Choice(name="Afficher le profil", value="view")
]

class Reputation(commands.Cog):
    """
    Cog qui gère la réputation et le profil d'un joueur via une commande slash unique.
    La commande `/reputation` permet de signaler, recommander ou afficher le profil d'un utilisateur.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def today_str(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%d")

    @app_commands.command(name="reputation", description="Gérer la réputation des joueurs.")
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
        """Exécute une action sur la réputation en fonction du choix effectué."""
        try:
            # Vérification que la commande est exécutée dans un serveur
            if not interaction.guild:
                await interaction.response.send_message("Cette commande doit être exécutée dans un serveur.", ephemeral=True)
                return

            action_lower = action.value.lower()
            
            if action_lower == "report":
                # Vérification pour empêcher l'auto-signalement
                if user.id == interaction.user.id:
                    return await interaction.response.send_message("Vous ne pouvez pas vous signaler vous-même.", ephemeral=True)

                success = await add_event(interaction.user.id, user.id, 'report')
                if not success:
                    return await interaction.response.send_message(
                        "Vous avez déjà signalé cet utilisateur aujourd'hui ou 5 fois au total.", ephemeral=True
                    )
                await interaction.response.send_message(
                    f"{user.mention} a été signalé pour `{reason or 'Aucune raison fournie'}`.", ephemeral=True
                )
                # Mise à jour des rôles du membre signalé
                profile_data = await get_profile_data(user.id)
                await update_roles(user, profile_data)

            elif action_lower == "recommend":
                # Vérification pour empêcher l'auto-recommandation
                if user.id == interaction.user.id:
                    return await interaction.response.send_message("Vous ne pouvez pas vous recommander vous-même.", ephemeral=True)

                success = await add_event(interaction.user.id, user.id, 'recommendation')
                if not success:
                    return await interaction.response.send_message(
                        "Vous avez déjà recommandé cet utilisateur aujourd'hui ou 5 fois au total.", ephemeral=True
                    )
                await interaction.response.send_message(
                    f"{user.mention} a été recommandé !", ephemeral=True
                )
                # Mise à jour des rôles du membre recommandé
                profile_data = await get_profile_data(user.id)
                await update_roles(user, profile_data)

            elif action_lower == "view":
                profile_data = await get_profile_data(user.id)
                reports_count = profile_data.get("reports", 0)
                recos_count = profile_data.get("recommendations", 0)
                ratio = (recos_count + 1) / (reports_count + 1)

                embed = discord.Embed(title=f"Profil de {user.display_name}", color=discord.Color.blue())
                embed.add_field(name="Signalements", value=str(reports_count), inline=True)
                embed.add_field(name="Recommandations", value=str(recos_count), inline=True)
                embed.add_field(name="Ratio (Reco+1)/(Report+1)", value=f"{ratio:.2f}", inline=True)

                await interaction.response.send_message(embed=embed, ephemeral=True)

            else:
                await interaction.response.send_message("Action non reconnue.", ephemeral=True)

        except Exception as e:
            logger.exception(f"Erreur dans reputation_execute pour action={action.value}: {e}")
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'exécution de cette commande.", ephemeral=True
            )

async def setup(bot: commands.Bot):
    cog = Reputation(bot)
    await bot.add_cog(cog)
    logger.info("Reputation Cog chargé avec succès.")
