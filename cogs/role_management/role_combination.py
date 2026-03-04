# cogs/role_management/role_combination.py

import asyncio
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from cogs.role_management.services.role_combination_service import RoleCombinationService

logger = logging.getLogger(__name__)


class RoleCombinationCog(commands.Cog):
    """Cog pour gérer les combinaisons de rôles."""

    def __init__(self, bot: commands.Bot, service: RoleCombinationService):
        self.bot = bot
        self._service = service
        self.member_locks: dict[int, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Slash command
    # ------------------------------------------------------------------

    @app_commands.command(name="role_combinations", description="Gérer les combinaisons de rôles.")
    @app_commands.describe(
        action="Action à effectuer (get, add, remove).",
        primary_role="Rôle principal de la combinaison.",
        secondary_role="Rôle secondaire de la combinaison.",
        combined_role="Rôle combiné résultant.",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Afficher les rôles combinés", value="get"),
            app_commands.Choice(name="Ajouter une combinaison de rôles", value="add"),
            app_commands.Choice(name="Supprimer une combinaison de rôles", value="remove"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def role_combinations_command(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        primary_role: Optional[discord.Role] = None,
        secondary_role: Optional[discord.Role] = None,
        combined_role: Optional[discord.Role] = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message("Commande utilisable uniquement dans un serveur.", ephemeral=True)
            return

        guild = interaction.guild
        act = action.value

        try:
            if act == "get":
                await interaction.response.defer(ephemeral=True)
                combos = await self._service.get_combinations(guild.id)
                if not combos:
                    await interaction.followup.send("Aucune combinaison configurée.", ephemeral=True)
                    return

                embed = discord.Embed(title="Combinaisons de Rôles", color=discord.Color.green())
                for c in combos:
                    p = guild.get_role(c.primary_role_id)
                    s = guild.get_role(c.secondary_role_id)
                    cb = guild.get_role(c.combined_role_id)
                    p_m = p.mention if p else f"ID:{c.primary_role_id}"
                    s_m = s.mention if s else f"ID:{c.secondary_role_id}"
                    cb_m = cb.mention if cb else f"ID:{c.combined_role_id}"
                    embed.add_field(name=f"{p_m} + {s_m}", value=f"→ {cb_m}", inline=False)

                    if len(embed) > 1900:
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        embed = discord.Embed(title="Combinaisons (suite)", color=discord.Color.green())

                if embed.fields:
                    await interaction.followup.send(embed=embed, ephemeral=True)

            elif act == "add":
                if not primary_role or not secondary_role or not combined_role:
                    await interaction.response.send_message(
                        "Spécifiez `primary_role`, `secondary_role` et `combined_role`.", ephemeral=True
                    )
                    return
                await self._service.add_combination(
                    guild.id, guild.name, primary_role.id, secondary_role.id, combined_role.id
                )
                await interaction.response.send_message(
                    f"Combinaison ajoutée : {primary_role.mention} + {secondary_role.mention} → {combined_role.mention}.",
                    ephemeral=True,
                )

            elif act == "remove":
                if not primary_role or not secondary_role:
                    await interaction.response.send_message(
                        "Spécifiez `primary_role` et `secondary_role`.", ephemeral=True
                    )
                    return
                ok = await self._service.remove_combination(guild.id, primary_role.id, secondary_role.id)
                if ok:
                    await interaction.response.send_message(
                        f"Combinaison supprimée : {primary_role.mention} + {secondary_role.mention}.", ephemeral=True
                    )
                else:
                    await interaction.response.send_message("Combinaison introuvable.", ephemeral=True)

        except Exception as e:
            logger.exception(f"Erreur role_combinations: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Une erreur est survenue.", ephemeral=True)

    # ------------------------------------------------------------------
    # Listener
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles != after.roles:
            await self._assign_combined_roles(after)

    async def _assign_combined_roles(self, member: discord.Member):
        if member.id not in self.member_locks:
            self.member_locks[member.id] = asyncio.Lock()

        async with self.member_locks[member.id]:
            try:
                combos = await self._service.get_combinations(member.guild.id)
                roles_to_add = []
                roles_to_remove = []
                member_role_ids = {r.id for r in member.roles}

                for c in combos:
                    has_p = c.primary_role_id in member_role_ids
                    has_s = c.secondary_role_id in member_role_ids
                    has_c = c.combined_role_id in member_role_ids
                    if has_p and has_s and not has_c:
                        roles_to_add.append(c.combined_role_id)
                        roles_to_remove.extend([c.primary_role_id, c.secondary_role_id])

                if not roles_to_add:
                    return

                remove_objs = [member.guild.get_role(r) for r in roles_to_remove]
                remove_objs = [r for r in remove_objs if r]
                if remove_objs:
                    try:
                        await member.remove_roles(*remove_objs, reason="Attribution rôles combinés.")
                    except discord.Forbidden:
                        await self._notify_mod(member.guild, f"Impossible de retirer les rôles de {member.mention}.")
                    except Exception as e:
                        logger.exception(f"Erreur retrait rôles {member}: {e}")

                add_objs = [member.guild.get_role(r) for r in roles_to_add]
                add_objs = [r for r in add_objs if r]
                if add_objs:
                    try:
                        await member.add_roles(*add_objs, reason="Attribution rôles combinés.")
                    except discord.Forbidden:
                        await self._notify_mod(member.guild, f"Impossible d'ajouter les rôles à {member.mention}.")
                    except Exception as e:
                        logger.exception(f"Erreur ajout rôles {member}: {e}")

            except Exception as e:
                logger.exception(f"Erreur assign_combined_roles {member}: {e}")
            finally:
                self.member_locks.pop(member.id, None)

    async def _notify_mod(self, guild: discord.Guild, message: str):
        channel_id = await self._service.get_moderation_channel_id(guild.id)
        if not channel_id:
            return
        channel = self.bot.get_channel(channel_id)
        if channel:
            try:
                await channel.send(message)
            except Exception as e:
                logger.error(f"Erreur notification modération: {e}")


async def setup(bot: commands.Bot):
    from database.services.role_combinations_service import RoleCombinationsService
    role_combos_svc = RoleCombinationsService(bot.db)
    service = RoleCombinationService(role_combos_svc, bot.channel_config_svc)
    await bot.add_cog(RoleCombinationCog(bot, service))
    logger.info("RoleCombinationCog chargé.")
