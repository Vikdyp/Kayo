# cogs/configuration/role_mappings_configuration.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Dict, Optional, List

from cogs.configuration.services.role_service import ServerRoleService

logger = logging.getLogger(__name__)

class RolesConfiguration(commands.Cog):
    """Cog pour gérer la configuration des rôles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("RolesConfiguration initialisé.")

    # Liste plate des rôles prédéfinis
    PREDEFINED_ROLES = [
        "bon joueur", "booster", "ban", "mauvais joueur", "admin",
        "fer", "bronze", "argent", "or", "platine", "diamant", "ascendant",
        "immortel", "radiant", "sentinel", "duelist", "controller", "initiator", "fill",
        "tryhard", "e-sports", "chill", "tester", "francais", "anglais", "espagnol", "pc", "console",
        "quoicoubeh_top3"
    ]

    @app_commands.command(name="roles", description="Exécute des actions sur la configuration des rôles.")
    @app_commands.describe(
        action="Action à effectuer",
        role_name="Nom du rôle (nécessaire pour 'set' ou 'remove')",
        role="Rôle Discord (nécessaire pour 'set')"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Afficher ce qu'il manque", value="status"),
            app_commands.Choice(name="Afficher les rôles configurés", value="get"),
            app_commands.Choice(name="Configurer un rôle", value="set"),
            app_commands.Choice(name="Supprimer un rôle", value="remove")
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def roles_execute(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        role_name: Optional[str] = None,
        role: Optional[discord.Role] = None
    ):
        """
        /roles action:<get|set|remove> role_name:<str> role:<@role>
        """
        try:
            await interaction.response.defer(thinking=True)
            # Vérification: commande utilisée dans un serveur ?
            if not interaction.guild:
                await interaction.followup.send(
                    "Cette commande doit être exécutée dans un serveur.", ephemeral=True
                )
                return

            guild_id = interaction.guild.id
            guild_name = interaction.guild.name  # pour le stockage dans serveur_id

            # =========== GET ===========
            if action.value == "get":
                roles = await ServerRoleService.get_roles_config(guild_id, guild_name)
                embed = self.build_roles_status_embed(interaction.guild, roles)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
                if not roles:
                    await interaction.followup.send("Aucun rôle configuré.", ephemeral=True)
                    return

                role_list = "**Rôles Configurés:**\n"
                for role_key, role_id in roles.items():
                    guild_role = interaction.guild.get_role(role_id)
                    if guild_role:
                        role_mention = guild_role.mention
                    else:
                        role_mention = "Rôle non trouvé"
                    role_list += f"• **{role_key.capitalize()}**: {role_mention}\n"

                    # Eviter de dépasser la limite de 2000 caractères
                    if len(role_list) > 1900:
                        await interaction.followup.send(role_list, ephemeral=True)
                        role_list = ""

                if role_list:
                    await interaction.followup.send(role_list, ephemeral=True)

            # =========== STATUS ===========
            elif action.value == "status":
                roles = await ServerRoleService.get_roles_config(guild_id, guild_name)
                embed = self.build_roles_status_embed(interaction.guild, roles)
                await interaction.followup.send(embed=embed, ephemeral=True)

            # =========== SET ===========
            elif action.value == "set":
                if not role_name or not role:
                    await interaction.followup.send(
                        "Veuillez spécifier le nom du rôle (role_name) et le rôle Discord (role).",
                        ephemeral=True
                    )
                    return

                success = await ServerRoleService.set_role_for_action(
                    guild_id, guild_name, role_name, role.id
                )
                if success:
                    await interaction.followup.send(
                        f"Rôle **{role.name}** configuré pour **{role_name.capitalize()}**.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "Une erreur est survenue lors de la configuration.", ephemeral=True
                    )

            # =========== REMOVE ===========
            elif action.value == "remove":
                if not role_name:
                    await interaction.followup.send(
                        "Veuillez spécifier un rôle (role_name) à supprimer.",
                        ephemeral=True
                    )
                    return

                success = await ServerRoleService.remove_role_for_action(
                    guild_id, guild_name, role_name
                )
                if success:
                    await interaction.followup.send(
                        f"Configuration pour **{role_name.capitalize()}** supprimée.", ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "Aucune configuration trouvée pour ce rôle.", ephemeral=True
                    )

            else:
                await interaction.followup.send(
                    "Action non prise en charge.", ephemeral=True
                )

        except Exception as e:
            logger.exception(f"[roles_execute] Erreur : {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors du traitement de votre requête.", ephemeral=True
            )

    def build_roles_status_embed(self, guild: discord.Guild, roles: Dict[str, int]) -> discord.Embed:
        roles = roles or {}
        missing_roles = [role for role in self.PREDEFINED_ROLES if role not in roles]

        embed = discord.Embed(title="Configuration des roles", color=discord.Color.green())
        configured_text = self.format_configured_roles(guild, roles) or "Aucun role configure."
        missing_text = self.format_missing_roles(missing_roles) or "Rien a configurer."

        embed.add_field(name=f"Configures ({len(roles)})", value=configured_text, inline=False)
        embed.add_field(name=f"A configurer ({len(missing_roles)})", value=missing_text, inline=False)
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
            if guild_role:
                role_mention = guild_role.mention
            else:
                role_mention = "role non trouve"
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

    @roles_execute.autocomplete('role_name')
    async def role_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        """
        Propose l'auto-complétion pour les noms de rôles non encore configurés.
        """
        try:
            if not interaction.guild:
                return []

            guild_id = interaction.guild.id
            guild_name = interaction.guild.name

            configured_roles = await ServerRoleService.get_roles_config(guild_id, guild_name)
            configured_role_keys = set(configured_roles.keys()) if configured_roles else set()

            # Suggérer uniquement les rôles non encore configurés et correspondant au texte actuel
            available_roles = [
                role
                for role in self.PREDEFINED_ROLES
                if role not in configured_role_keys
                and (current.lower() in role.lower())
            ]

            return [
                app_commands.Choice(name=role.capitalize(), value=role)
                for role in available_roles
            ][:25]

        except Exception as e:
            logger.exception(f"[role_name_autocomplete] Erreur : {e}")
            return []

async def setup(bot: commands.Bot):
    await bot.add_cog(RolesConfiguration(bot))
    logger.info("RolesConfiguration Cog chargé.")
