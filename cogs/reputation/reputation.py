from __future__ import annotations

import logging
import unicodedata
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from cogs.reputation.presenters import build_full_profile_embed, build_reputation_summary_embed
from cogs.reputation.services import ReputationService

logger = logging.getLogger(__name__)

RANK_ROLE_NAMES = {"Fer", "Bronze", "Argent", "Or", "Platine", "Diamant", "Ascendant", "Immortel", "Radiant"}
LANGUAGE_LABELS = {
    "francais": "Francais",
    "anglais": "Anglais",
    "english": "English",
    "espagnol": "Espagnol",
    "espanol": "Espagnol",
}
PLATFORM_NAMES = {"Pc", "PC", "Console"}

ACTION_CHOICES = [
    app_commands.Choice(name="Signaler un utilisateur", value="report"),
    app_commands.Choice(name="Recommander un utilisateur", value="recommend"),
    app_commands.Choice(name="Afficher le profil resume", value="view"),
]


class ReputationCog(commands.Cog):
    def __init__(self, bot: commands.Bot, reputation_service: ReputationService) -> None:
        self.bot = bot
        self._service = reputation_service
        logger.info("ReputationCog initialized.")

    @app_commands.command(name="reputation", description="Gerer la reputation des joueurs.")
    @app_commands.describe(
        action="Action a effectuer",
        user="Utilisateur concerne",
        reason="Raison du signalement",
    )
    @app_commands.choices(action=ACTION_CHOICES)
    async def reputation_execute(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        user: discord.Member,
        reason: Optional[str] = None,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Cette commande doit etre executee dans un serveur.", ephemeral=True)
            return

        action_value = action.value.lower()
        if action_value == "view":
            summary = await self._service.get_summary(guild_id=interaction.guild.id, target_discord_id=user.id)
            await interaction.response.send_message(embed=build_reputation_summary_embed(user, summary), ephemeral=True)
            return

        if user.id == interaction.user.id:
            await interaction.response.send_message("Vous ne pouvez pas faire cette action sur vous-meme.", ephemeral=True)
            return

        if action_value not in {"report", "recommend"}:
            await interaction.response.send_message("Action non reconnue.", ephemeral=True)
            return

        event_type = "report" if action_value == "report" else "recommendation"
        result = await self._service.add_event(
            guild_id=interaction.guild.id,
            guild_name=interaction.guild.name,
            reporter_discord_id=interaction.user.id,
            target_discord_id=user.id,
            event_type=event_type,
            reason=reason,
        )
        if not result.created:
            await interaction.response.send_message(self._format_add_error(result.status, event_type), ephemeral=True)
            return

        summary = await self._service.get_summary(guild_id=interaction.guild.id, target_discord_id=user.id)
        await self._sync_reputation_roles(user, summary)

        if event_type == "report":
            await interaction.response.send_message(
                f"{user.mention} a ete signale pour `{reason or 'Aucune raison fournie'}`.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(f"{user.mention} a ete recommande.", ephemeral=True)

    @app_commands.command(name="profile_set", description="Parametrer votre profil Valorant.")
    @app_commands.describe(
        genre="Homme, Femme ou Autre",
        tracker="Lien tracker.gg Valorant",
        lft="'LFT', 'Rien' ou le nom de votre equipe",
        note="Champ libre sans lien",
    )
    async def profile_set(
        self,
        interaction: discord.Interaction,
        genre: Optional[str] = None,
        tracker: Optional[str] = None,
        lft: Optional[str] = None,
        note: Optional[str] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        result = await self._service.save_profile(
            discord_id=interaction.user.id,
            genre=genre,
            valorant_tracker=tracker,
            lft=lft,
            note=note,
        )
        if not result.success:
            await interaction.followup.send(result.error or "Impossible de mettre a jour votre profil.", ephemeral=True)
            return
        await interaction.followup.send("Profil mis a jour avec succes.", ephemeral=True)

    @app_commands.command(name="profile_show", description="Afficher le profil complet d'un joueur.")
    @app_commands.describe(member="Joueur dont afficher le profil")
    async def profile_show(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Cette commande doit etre executee dans un serveur.", ephemeral=True)
            return

        target = member or interaction.user
        if not isinstance(target, discord.Member):
            await interaction.followup.send("Membre introuvable.", ephemeral=True)
            return

        summary = await self._service.get_summary(guild_id=interaction.guild.id, target_discord_id=target.id)
        profile = await self._service.get_profile(target.id)
        await interaction.followup.send(
            embed=build_full_profile_embed(
                member=target,
                summary=summary,
                profile=profile,
                rank=self._get_user_rank(target),
                language=self._get_user_language(target),
                platform=self._get_user_platform(target),
            ),
            ephemeral=True,
        )

    async def _sync_reputation_roles(self, member: discord.Member, summary) -> None:
        configured = await self._service.get_reputation_role_ids(member.guild.id)
        if not configured:
            logger.info("No reputation roles configured for guild %s.", member.guild.id)
            return

        plan = self._service.build_reputation_role_plan(
            current_role_ids={role.id for role in member.roles},
            configured_role_ids=configured,
            summary=summary,
        )
        roles_to_remove = [
            role
            for role_id in plan.role_ids_to_remove
            if (role := member.guild.get_role(role_id)) is not None
        ]
        role_to_add = member.guild.get_role(plan.role_id_to_add) if plan.role_id_to_add else None

        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Mise a jour reputation.")
            if role_to_add:
                await member.add_roles(role_to_add, reason="Mise a jour reputation.")
        except discord.Forbidden:
            logger.warning("Missing permissions to update reputation roles for member %s.", member.id)

    @staticmethod
    def _format_add_error(status: str, event_type: str) -> str:
        if status == "duplicate_today":
            return (
                "Vous avez deja signale cet utilisateur aujourd'hui."
                if event_type == "report"
                else "Vous avez deja recommande cet utilisateur aujourd'hui."
            )
        if status == "limit_reached":
            return (
                "La limite globale de signalements pour cet utilisateur est atteinte."
                if event_type == "report"
                else "La limite globale de recommandations pour cet utilisateur est atteinte."
            )
        return "Une erreur est survenue lors de l'enregistrement."

    @staticmethod
    def _get_user_rank(member: discord.Member) -> str:
        for role in member.roles:
            if role.name in RANK_ROLE_NAMES:
                return role.name
        return "Inconnu"

    @staticmethod
    def _get_user_language(member: discord.Member) -> str:
        for role in member.roles:
            if label := LANGUAGE_LABELS.get(_normalize_role_name(role.name)):
                return label
        return "Non specifie"

    @staticmethod
    def _get_user_platform(member: discord.Member) -> str:
        for role in member.roles:
            if role.name in PLATFORM_NAMES:
                return role.name
        return "Non specifie"


async def setup(bot: commands.Bot) -> None:
    reputation_service = getattr(bot, "reputation_service", None)
    if reputation_service is None:
        logger.error("reputation_service is not initialized. ReputationCog will not be loaded.")
        return
    await bot.add_cog(ReputationCog(bot, reputation_service))
    logger.info("ReputationCog loaded.")


def _normalize_role_name(value: str) -> str:
    try:
        value = value.encode("latin1").decode("utf-8")
    except UnicodeError:
        pass
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.strip().lower().split())
