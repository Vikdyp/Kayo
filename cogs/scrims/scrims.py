# cogs/scrims/scrims.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from cogs.utilities.data_manager import DataManager
from cogs.utilities.request_manager import enqueue_request
from cogs.utilities.permission_manager import is_admin
from cogs.utilities.confirmation_view import PurgeConfirmationView

logger = logging.getLogger("discord.scrims")

VALID_MAPS = ["SUNSET", "LOTUS", "PEARL", "FRACTURE", "BREEZE", "ICEBOX", "BIND", "HAVEN", "SPLIT", "ASCENT"]

class Scrims(commands.Cog):
    """Cog pour la gestion des scrims et des équipes."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.config: Dict[str, Any] = {}
        self.scrims_data: Dict[str, Any] = {}
        self.teams_data: Dict[str, Any] = {}
        self.tournaments_data: Dict[str, Any] = {}
        self.leaderboard_data: Dict[str, Any] = {}
        self.bot.loop.create_task(self.load_all_data())

    async def load_all_data(self):
        self.config = await self.data.get_config()
        self.scrims_data = await self.data.get_scrims_data()
        self.teams_data = await self.data.get_teams_data()
        self.tournaments_data = await self.data.get_tournaments_data()
        self.leaderboard_data = await self.data.get_leaderboard_data()
        logger.info("Scrims: toutes les données chargées.")

    async def save_all_data(self):
        await self.data.save_config(self.config)
        await self.data.save_scrims_data(self.scrims_data)
        await self.data.save_teams_data(self.teams_data)
        await self.data.save_tournaments_data(self.tournaments_data)
        await self.data.save_leaderboard_data(self.leaderboard_data)
        logger.info("Scrims: toutes les données sauvegardées.")

    async def ask_confirmation(self, interaction: discord.Interaction, message: str):
        view = PurgeConfirmationView(interaction, None)
        await interaction.response.send_message(message, view=view, ephemeral=True)
        await view.wait()
        return view.value

    def is_user_in_team(self, user_id: int) -> bool:
        for team_key, team_info in self.teams_data.items():
            if user_id in team_info["players"] or team_info.get("sub") == user_id or team_info.get("coach") == user_id:
                return True
        return False

    # ---------- Commande /create_team ----------
    @app_commands.command(name="create_team", description="Créer une équipe")
    @app_commands.describe(
        team_name="Nom de l'équipe",
        user1="Joueur 1",
        user2="Joueur 2",
        user3="Joueur 3",
        user4="Joueur 4",
        user5="Joueur 5",
        sub="Remplaçant (optionnel)",
        coach="Coach (optionnel)"
    )
    @enqueue_request()
    async def create_team(
        self,
        interaction: discord.Interaction,
        team_name: str,
        user1: discord.Member,
        user2: discord.Member,
        user3: discord.Member,
        user4: discord.Member,
        user5: discord.Member,
        sub: Optional[discord.Member] = None,
        coach: Optional[discord.Member] = None
    ):
        await interaction.response.defer(ephemeral=True)
        team_members = [user1, user2, user3, user4, user5]
        if sub:
            team_members.append(sub)
        if coach:
            team_members.append(coach)

        # Vérifier que personne n'est déjà dans une autre équipe
        for member in team_members:
            if self.is_user_in_team(member.id):
                return await interaction.followup.send(f"{member.mention} est déjà dans une autre équipe.", ephemeral=True)

        # Demander confirmation à chaque membre (sauf le coach, éventuellement)
        # On part du principe que sub et coach doivent aussi confirmer
        for member in team_members:
            try:
                view = PurgeConfirmationView(interaction, None)
                await member.send(f"{interaction.user.display_name} vous propose de rejoindre l'équipe '{team_name}'. Confirmez-vous ?", view=view)
                await view.wait()
                if not view.value:
                    return await interaction.followup.send(f"{member.mention} a refusé de rejoindre l'équipe.", ephemeral=True)
            except discord.Forbidden:
                return await interaction.followup.send(f"Impossible d'envoyer un message à {member.mention}.", ephemeral=True)
            except Exception as e:
                logger.exception(f"Erreur lors de la demande de confirmation à {member.display_name}: {e}")
                return await interaction.followup.send("Erreur lors de la demande de confirmation.", ephemeral=True)

        # Tous ont confirmé
        if not await self.ask_confirmation(interaction, f"Confirmez-vous la création de l'équipe '{team_name}' ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)

        # Créer l'équipe
        team_id = len(self.teams_data) + 1
        team_key = f"team_{team_id}"
        players = [user1.id, user2.id, user3.id, user4.id, user5.id]
        self.teams_data[team_key] = {
            "id": team_id,
            "name": team_name,
            "players": players,
            "sub": sub.id if sub else None,
            "coach": coach.id if coach else None,
            "wins": 0,
            "losses": 0
        }
        await self.save_all_data()

        # Poster dans le forum présentation-équipes
        forum_channel = self.bot.get_channel(self.config.get("teams_forum_id"))
        if not forum_channel or forum_channel.type != discord.ChannelType.guild_forum:
            return await interaction.followup.send("Le forum 'présentation-équipes' est introuvable ou n'est pas un forum.", ephemeral=True)

        embed = discord.Embed(title=f"Équipe {team_name}", color=discord.Color.green())
        members_str = ""
        for p_id in players:
            members_str += f"<@{p_id}>\n"
        if sub:
            members_str += f"Sub: <@{sub.id}>\n"
        if coach:
            members_str += f"Coach: <@{coach.id}>\n"
        embed.add_field(name="Membres", value=members_str, inline=False)
        embed.add_field(name="ID Équipe", value=str(team_id), inline=True)

        thread = await forum_channel.create_thread(name=f"Équipe {team_name}", content=None, embed=embed)
        await interaction.followup.send(f"Équipe '{team_name}' créée avec succès dans {forum_channel.mention} !", ephemeral=True)

    # ---------- Commande /remove_team ----------
    @app_commands.command(name="remove_team", description="Supprimer une équipe")
    @app_commands.describe(team_id="ID de l'équipe à supprimer")
    @is_admin()
    @enqueue_request()
    async def remove_team(self, interaction: discord.Interaction, team_id: int):
        await interaction.response.defer(ephemeral=True)
        team_key = f"team_{team_id}"
        if team_key not in self.teams_data:
            return await interaction.followup.send("Équipe introuvable.", ephemeral=True)

        team_name = self.teams_data[team_key]["name"]
        if not await self.ask_confirmation(interaction, f"Confirmez-vous la suppression de l'équipe '{team_name}' ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)

        del self.teams_data[team_key]
        await self.save_all_data()
        await interaction.followup.send(f"L'équipe '{team_name}' a été supprimée avec succès.", ephemeral=True)

    # ---------- Commande /team_add_member ----------
    @app_commands.command(name="team_add_member", description="Ajouter un membre dans une équipe")
    @app_commands.describe(team_id="ID de l'équipe", user="Utilisateur à ajouter", role="player/sub/coach")
    @is_admin()
    @enqueue_request()
    async def team_add_member(self, interaction: discord.Interaction, team_id: int, user: discord.Member, role: str):
        await interaction.response.defer(ephemeral=True)
        team_key = f"team_{team_id}"
        if team_key not in self.teams_data:
            return await interaction.followup.send("Équipe introuvable.", ephemeral=True)

        role = role.lower()
        if role not in ["player", "sub", "coach"]:
            return await interaction.followup.send("Rôle invalide. Choisir player/sub/coach.", ephemeral=True)

        team_info = self.teams_data[team_key]
        if self.is_user_in_team(user.id):
            return await interaction.followup.send(f"{user.mention} est déjà dans une autre équipe.", ephemeral=True)

        # Vérifier slots
        if role == "player":
            if len(team_info["players"]) >= 5:
                return await interaction.followup.send("L'équipe a déjà 5 joueurs.", ephemeral=True)
        elif role == "sub":
            if team_info["sub"] is not None:
                return await interaction.followup.send("Cette équipe a déjà un remplaçant.", ephemeral=True)
        elif role == "coach":
            if team_info["coach"] is not None:
                return await interaction.followup.send("Cette équipe a déjà un coach.", ephemeral=True)

        # Demander confirmation au user
        try:
            view = PurgeConfirmationView(interaction, None)
            await user.send(f"{interaction.user.display_name} vous propose de rejoindre l'équipe {team_info['name']} en tant que {role}. Confirmez-vous ?", view=view)
            await view.wait()
            if not view.value:
                return await interaction.followup.send(f"{user.mention} a refusé de rejoindre l'équipe.", ephemeral=True)
        except discord.Forbidden:
            return await interaction.followup.send(f"Impossible d'envoyer un message à {user.mention}.", ephemeral=True)
        except Exception as e:
            logger.exception(f"Erreur lors de la demande de confirmation à {user.display_name}: {e}")
            return await interaction.followup.send("Erreur lors de la demande de confirmation.", ephemeral=True)

        # User a confirmé
        if not await self.ask_confirmation(interaction, f"Confirmez-vous l'ajout de {user.mention} en tant que {role} dans {team_info['name']} ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)

        if role == "player":
            team_info["players"].append(user.id)
        elif role == "sub":
            team_info["sub"] = user.id
        elif role == "coach":
            team_info["coach"] = user.id

        self.teams_data[team_key] = team_info
        await self.save_all_data()

        await interaction.followup.send(f"{user.mention} a été ajouté comme {role} dans l'équipe {team_info['name']}.", ephemeral=True)

    # ---------- Commande /team_remove_member ----------
    @app_commands.command(name="team_remove_member", description="Retirer un membre d'une équipe")
    @app_commands.describe(team_id="ID de l'équipe", user="Utilisateur à retirer")
    @is_admin()
    @enqueue_request()
    async def team_remove_member(self, interaction: discord.Interaction, team_id: int, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        team_key = f"team_{team_id}"
        if team_key not in self.teams_data:
            return await interaction.followup.send("Équipe introuvable.", ephemeral=True)
        team_info = self.teams_data[team_key]

        if user.id not in team_info["players"] and team_info.get("sub") != user.id and team_info.get("coach") != user.id:
            return await interaction.followup.send(f"{user.mention} n'est pas dans cette équipe.", ephemeral=True)

        if not await self.ask_confirmation(interaction, f"Confirmez-vous le retrait de {user.mention} de l'équipe {team_info['name']} ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)

        if user.id in team_info["players"]:
            team_info["players"].remove(user.id)
        elif team_info.get("sub") == user.id:
            team_info["sub"] = None
        elif team_info.get("coach") == user.id:
            team_info["coach"] = None

        self.teams_data[team_key] = team_info
        await self.save_all_data()

        await interaction.followup.send(f"{user.mention} a été retiré(e) de l'équipe {team_info['name']}.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Scrims(bot))
    logger.info("Scrims Cog chargé avec succès.")
