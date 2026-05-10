from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from cogs.tournaments.presenters import build_team_public_message, build_tournament_embed
from cogs.tournaments.services import ParsedTeamRegistration, TournamentService

logger = logging.getLogger(__name__)

PARIS_TZ = ZoneInfo("Europe/Paris")
DATE_FORMAT = "%d/%m/%Y %H:%M"


class TournamentCog(commands.Cog):
    ACTION_CHOICES = [
        app_commands.Choice(name="create", value="create"),
        app_commands.Choice(name="close", value="close"),
    ]

    def __init__(self, bot: commands.Bot, tournament_service: TournamentService) -> None:
        self.bot = bot
        self._service = tournament_service
        self._views_reloaded = False
        logger.info("TournamentCog initialized.")

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._views_reloaded:
            return
        self._views_reloaded = True
        for guild in self.bot.guilds:
            active = await self._service.get_active_tournament(guild.id)
            if active and active.registration_message_id:
                self.bot.add_view(
                    TournamentRegistrationView(self, active.id),
                    message_id=active.registration_message_id,
                )

    @app_commands.command(name="tournoi", description="Creer ou fermer un tournoi.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(action="Action a effectuer")
    @app_commands.choices(action=ACTION_CHOICES)
    async def tournoi(self, interaction: discord.Interaction, action: app_commands.Choice[str]) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Cette commande doit etre executee dans un serveur.", ephemeral=True)
            return

        if action.value in {"create", "creat"}:
            active = await self._service.get_active_tournament(interaction.guild.id)
            if active:
                await interaction.response.send_message(
                    "Un tournoi est deja actif. Fermez-le avant d'en creer un nouveau.",
                    ephemeral=True,
                )
                return

            await interaction.response.send_modal(TournamentCreationModal(self))
            return

        if action.value == "close":
            closed = await self._service.close_active_tournament(interaction.guild.id)
            message = "Le tournoi actif a ete ferme." if closed else "Aucun tournoi actif a fermer."
            await interaction.response.send_message(message, ephemeral=True)
            return

        await interaction.response.send_message("Action non reconnue.", ephemeral=True)


class TournamentCreationModal(discord.ui.Modal, title="Creation de Tournoi"):
    tournament_name = discord.ui.TextInput(label="Nom du tournoi", placeholder="Ex: Tournoi Valorant", required=True)
    max_teams = discord.ui.TextInput(label="Nombre maximum d'equipes", placeholder="Ex: 16", required=True)
    registration_start = discord.ui.TextInput(label="Debut inscriptions", placeholder="JJ/MM/YYYY HH:MM", required=True)
    registration_end = discord.ui.TextInput(label="Fin inscriptions", placeholder="JJ/MM/YYYY HH:MM", required=True)
    tournament_date = discord.ui.TextInput(label="Date du tournoi", placeholder="JJ/MM/YYYY HH:MM", required=True)

    def __init__(self, cog: TournamentCog) -> None:
        super().__init__()
        self._cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Serveur introuvable.", ephemeral=True)
            return

        try:
            max_teams = int(str(self.max_teams.value).strip())
            registration_start = parse_modal_datetime(str(self.registration_start.value))
            registration_end = parse_modal_datetime(str(self.registration_end.value))
            tournament_date = parse_modal_datetime(str(self.tournament_date.value))
        except ValueError:
            await interaction.response.send_message("Format invalide: utilisez des nombres et JJ/MM/YYYY HH:MM.", ephemeral=True)
            return

        tournament = await self._cog._service.create_tournament(
            guild_id=interaction.guild.id,
            guild_name=interaction.guild.name,
            tournament_name=str(self.tournament_name.value),
            max_teams=max_teams,
            registration_start=registration_start,
            registration_end=registration_end,
            tournament_date=tournament_date,
        )
        if tournament is None:
            await interaction.response.send_message("Impossible de creer le tournoi.", ephemeral=True)
            return

        channel = await resolve_registration_channel(self._cog._service, interaction)
        if channel is None:
            await interaction.response.send_message("Salon d'inscription introuvable.", ephemeral=True)
            return

        message = await channel.send(
            embed=build_tournament_embed(
                name=tournament.tournament_name,
                registration_start=tournament.registration_start,
                registration_end=tournament.registration_end,
                tournament_date=tournament.tournament_date,
                max_teams=tournament.max_teams,
            ),
            view=TournamentRegistrationView(self._cog, tournament.id),
        )
        await self._cog._service.save_registration_message(
            tournament_id=tournament.id,
            channel_id=message.channel.id,
            message_id=message.id,
        )
        await interaction.response.send_message("Tournoi cree avec succes.", ephemeral=True)


class TournamentRegistrationView(discord.ui.View):
    def __init__(self, cog: TournamentCog, tournament_id: int) -> None:
        super().__init__(timeout=None)
        self._cog = cog
        self._tournament_id = tournament_id

    @discord.ui.button(label="S'inscrire au tournoi", style=discord.ButtonStyle.primary, custom_id="tournament_register")
    async def register(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(TeamRegistrationModal(self._cog, self._tournament_id))


class TeamRegistrationModal(discord.ui.Modal, title="Inscription d'equipe"):
    team_name = discord.ui.TextInput(label="Nom de l'equipe", placeholder="Nom de votre equipe", required=True)
    players = discord.ui.TextInput(
        label="IDs joueurs (5, separes par virgule)",
        placeholder="123,456,789,101,112",
        required=True,
    )
    extras = discord.ui.TextInput(
        label="IDs remplacants/coach (optionnel)",
        placeholder="2 remplacants puis 1 coach max",
        required=False,
    )

    def __init__(self, cog: TournamentCog, tournament_id: int) -> None:
        super().__init__()
        self._cog = cog
        self._tournament_id = tournament_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Serveur introuvable.", ephemeral=True)
            return

        try:
            registration = self._cog._service.parse_team_registration(
                team_name=str(self.team_name.value),
                players_raw=str(self.players.value),
                extras_raw=str(self.extras.value or ""),
            )
        except ValueError:
            await interaction.response.send_message(
                "Inscription invalide: il faut un nom et exactement 5 IDs Discord joueurs.",
                ephemeral=True,
            )
            return

        result = await self._cog._service.register_team(
            guild_id=interaction.guild.id,
            guild_name=interaction.guild.name,
            tournament_id=self._tournament_id,
            captain_discord_id=interaction.user.id,
            registration=registration,
        )
        if result.status != "created":
            await interaction.response.send_message(format_registration_error(result.status), ephemeral=True)
            return

        await send_team_public_message(self._cog, interaction.guild, registration)
        await dm_registered_players(self._cog.bot, registration)
        await interaction.response.send_message("Inscription d'equipe enregistree.", ephemeral=True)


def parse_modal_datetime(value: str) -> datetime:
    return datetime.strptime(value.strip(), DATE_FORMAT).replace(tzinfo=PARIS_TZ)


async def resolve_registration_channel(service: TournamentService, interaction: discord.Interaction):
    configured_id = await service.get_registration_channel_id(interaction.guild.id)
    if configured_id:
        channel = interaction.guild.get_channel(configured_id)
        if channel and hasattr(channel, "send"):
            return channel
    return interaction.channel if hasattr(interaction.channel, "send") else None


async def send_team_public_message(
    cog: TournamentCog,
    guild: discord.Guild,
    registration: ParsedTeamRegistration,
) -> None:
    channel_id = await cog._service.get_public_channel_id(guild.id)
    channel = guild.get_channel(channel_id) if channel_id else None
    if channel is None:
        return

    content = build_team_public_message(registration)
    try:
        if isinstance(channel, discord.ForumChannel):
            await channel.create_thread(name=registration.team_name[:100], content=content)
        elif hasattr(channel, "send"):
            await channel.send(content)
    except discord.HTTPException:
        logger.exception("Could not publish tournament team %s.", registration.team_name)


async def dm_registered_players(bot: commands.Bot, registration: ParsedTeamRegistration) -> None:
    for user_id in registration.player_discord_ids:
        try:
            user = await bot.fetch_user(user_id)
            await user.send(
                f"Bonjour, vous etes inscrit dans l'equipe `{registration.team_name}` pour le tournoi."
            )
        except Exception:
            logger.debug("Could not DM tournament player %s.", user_id)


def format_registration_error(status: str) -> str:
    if status == "full":
        return "Le tournoi est complet."
    if status == "duplicate":
        return "Cette equipe est deja inscrite."
    return "Le tournoi n'est plus actif."


async def setup(bot: commands.Bot) -> None:
    tournament_service = getattr(bot, "tournament_service", None)
    if tournament_service is None:
        logger.error("tournament_service is not initialized. TournamentCog will not be loaded.")
        return

    await bot.add_cog(TournamentCog(bot, tournament_service))
    logger.info("TournamentCog loaded.")
