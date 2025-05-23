import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime
from typing import Optional

# Import des fonctions de service
from .service.tournament_service import (
    create_tournament,
    persist_registration_message,
    register_team,
    create_forum_post,
    close_tournament,
    get_active_tournament
)

logger = logging.getLogger("tournament")

class TournamentCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Ici, vous pouvez recharger et réattacher les vues persistantes depuis la BDD si nécessaire.

    @app_commands.command(name="tournoi", description="Créer ou fermer un tournoi (Admin uniquement)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(action="Action à effectuer: creat pour créer, close pour fermer")
    @app_commands.choices(action=[
        app_commands.Choice(name="creat", value="creat"),
        app_commands.Choice(name="close", value="close")
    ])
    async def tournoi(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        action_lower = action.value.lower()
        if action_lower == "creat":
            # Vérifier qu'il n'existe pas déjà un tournoi actif
            active = await get_active_tournament()
            if active:
                await interaction.response.send_message("Un tournoi est déjà actif. Veuillez le fermer avant d'en créer un nouveau.", ephemeral=True)
                return

            modal = TournamentCreationModal(bot=self.bot)
            await interaction.response.send_modal(modal)
        elif action_lower == "close":
            success = await close_tournament()
            if success:
                await interaction.response.send_message("Le tournoi actif a été fermé et toutes les inscriptions supprimées.", ephemeral=True)
            else:
                await interaction.response.send_message("Erreur lors de la fermeture du tournoi.", ephemeral=True)
        else:
            await interaction.response.send_message("Action non reconnue.", ephemeral=True)

class TournamentCreationModal(discord.ui.Modal, title="Création de Tournoi"):
    tournament_name = discord.ui.TextInput(label="Nom du tournoi", placeholder="Ex: Tournoi d'été", required=True)
    max_teams = discord.ui.TextInput(label="Nombre maximum d'équipes", placeholder="Ex: 16", required=True)
    registration_start = discord.ui.TextInput(label="Date de début des inscriptions", placeholder="JJ/MM/YYYY HH:MM", required=True)
    registration_end = discord.ui.TextInput(label="Date de fin des inscriptions", placeholder="JJ/MM/YYYY HH:MM", required=True)
    tournament_date = discord.ui.TextInput(label="Date du tournoi", placeholder="JJ/MM/YYYY HH:MM", required=True)

    def __init__(self, *, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        try:
            start_date = datetime.strptime(self.registration_start.value, "%d/%m/%Y %H:%M")
            end_date = datetime.strptime(self.registration_end.value, "%d/%m/%Y %H:%M")
            tourn_date = datetime.strptime(self.tournament_date.value, "%d/%m/%Y %H:%M")
        except ValueError:
            await interaction.response.send_message("Format de date invalide.", ephemeral=True)
            return

        try:
            max_teams_int = int(self.max_teams.value)
        except ValueError:
            await interaction.response.send_message("Le nombre maximum d'équipes doit être un entier.", ephemeral=True)
            return

        # Création du tournoi dans la BDD
        tournament_id = await create_tournament(
            tournament_name=self.tournament_name.value,
            max_teams=max_teams_int,
            registration_start=start_date,
            registration_end=end_date,
            tournament_date=tourn_date
        )
        if not tournament_id:
            await interaction.response.send_message("Erreur lors de la création du tournoi.", ephemeral=True)
            return

        # Création d'un embed avec les infos du tournoi
        embed = discord.Embed(
            title=self.tournament_name.value,
            description=(
                f"Inscriptions du {self.registration_start.value} au {self.registration_end.value}\n"
                f"Date du tournoi : {self.tournament_date.value}"
            ),
            color=discord.Color.blue()
        )
        view = TournamentRegistrationView(tournament_id=tournament_id, bot=self.bot)
        message = await interaction.channel.send(embed=embed, view=view)

        # Enregistrement du message persistant pour réattachement ultérieur
        await persist_registration_message(
            channel_id=message.channel.id,
            message_id=message.id,
            tournament_id=tournament_id,
            guild_id=interaction.guild.id
        )
        await interaction.response.send_message("Tournoi créé avec succès !", ephemeral=True)

class TournamentRegistrationView(discord.ui.View):
    def __init__(self, tournament_id: int, bot: commands.Bot):
        super().__init__(timeout=None)
        self.tournament_id = tournament_id
        self.bot = bot
        self.add_item(TournamentRegistrationButton(tournament_id=tournament_id, bot=bot))

class TournamentRegistrationButton(discord.ui.Button):
    def __init__(self, tournament_id: int, bot: commands.Bot):
        super().__init__(label="S'inscrire au tournoi", style=discord.ButtonStyle.primary, custom_id="tournament_register")
        self.tournament_id = tournament_id
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        modal = TeamRegistrationModal(tournament_id=self.tournament_id, bot=self.bot)
        await interaction.response.send_modal(modal)

class TeamRegistrationModal(discord.ui.Modal, title="Inscription d'équipe"):
    team_name = discord.ui.TextInput(
        label="Nom de l'équipe",
        placeholder="Nom de votre équipe",
        required=True
    )
    players = discord.ui.TextInput(
        label="IDs Joueurs (5, séparés par une virgule)",
        placeholder="Ex: 123456789,987654321,1122334455,5566778899,9988776655",
        required=True
    )
    extras = discord.ui.TextInput(
        label="IDs Remplaçants/Coach (optionnel)",
        placeholder="Ex: 2233445566,3344556677,4455667788",
        required=False
    )

    def __init__(self, tournament_id: int, bot: commands.Bot):
        super().__init__()
        self.tournament_id = tournament_id
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        # Récupérer et nettoyer les IDs des joueurs obligatoires
        players_ids = [pid.strip() for pid in self.players.value.split(",") if pid.strip()]
        if len(players_ids) != 5:
            await interaction.response.send_message("Vous devez saisir exactement 5 Discord IDs pour les joueurs.", ephemeral=True)
            return

        # Pour le champ extras, on extrait jusqu'à 3 IDs (les remplaçants et/ou le coach)
        extras_input = [x.strip() for x in self.extras.value.split(",") if x.strip()] if self.extras.value else []
        extras_ids = extras_input[:3] if extras_input else []

        substitutes = extras_ids[:2] if extras_ids else []
        coach = extras_ids[2] if len(extras_ids) >= 3 else None

        team_info = {
            "team_name": self.team_name.value,
            "players": players_ids,
            "substitutes": substitutes,
            "coach": coach
        }
        # Enregistrer l'équipe dans la BDD
        team_id = await register_team(self.tournament_id, team_info)
        if not team_id:
            await interaction.response.send_message("Erreur lors de l'inscription de l'équipe.", ephemeral=True)
            return

        # Envoyer un message privé à chaque joueur obligatoire pour demander leur pseudo Valorant
        for player_id in players_ids:
            try:
                member = await self.bot.fetch_user(int(player_id))
                await member.send(
                    f"Bonjour ! Vous êtes inscrit dans l'équipe '{team_info['team_name']}' pour le tournoi. "
                    "Veuillez répondre à ce message en indiquant votre pseudo Valorant."
                )
            except Exception as e:
                logger.error(f"Erreur lors de l'envoi du DM à {player_id}: {e}")

        # Créer un post dans le forum (ID: 1236736105106116668) avec les infos publiques de l'équipe
        await create_forum_post(self.tournament_id, team_info)
        await interaction.response.send_message(
            "Inscription d'équipe enregistrée ! Vous recevrez prochainement un DM pour compléter votre inscription.",
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(TournamentCog(bot))
    logger.info("Tournament Cog chargé avec succès.")
