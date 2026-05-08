# cogs/configuration/roles_configuration.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, List

from cogs.configuration.presenters import build_roles_list_embed, build_roles_status_embed
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

        service = getattr(bot, "role_configuration_service", None)
        if service is None:
            raise RuntimeError("bot.role_configuration_service is not set.")

        self.service = service
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

                embed = build_roles_list_embed(guild, roles)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # ---------- STATUS (configurés + manquants) ----------
            if action_value == "status":
                roles = await self.service.get_all(guild_id)
                embed = build_roles_status_embed(guild, roles, self.PREDEFINED_ROLES)
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

                success = await self.service.remove_one(guild_id, key)
                if success:
                    await interaction.followup.send(
                        f"Configuration supprimée pour **`{key}`**.",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send("Suppression échouée (DB).", ephemeral=True)
                return

            await interaction.followup.send("Action non prise en charge.", ephemeral=True)

        except Exception as e:
            logger.exception(f"[roles_execute] Erreur : {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors du traitement.",
                ephemeral=True,
            )

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
    try:
        cog = RolesConfiguration(bot)
    except RuntimeError as exc:
        logger.error("RolesConfiguration non chargé: %s", exc)
        return

    await bot.add_cog(cog)
    logger.info("RolesConfiguration Cog chargé.")
