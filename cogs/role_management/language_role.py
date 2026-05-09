from __future__ import annotations

import logging

import discord
from discord.ext import commands

from cogs.role_management.presenters import (
    build_language_roles_embed,
    format_missing_config_message,
    format_missing_discord_roles_message,
    format_role_selection_result,
)
from cogs.role_management.services import RoleSelectionService
from cogs.role_management.services.role_selection_service import LANGUAGE_ROLE_KEYS, LANGUAGE_ROLE_MESSAGE_TYPE
from cogs.role_management.views import LanguageRolesView

logger = logging.getLogger(__name__)


class LanguageRoleCog(commands.Cog):
    """Language role selector with persistent buttons."""

    def __init__(self, bot: commands.Bot, role_selection_service: RoleSelectionService) -> None:
        self.bot = bot
        self._service = role_selection_service
        self.bot.add_view(LanguageRolesView(self))
        logger.info("LanguageRoleCog initialized.")

    @commands.command(name="setup_language")
    @commands.has_permissions(administrator=True)
    async def setup_language(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await ctx.send("Cette commande doit etre executee dans un serveur.", delete_after=10)
            return

        configured = await self._service.get_configured_role_ids(ctx.guild.id, LANGUAGE_ROLE_KEYS)
        missing_config = self._service.missing_config_keys(configured, LANGUAGE_ROLE_KEYS)
        if missing_config:
            await ctx.send(format_missing_config_message(missing_config), delete_after=15)
            return

        _, missing_discord = self._resolve_configured_roles(ctx.guild, configured)
        if missing_discord:
            await ctx.send(format_missing_discord_roles_message(missing_discord), delete_after=15)
            return

        embed = build_language_roles_embed()
        view = LanguageRolesView(self)
        existing = await self._service.get_persistent_message(ctx.guild.id, LANGUAGE_ROLE_MESSAGE_TYPE)

        if existing:
            channel = self.bot.get_channel(existing.channel_id)
            if channel and hasattr(channel, "fetch_message"):
                try:
                    message = await channel.fetch_message(existing.message_id)
                    await message.edit(embed=embed, view=view)
                    await ctx.send("Le message de selection des langues a ete mis a jour.", delete_after=10)
                    return
                except discord.NotFound:
                    await self._service.delete_persistent_message(ctx.guild.id, LANGUAGE_ROLE_MESSAGE_TYPE)

        message = await ctx.send(embed=embed, view=view)
        await self._service.save_persistent_message(
            guild_id=ctx.guild.id,
            guild_name=ctx.guild.name,
            message_type=LANGUAGE_ROLE_MESSAGE_TYPE,
            channel_id=message.channel.id,
            message_id=message.id,
        )
        logger.info("Language role selector persisted with message_id=%s.", message.id)

    async def handle_role_selection(self, interaction: discord.Interaction, role_key: str) -> None:
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Cette action doit etre effectuee dans un serveur.",
                ephemeral=True,
            )
            return

        role_id = await self._service.get_role_id(guild.id, role_key)
        if role_id is None:
            await interaction.response.send_message(format_missing_config_message([role_key]), ephemeral=True)
            return

        role = guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message(format_missing_discord_roles_message([role_key]), ephemeral=True)
            return

        plan = self._service.build_toggle_plan(
            current_role_ids={member_role.id for member_role in member.roles},
            role_id=role_id,
        )
        try:
            if plan.role_ids_to_remove:
                await member.remove_roles(role, reason="Retrait de role via le selecteur de langue.")
                await interaction.response.send_message(
                    format_role_selection_result(
                        added_mention=None,
                        removed_mentions=[role.mention],
                    ),
                    ephemeral=True,
                )
                return

            await member.add_roles(role, reason="Selection de role via le selecteur de langue.")
            await interaction.response.send_message(
                format_role_selection_result(
                    added_mention=role.mention,
                    removed_mentions=[],
                ),
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Je n'ai pas les permissions necessaires pour gerer vos roles.",
                ephemeral=True,
            )

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

    @setup_language.error
    async def setup_language_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Vous n'avez pas les permissions necessaires.", delete_after=10)
            return
        logger.exception("setup_language failed: %s", error)
        await ctx.send("Une erreur est survenue lors de l'execution de la commande.", delete_after=10)


async def setup(bot: commands.Bot) -> None:
    role_selection_service = getattr(bot, "role_selection_service", None)
    if role_selection_service is None:
        logger.error("role_selection_service is not initialized. LanguageRoleCog will not be loaded.")
        return
    await bot.add_cog(LanguageRoleCog(bot, role_selection_service))
    logger.info("LanguageRoleCog loaded.")
