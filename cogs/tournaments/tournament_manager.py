# cogs/tournaments/tournament_manager.py

import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import random

from cogs.utilities.data_manager import DataManager
from cogs.utilities.request_manager import enqueue_request
from cogs.utilities.permission_manager import is_admin
from cogs.utilities.confirmation_view import ConfirmationView

logger = logging.getLogger("discord.tournament")

class InscriptionButton(discord.ui.Button):
    def __init__(self, cog, tournament_name: str):
        super().__init__(label="S'inscrire", style=discord.ButtonStyle.primary)
        self.cog = cog
        self.tournament_name = tournament_name

    async def callback(self, interaction: discord.Interaction):
        # Demander le nom de l'équipe
        await interaction.response.send_message("Veuillez entrer le nom de votre équipe :", ephemeral=True)
        def check(m: discord.Message):
            return m.author == interaction.user and m.channel == interaction.channel

        try:
            msg = await self.cog.bot.wait_for("message", check=check, timeout=60)
        except:
            return await interaction.followup.send("Temps écoulé.", ephemeral=True)

        team_name = msg.content.strip()
        # Vérifier si équipe déjà inscrite
        tournaments_data = await self.cog.data.get_tournaments_data()
        t_info = tournaments_data.get(self.tournament_name)
        if not t_info:
            return await interaction.followup.send("Tournoi introuvable.", ephemeral=True)

        # Vérifier fin inscription
        end_date_str = t_info["end_inscription"]
        end_date = datetime.fromisoformat(end_date_str)
        if datetime.utcnow() > end_date:
            return await interaction.followup.send("Les inscriptions sont terminées.", ephemeral=True)

        # Vérifier max teams
        max_teams = t_info["max_teams"]
        if max_teams != 0 and len(t_info["teams"]) >= max_teams:
            return await interaction.followup.send("Le nombre maximum d'équipes est atteint.", ephemeral=True)

        # Vérifier nom équipe unique
        for team in t_info["teams"]:
            if team["name"].lower() == team_name.lower():
                return await interaction.followup.send("Ce nom d'équipe est déjà pris.", ephemeral=True)

        # Ajouter l'équipe (ici on ne demande pas la composition, simplification)
        # On pourrait demander les membres de l'équipe via d'autres interactions
        new_team = {
            "name": team_name,
            "wins": 0,
            "losses": 0
        }
        t_info["teams"].append(new_team)
        tournaments_data[self.tournament_name] = t_info
        await self.cog.data.save_tournaments_data(tournaments_data)
        await interaction.followup.send(f"L'équipe '{team_name}' est inscrite au tournoi {self.tournament_name} !", ephemeral=True)

class InscriptionView(discord.ui.View):
    def __init__(self, cog, tournament_name: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(InscriptionButton(cog, tournament_name))

class TournamentManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.config: Dict[str, Any] = {}
        self.tournaments_data: Dict[str, Any] = {}
        self.check_inscriptions_task.start()

    def cog_unload(self):
        self.check_inscriptions_task.cancel()

    async def load_data(self):
        self.config = await self.data.get_config()
        self.tournaments_data = await self.data.get_tournaments_data()

    async def save_data(self):
        await self.data.save_config(self.config)
        await self.data.save_tournaments_data(self.tournaments_data)

    @tasks.loop(minutes=1)
    async def check_inscriptions_task(self):
        await self.bot.wait_until_ready()
        await self.load_data()
        now = datetime.utcnow()
        for t_name, t_info in self.tournaments_data.items():
            if t_info["status"] == "open":
                end_date = datetime.fromisoformat(t_info["end_inscription"])
                if now > end_date:
                    # Clôturer les inscriptions
                    t_info["status"] = "closed"
                    # Générer le bracket
                    await self.generate_bracket(t_name)
                    # Poster les premiers matchs
                    await self.post_bracket(t_name)
                    await self.save_data()

    async def generate_bracket(self, t_name: str):
        t_info = self.tournaments_data[t_name]
        teams = t_info["teams"]
        random.shuffle(teams)
        # Générer des matchs (arbre)
        # Pour simplifier, on fait un bracket simple, s'il y a 8 équipes, round 1: 4 matchs, etc.
        # Stocker dans t_info["bracket"] = [{round:1, matches:[ (teamA, teamB), ...]}]
        # Si nombre d'équipes non puissance de 2, ajouter BYE
        n = len(teams)
        # Trouver la puissance de 2 supérieure
        p = 1
        while p < n:
            p *= 2
        # Ajouter des BYE si nécessaire
        for i in range(p - n):
            teams.append({"name":"BYE","wins":0,"losses":0})
        # Créer round 1
        matches = []
        for i in range(0, p, 2):
            matches.append((teams[i]["name"], teams[i+1]["name"]))
        t_info["bracket"] = {
            "rounds": [{
                "round_number": 1,
                "matches": [{"match_id": i+1, "teams": list(matches[i]), "winner": None} for i in range(len(matches))]
            }]
        }
        t_info["status"] = "in_progress"

    async def post_bracket(self, t_name: str):
        # Poster l'embed du bracket actuel dans le salon tournoi
        tournament_channel = self.bot.get_channel(self.config.get("tournament_channel_id"))
        if not tournament_channel:
            logger.warning("Channel de tournoi introuvable.")
            return
        t_info = self.tournaments_data[t_name]
        embed = discord.Embed(title=f"Tournoi {t_name}", color=discord.Color.blue())
        embed.description = t_info.get("description","Pas de description")
        embed.add_field(name="Date Fin Inscriptions", value=t_info["end_inscription"], inline=False)
        rounds = t_info["bracket"]["rounds"]
        for r in rounds:
            round_number = r["round_number"]
            match_list_str = ""
            for m in r["matches"]:
                teams = m["teams"]
                # si "BYE" => l'autre team passe direct
                match_list_str += f"Match {m['match_id']}: {teams[0]} vs {teams[1]}\n"
            embed.add_field(name=f"Round {round_number}", value=match_list_str or "Aucun match", inline=False)
        await tournament_channel.send(embed=embed)

    async def update_bracket_embed(self, t_name: str):
        # Mettre à jour le bracket (re-poster un embed mis à jour)
        # Pour simplifier on poste un nouveau message à chaque update
        await self.post_bracket(t_name)

    @app_commands.command(name="create_tournament", description="Crée un tournoi")
    @app_commands.describe(
        name="Nom du tournoi",
        description="Description du tournoi",
        max_teams="Nombre max d'équipes (0 pour illimité)",
        end_inscription="Date fin inscriptions (YYYY-MM-DD HH:MM UTC)"
    )
    @enqueue_request()
    @is_admin()
    async def create_tournament(self, interaction: discord.Interaction, name: str, description: str, max_teams: int, end_inscription: str):
        await interaction.response.defer(ephemeral=True)
        await self.load_data()
        if name in self.tournaments_data:
            return await interaction.followup.send("Un tournoi avec ce nom existe déjà.", ephemeral=True)

        # Vérifier format date
        try:
            end_date = datetime.strptime(end_inscription, "%Y-%m-%d %H:%M")
            end_date_utc = end_date.replace(tzinfo=timezone.utc)
        except ValueError:
            return await interaction.followup.send("Format de date invalide. Utilisez YYYY-MM-DD HH:MM", ephemeral=True)

        if end_date_utc < datetime.utcnow():
            return await interaction.followup.send("La date de fin d'inscription est déjà passée.", ephemeral=True)

        if not await self.ask_confirmation(interaction, f"Confirmez-vous la création du tournoi {name} ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)

        self.tournaments_data[name] = {
            "name": name,
            "description": description,
            "max_teams": max_teams,
            "end_inscription": end_date_utc.isoformat(),
            "teams": [],
            "status": "open"
        }
        await self.save_data()

        inscription_channel = self.bot.get_channel(self.config.get("inscription_tournament_channel_id"))
        if not inscription_channel:
            return await interaction.followup.send("Le salon d'inscription au tournoi est introuvable.", ephemeral=True)

        embed = discord.Embed(title=f"Tournoi {name}", description=description, color=discord.Color.green())
        embed.add_field(name="Date Fin Inscriptions", value=end_inscription, inline=False)
        embed.add_field(name="Max Teams", value=str(max_teams) if max_teams !=0 else "Illimité", inline=True)

        view = InscriptionView(self, name)
        await inscription_channel.send(embed=embed, view=view)

        await interaction.followup.send(f"Tournoi {name} créé avec succès. Annonce postée dans {inscription_channel.mention}", ephemeral=True)

    @app_commands.command(name="report_match", description="Reporter le résultat d'un match")
    @app_commands.describe(tournament_name="Nom du tournoi", match_id="ID du match", winner="Nom de l'équipe gagnante")
    @enqueue_request()
    async def report_match(self, interaction: discord.Interaction, tournament_name: str, match_id: int, winner: str):
        await interaction.response.defer(ephemeral=True)
        await self.load_data()
        t_info = self.tournaments_data.get(tournament_name)
        if not t_info:
            return await interaction.followup.send("Tournoi introuvable.", ephemeral=True)
        if t_info["status"] != "in_progress":
            return await interaction.followup.send("Le tournoi n'est pas en cours.", ephemeral=True)

        # Trouver le match
        # Ceci est simplifié, on suppose qu'il est dans le round actuel
        # En réalité, il faudrait suivre l'avancement des rounds.
        match_found = None
        for r in t_info["bracket"]["rounds"]:
            for m in r["matches"]:
                if m["match_id"] == match_id:
                    match_found = m
                    break
            if match_found:
                break

        if not match_found:
            return await interaction.followup.send("Match introuvable.", ephemeral=True)

        if match_found["winner"] is not None:
            return await interaction.followup.send("Le vainqueur de ce match est déjà déterminé.", ephemeral=True)

        # Vérifier que le winner est une des teams du match
        if winner not in match_found["teams"]:
            # Litige ?
            # Ici on simplifie, on demande confirmation admin
            return await interaction.followup.send("Le vainqueur indiqué ne fait pas partie du match, litige nécessaire.", ephemeral=True)

        # Tout va bien
        match_found["winner"] = winner
        # Mettre à jour les stats de l'équipe gagnante et perdante
        # Dans teams du tournoi
        for team in t_info["teams"]:
            if team["name"] == winner:
                team["wins"] += 1
            elif team["name"] in match_found["teams"] and team["name"] != winner:
                team["losses"] += 1

        # Vérifier si le round est terminé, générer le round suivant, etc.
        # Pour simplifier, on ne le fait pas ici.
        # On met juste à jour le bracket embed
        await self.save_data()
        await self.update_bracket_embed(tournament_name)
        await interaction.followup.send(f"Match {match_id} enregistré. Gagnant: {winner}", ephemeral=True)

        # Notifier les joueurs du prochain match si round suivant est déterminé
        # (Non implémenté dans cet exemple)

async def setup(bot: commands.Bot):
    await bot.add_cog(TournamentManager(bot))
    logger.info("TournamentManager Cog chargé avec succès.")
