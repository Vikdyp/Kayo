# cogs/configuration/roles_configuration.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Dict, Optional, List

from utils.confirmation_view import ConfirmationView
from cogs.configuration.services.role_service import RoleConfigurationService, normalize_key

logger = logging.getLogger(__name__)


class RolesConfiguration(commands.Cog):
    """Cog pour gérer la configuration des rôles."""

    PREDEFINED_ROLES = [
        "bon joueur", "booster", "ban", "mauvais joueur", "admin",
        "fer", "bronze", "argent", "or", "platine", "diamant", "ascendant",
        "immortel", "radiant", "sentinel", "duelist", "controller", "initiator", "fill",
        "tryhard", "e-sports", "chill", "tester", "francais", "anglais", "espagnol", "pc", "console",
        "quoicoubeh_top3"
    ]

    ACTION_CHOICES = [
        app_commands.Choice(name="Afficher ce qu'il manque", value="status"),
        app_commands.Choice(name="Afficher les rôles configurés", value="get"),
        app_commands.Choice(name="Configurer un rôle", value="set"),
        app_commands.Choice(name="Supprimer un rôle", value="remove"),
    ]

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        db = getattr(bot, "db", None)
        if db is None:
            raise RuntimeError("bot.db is not set. Attach a Db instance at startup.")

        self.service = RoleConfigurationService(db)
        logger.info("RolesConfiguration initialisé.")

    @app_commands.command(name="roles", description="Gérer la configuration des rôles.")
    @app_commands.describe(
        action="Action à effectuer",
        role_name="Clé du rôle (ex: argent, admin, bon joueur, ...)",
        role="Rôle Discord (nécessaire pour 'set')",
    )
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def roles_execute(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        role_name: Optional[str] = None,
        role: Optional[discord.Role] = None,
    ):
        try:
            await interaction.response.defer(thinking=True)

            if not interaction.guild:
                await interaction.followup.send(
                    "Cette commande doit être exécutée dans un serveur.",
                    ephemeral=True,
                )
                return

            guild = interaction.guild
            guild_id = guild.id
            guild_name = guild.name
            action_value = action.value.lower()

            # ---------- GET (configurés uniquement) ----------
            if action_value == "get":
                roles = await self.service.get_all(guild_id)
                if not roles:
                    await interaction.followup.send("Aucun rôle configuré.", ephemeral=True)
                    return

                embed = discord.Embed(title="Rôles configurés", color=discord.Color.green())
                for key in sorted(roles.keys()):
                    role_id = roles[key]
                    guild_role = guild.get_role(role_id)
                    value = guild_role.mention if guild_role else f"Rôle introuvable (id={role_id})"
                    embed.add_field(name=f"`{key}`", value=value, inline=False)

                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # ---------- STATUS (configurés + manquants) ----------
            if action_value == "status":
                roles = await self.service.get_all(guild_id)
                embed = self.build_roles_status_embed(guild, roles)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # ---------- SET ----------
            if action_value == "set":
                if not role_name or role is None:
                    await interaction.followup.send(
                        "Veuillez spécifier `role_name` et `role`.",
                        ephemeral=True,
                    )
                    return

                if role.guild.id != guild_id:
                    await interaction.followup.send(
                        "Le rôle doit appartenir à ce serveur.",
                        ephemeral=True,
                    )
                    return

                key = normalize_key(role_name)
                await self.service.set_one(
                    guild_id=guild_id,
                    guild_name=guild_name,
                    key=key,
                    role_id=role.id,
                    role_name=role.name,
                )

                await interaction.followup.send(
                    f"Rôle {role.mention} configuré pour **`{key}`**.",
                    ephemeral=True,
                )
                return

            # ---------- REMOVE ----------
            if action_value == "remove":
                if not role_name:
                    await interaction.followup.send(
                        "Veuillez spécifier `role_name`.",
                        ephemeral=True,
                    )
                    return

                key = normalize_key(role_name)
                existing = await self.service.get_one(guild_id, key)
                if existing is None:
                    await interaction.followup.send(
                        f"Aucune configuration trouvée pour **`{key}`**.",
                        ephemeral=True,
                    )
                    return

                async def confirmation_callback(result: Optional[bool]):
                    if result is True:
                        success = await self.service.remove_one(guild_id, key)
                        if success:
                            await interaction.followup.send(
                                f"Configuration supprimée pour **`{key}`**.",
                                ephemeral=True,
                            )
                        else:
                            await interaction.followup.send("Suppression échouée (DB).", ephemeral=True)
                    elif result is False:
                        await interaction.followup.send("Suppression annulée.", ephemeral=True)
                    else:
                        await interaction.followup.send("Délai de confirmation expiré.", ephemeral=True)

                view = ConfirmationView(interaction=interaction, callback=confirmation_callback)
                await interaction.followup.send(
                    f"Supprimer la configuration pour **`{key}`** ?",
                    view=view,
                    ephemeral=True,
                )
                return

            await interaction.followup.send("Action non prise en charge.", ephemeral=True)

        except Exception as e:
            logger.exception(f"[roles_execute] Erreur : {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors du traitement.",
                ephemeral=True,
            )

    def build_roles_status_embed(self, guild: discord.Guild, roles: Dict[str, int]) -> discord.Embed:
        roles = roles or {}
        missing_roles = [r for r in self.PREDEFINED_ROLES if r not in roles]

        embed = discord.Embed(title="Configuration des rôles", color=discord.Color.green())

        configured_text = self.format_configured_roles(guild, roles) or "Aucun rôle configuré."
        missing_text = self.format_missing_roles(missing_roles) or "Rien à configurer."

        embed.add_field(name=f"Configurés ({len(roles)})", value=configured_text, inline=False)
        embed.add_field(name=f"À configurer ({len(missing_roles)})", value=missing_text, inline=False)
        embed.add_field(
            name="Astuce",
            value="`/roles action:set role_name:<cle> role:<@role>`",
            inline=False,
        )
        return embed

    def format_configured_roles(self, guild: discord.Guild, roles: Dict[str, int]) -> str:
        lines: List[str] = []
        for role_key in sorted(roles.keys()):
            role_id = roles[role_key]
            guild_role = guild.get_role(role_id)
            role_mention = guild_role.mention if guild_role else f"rôle introuvable (id={role_id})"
            lines.append(f"- `{role_key}`: {role_mention}")
        return self.truncate_lines(lines)

    def format_missing_roles(self, missing_roles: List[str]) -> str:
        lines = [f"- `{role_key}`" for role_key in missing_roles]
        return self.truncate_lines(lines)

    def truncate_lines(self, lines: List[str], limit: int = 1024) -> str:
        if not lines:
            return ""
        output: List[str] = []
        total = 0
        for line in lines:
            line_len = len(line) + (1 if output else 0)
            if total + line_len > limit - 40:
                remaining = len(lines) - len(output)
                output.append(f"... +{remaining} autres")
                break
            output.append(line)
            total += line_len
        return "\n".join(output)

    @roles_execute.autocomplete("role_name")
    async def role_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        try:
            if not interaction.guild:
                return []

            guild_id = interaction.guild.id
            configured_roles = await self.service.get_all(guild_id)
            configured_keys = set(configured_roles.keys()) if configured_roles else set()

            current_lower = current.lower().strip()

            available = [
                r for r in self.PREDEFINED_ROLES
                if r not in configured_keys and current_lower in r.lower()
            ]

            return [app_commands.Choice(name=r, value=r) for r in available][:25]

        except Exception as e:
            logger.exception(f"[role_name_autocomplete] Erreur : {e}")
            return []


async def setup(bot: commands.Bot):
    await bot.add_cog(RolesConfiguration(bot))
    logger.info("RolesConfiguration Cog chargé.")
