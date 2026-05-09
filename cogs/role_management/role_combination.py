from __future__ import annotations

import asyncio
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from cogs.role_management.presenters import build_role_combinations_embed
from cogs.role_management.services import RoleCombinationService

logger = logging.getLogger(__name__)

ACTION_CHOICES = [
    app_commands.Choice(name="Afficher les roles combines", value="get"),
    app_commands.Choice(name="Ajouter une combinaison de roles", value="add"),
    app_commands.Choice(name="Supprimer une combinaison de roles", value="remove"),
]


class RoleCombinationCog(commands.Cog):
    def __init__(self, bot: commands.Bot, service: RoleCombinationService) -> None:
        self.bot = bot
        self._service = service
        self._member_locks: dict[tuple[int, int], asyncio.Lock] = {}
        logger.info("RoleCombinationCog initialized.")

    @app_commands.command(name="role_combinations", description="Gerer les combinaisons de roles.")
    @app_commands.describe(
        action="Action a effectuer",
        primary_role="Premier role de la combinaison",
        secondary_role="Second role de la combinaison",
        combined_role="Role resultant",
    )
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def role_combinations_command(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        primary_role: Optional[discord.Role] = None,
        secondary_role: Optional[discord.Role] = None,
        combined_role: Optional[discord.Role] = None,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Cette commande doit etre executee dans un serveur.", ephemeral=True)
            return

        action_value = action.value.lower()
        if action_value == "get":
            await interaction.response.defer(ephemeral=True)
            combinations = await self._service.list_combinations(interaction.guild.id)
            await interaction.followup.send(
                embed=build_role_combinations_embed(interaction.guild, combinations),
                ephemeral=True,
            )
            return

        if action_value == "add":
            if not primary_role or not secondary_role or not combined_role:
                await interaction.response.send_message(
                    "Veuillez specifier `primary_role`, `secondary_role` et `combined_role`.",
                    ephemeral=True,
                )
                return
            result = await self._service.save_combination(
                guild_id=interaction.guild.id,
                guild_name=interaction.guild.name,
                primary_role_id=primary_role.id,
                secondary_role_id=secondary_role.id,
                combined_role_id=combined_role.id,
            )
            if result.status == "invalid":
                await interaction.response.send_message(
                    "Combinaison invalide: les trois roles doivent etre differents.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                f"Combinaison ajoutee: {primary_role.mention} + {secondary_role.mention} -> {combined_role.mention}.",
                ephemeral=True,
            )
            return

        if action_value == "remove":
            if not primary_role or not secondary_role:
                await interaction.response.send_message(
                    "Veuillez specifier `primary_role` et `secondary_role`.",
                    ephemeral=True,
                )
                return
            result = await self._service.remove_combination(
                guild_id=interaction.guild.id,
                primary_role_id=primary_role.id,
                secondary_role_id=secondary_role.id,
            )
            if result.status == "removed":
                await interaction.response.send_message(
                    f"Combinaison supprimee: {primary_role.mention} + {secondary_role.mention}.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message("Combinaison introuvable.", ephemeral=True)
            return

        await interaction.response.send_message("Action non reconnue.", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.roles == after.roles or after.bot:
            return
        await self.apply_combinations(after)

    async def apply_combinations(self, member: discord.Member) -> None:
        key = (member.guild.id, member.id)
        lock = self._member_locks.setdefault(key, asyncio.Lock())
        try:
            async with lock:
                combinations = await self._service.list_combinations(member.guild.id)
                plan = self._service.build_assignment_plan(
                    current_role_ids={role.id for role in member.roles},
                    combinations=combinations,
                )
                if not plan.role_ids_to_add and not plan.role_ids_to_remove:
                    return

                roles_to_remove = [
                    role
                    for role_id in plan.role_ids_to_remove
                    if (role := member.guild.get_role(role_id)) is not None
                ]
                roles_to_add = [
                    role
                    for role_id in plan.role_ids_to_add
                    if (role := member.guild.get_role(role_id)) is not None
                ]

                if roles_to_add:
                    await member.add_roles(*roles_to_add, reason="Attribution automatique de role combine.")
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason="Attribution automatique de role combine.")
        except discord.Forbidden:
            logger.warning("Missing permissions to apply role combinations for member %s.", member.id)
        except Exception:
            logger.exception("Could not apply role combinations for member %s.", member.id)
        finally:
            if not lock.locked():
                self._member_locks.pop(key, None)


async def setup(bot: commands.Bot) -> None:
    service = getattr(bot, "role_combination_service", None)
    if service is None:
        logger.error("role_combination_service is not initialized. RoleCombinationCog will not be loaded.")
        return
    await bot.add_cog(RoleCombinationCog(bot, service))
    logger.info("RoleCombinationCog loaded.")
