from __future__ import annotations

import logging

import discord
from discord.ext import commands

from cogs.role_management.presenters import (
    build_game_roles_embed,
    format_missing_config_message,
    format_missing_discord_roles_message,
    format_role_selection_result,
)
from cogs.role_management.services import RoleSelectionService
from cogs.role_management.services.role_selection_service import GAME_ROLE_KEYS, GAME_ROLE_MESSAGE_TYPE
from cogs.role_management.views import GameRolesView

logger = logging.getLogger(__name__)


class GameRoleCog(commands.Cog):
    """Valorant role selector with persistent buttons."""

    def __init__(self, bot: commands.Bot, role_selection_service: RoleSelectionService) -> None:
        self.bot = bot
        self._service = role_selection_service
        self.bot.add_view(GameRolesView(self))
        logger.info("GameRoleCog initialized.")

    @commands.command(name="setup_roles")
    @commands.has_permissions(administrator=True)
    async def setup_roles(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await ctx.send("Cette commande doit etre executee dans un serveur.", delete_after=10)
            return

        configured = await self._service.get_configured_role_ids(ctx.guild.id, GAME_ROLE_KEYS)
        missing_config = self._service.missing_config_keys(configured, GAME_ROLE_KEYS)
        if missing_config:
            await ctx.send(format_missing_config_message(missing_config), delete_after=15)
            return

        roles, missing_discord = self._resolve_configured_roles(ctx.guild, configured)
        if missing_discord:
            await ctx.send(format_missing_discord_roles_message(missing_discord), delete_after=15)
            return

        embed = build_game_roles_embed(
            {role_key: len(role.members) for role_key, role in roles.items()}
        )
        view = GameRolesView(self)
        existing = await self._service.get_persistent_message(ctx.guild.id, GAME_ROLE_MESSAGE_TYPE)

        if existing:
            channel = self.bot.get_channel(existing.channel_id)
            if channel and hasattr(channel, "fetch_message"):
                try:
                    message = await channel.fetch_message(existing.message_id)
                    await message.edit(embed=embed, view=view)
                    await ctx.send("Le message de selection des roles a ete mis a jour.", delete_after=10)
                    return
                except discord.NotFound:
                    await self._service.delete_persistent_message(ctx.guild.id, GAME_ROLE_MESSAGE_TYPE)

        message = await ctx.send(embed=embed, view=view)
        await self._service.save_persistent_message(
            guild_id=ctx.guild.id,
            guild_name=ctx.guild.name,
            message_type=GAME_ROLE_MESSAGE_TYPE,
            channel_id=message.channel.id,
            message_id=message.id,
        )
        logger.info("Game role selector persisted with message_id=%s.", message.id)

    async def handle_role_selection(self, interaction: discord.Interaction, role_key: str) -> None:
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Cette action doit etre effectuee dans un serveur.",
                ephemeral=True,
            )
            return

        configured = await self._service.get_configured_role_ids(guild.id, GAME_ROLE_KEYS)
        missing_config = self._service.missing_config_keys(configured, GAME_ROLE_KEYS)
        if missing_config:
            await interaction.response.send_message(format_missing_config_message(missing_config), ephemeral=True)
            return

        roles, missing_discord = self._resolve_configured_roles(guild, configured)
        if missing_discord:
            await interaction.response.send_message(format_missing_discord_roles_message(missing_discord), ephemeral=True)
            return

        plan = self._service.build_exclusive_selection_plan(
            current_role_ids={role.id for role in member.roles},
            configured_role_ids=configured,
            selected_key=role_key,
        )
        role_to_add = guild.get_role(plan.role_to_add_id) if plan.role_to_add_id else None
        roles_to_remove = [
            role
            for role_id in plan.role_ids_to_remove
            if (role := guild.get_role(role_id)) is not None
        ]

        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Changement de role via le selecteur Valorant.")
            if role_to_add:
                await member.add_roles(role_to_add, reason="Selection de role via le selecteur Valorant.")
        except discord.Forbidden:
            await interaction.response.send_message(
                "Je n'ai pas les permissions necessaires pour gerer vos roles.",
                ephemeral=True,
            )
            return

        already_selected_mention = roles[role_key].mention if plan.already_selected else None
        await interaction.response.send_message(
            format_role_selection_result(
                added_mention=role_to_add.mention if role_to_add else None,
                removed_mentions=[role.mention for role in roles_to_remove],
                already_selected_mention=already_selected_mention,
            ),
            ephemeral=True,
        )
        await self.update_roles_embed(guild)

    async def update_roles_embed(self, guild: discord.Guild) -> None:
        message_info = await self._service.get_persistent_message(guild.id, GAME_ROLE_MESSAGE_TYPE)
        if not message_info:
            return

        channel = guild.get_channel(message_info.channel_id)
        if not channel or not hasattr(channel, "fetch_message"):
            return

        configured = await self._service.get_configured_role_ids(guild.id, GAME_ROLE_KEYS)
        if self._service.missing_config_keys(configured, GAME_ROLE_KEYS):
            return

        roles, missing_discord = self._resolve_configured_roles(guild, configured)
        if missing_discord:
            return

        try:
            message = await channel.fetch_message(message_info.message_id)
            await message.edit(
                embed=build_game_roles_embed({key: len(role.members) for key, role in roles.items()}),
                view=GameRolesView(self),
            )
        except discord.NotFound:
            await self._service.delete_persistent_message(guild.id, GAME_ROLE_MESSAGE_TYPE)
        except discord.HTTPException as exc:
            logger.warning("Could not update game role selector for guild %s: %s", guild.id, exc)

    @staticmethod
    def _resolve_configured_roles(
        guild: discord.Guild,
        configured: dict[str, int],
    ) -> tuple[dict[str, discord.Role], tuple[str, ...]]:
        roles: dict[str, discord.Role] = {}
        missing: list[str] = []
        for key, role_id in configured.items():
            role = guild.get_role(role_id)
            if role is None:
                missing.append(key)
            else:
                roles[key] = role
        return roles, tuple(missing)

    @setup_roles.error
    async def setup_roles_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Vous n'avez pas les permissions necessaires.", delete_after=10)
            return
        logger.exception("setup_roles failed: %s", error)
        await ctx.send("Une erreur est survenue lors de l'execution de la commande.", delete_after=10)


async def setup(bot: commands.Bot) -> None:
    role_selection_service = getattr(bot, "role_selection_service", None)
    if role_selection_service is None:
        logger.error("role_selection_service is not initialized. GameRoleCog will not be loaded.")
        return
    await bot.add_cog(GameRoleCog(bot, role_selection_service))
    logger.info("GameRoleCog loaded.")
