# cogs/role_management/role_combination.py

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List
from cogs.role_management.services.role_combination_service import RoleCombinationService
import logging
import asyncio

logger = logging.getLogger(__name__)

class RoleCombination(commands.Cog):
    """Cog pour gérer les combinaisons de rôles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Utilisez un dictionnaire pour gérer les verrous par membre afin d'éviter les conflits
        self.member_locks = {}

    @app_commands.command(name="role_combinations", description="Gérer les combinaisons de rôles.")
    @app_commands.describe(
        action="Action à effectuer (get, add, remove).",
        primary_role="Rôle principal de la combinaison.",
        secondary_role="Rôle secondaire de la combinaison.",
        combined_role="Rôle combiné résultant."
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Afficher les rôles combinés", value="get"),
            app_commands.Choice(name="Ajouter une combinaison de rôles", value="add"),
            app_commands.Choice(name="Supprimer une combinaison de rôles", value="remove"),
        ]
    )
    async def role_combinations_command(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        primary_role: Optional[discord.Role] = None,
        secondary_role: Optional[discord.Role] = None,
        combined_role: Optional[discord.Role] = None,
    ):
        """
        Gère les combinaisons de rôles en fonction de l'action spécifiée.
        """
        try:
            logger.debug(f"Commande role_combinations exécutée avec action={action.value}")

            if not interaction.guild:
                await interaction.response.send_message(
                    "Cette commande doit être exécutée dans un serveur Discord.", ephemeral=True
                )
                return

            guild_id = interaction.guild.id
            action_lower = action.value.lower()

            if action_lower == "get":
                # Defer the interaction to acknowledge it
                await interaction.response.defer(ephemeral=True)

                combinations = await RoleCombinationService.get_role_combinations(guild_id)
                if not combinations:
                    await interaction.followup.send("Aucune combinaison de rôles configurée.", ephemeral=True)
                    return

                embed = discord.Embed(title="Combinaisons de Rôles Configurées", color=discord.Color.green())
                for combo in combinations:
                    primary_role_obj = interaction.guild.get_role(combo["primary_role_id"])
                    secondary_role_obj = interaction.guild.get_role(combo["secondary_role_id"])
                    combined_role_obj = interaction.guild.get_role(combo["combined_role_id"])

                    # Utilisation de role.mention pour des mentions cliquables
                    primary_mention = primary_role_obj.mention if primary_role_obj else f"Rôle Manquant (ID : {combo['primary_role_id']})"
                    secondary_mention = secondary_role_obj.mention if secondary_role_obj else f"Rôle Manquant (ID : {combo['secondary_role_id']})"
                    combined_mention = combined_role_obj.mention if combined_role_obj else f"Rôle Manquant (ID : {combo['combined_role_id']})"

                    embed.add_field(
                        name=f"{primary_mention} + {secondary_mention}",
                        value=f"→ {combined_mention}",
                        inline=False,
                    )

                    # Vérifier si la longueur dépasse 1900 caractères (pour éviter de dépasser 2000)
                    if len(embed) > 1900:
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        embed = discord.Embed(title="Combinaisons de Rôles Configurées (suite)", color=discord.Color.green())

                # Envoyer le reste des rôles
                if embed.fields:
                    await interaction.followup.send(embed=embed, ephemeral=True)

            elif action_lower == "add":
                if not primary_role or not secondary_role or not combined_role:
                    await interaction.response.send_message(
                        "Veuillez spécifier les rôles `primary_role`, `secondary_role` et `combined_role`.", ephemeral=True
                    )
                    return

                success = await RoleCombinationService.add_role_combination(
                    guild_id, primary_role.id, secondary_role.id, combined_role.id
                )
                if success:
                    await interaction.response.send_message(
                        f"Combinaison de rôles ajoutée : **{primary_role.mention}** + **{secondary_role.mention}** → **{combined_role.mention}**.",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        "Une erreur est survenue lors de l'ajout de la combinaison de rôles.", ephemeral=True
                    )

            elif action_lower == "remove":
                if not primary_role or not secondary_role:
                    await interaction.response.send_message(
                        "Veuillez spécifier les rôles `primary_role` et `secondary_role` pour supprimer la combinaison.",
                        ephemeral=True
                    )
                    return

                success = await RoleCombinationService.remove_role_combination(
                    guild_id, primary_role.id, secondary_role.id
                )
                if success:
                    await interaction.response.send_message(
                        f"Combinaison de rôles supprimée : **{primary_role.mention}** + **{secondary_role.mention}**.",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        "Une erreur est survenue lors de la suppression de la combinaison de rôles.", ephemeral=True
                    )

            else:
                await interaction.response.send_message(
                    f"Action non reconnue : **{action.value}**.", ephemeral=True
                )

        except Exception as e:
            logger.exception(f"Erreur lors de l'exécution de role_combinations_command : {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Une erreur est survenue lors de l'exécution de cette commande.", ephemeral=True
                )


    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """
        Écoute les mises à jour des membres pour attribuer ou retirer des rôles combinés.
        """
        if before.roles != after.roles:
            await self.assign_combined_roles(after)

    async def assign_combined_roles(self, member: discord.Member):
        """
        Vérifie les combinaisons de rôles pour un membre et applique les changements.
        Supprime les rôles originaux et attribue les rôles combinés.
        En cas d'erreur de permissions, notifie dans le salon de modération configuré.
        """
        guild_id = member.guild.id

        # Utilisez un verrou par membre pour éviter les conflits simultanés
        if member.id not in self.member_locks:
            self.member_locks[member.id] = asyncio.Lock()

        async with self.member_locks[member.id]:
            try:
                # Récupérer toutes les combinaisons de rôles pour le serveur
                combinations = await RoleCombinationService.get_role_combinations(guild_id)

                roles_to_add = []
                roles_to_remove = []

                member_role_ids = {role.id for role in member.roles}

                # Identifier les combinaisons applicables
                for combo in combinations:
                    primary_role_id = combo["primary_role_id"]
                    secondary_role_id = combo["secondary_role_id"]
                    combined_role_id = combo["combined_role_id"]

                    has_primary = primary_role_id in member_role_ids
                    has_secondary = secondary_role_id in member_role_ids
                    has_combined = combined_role_id in member_role_ids

                    if has_primary and has_secondary and not has_combined:
                        roles_to_add.append(combined_role_id)
                        roles_to_remove.extend([primary_role_id, secondary_role_id])

                if not roles_to_add:
                    logger.debug(f"Aucune combinaison de rôles à ajouter pour {member.display_name}.")
                    return

                # Retirer les rôles originaux
                roles_to_remove_objs = [member.guild.get_role(role_id) for role_id in roles_to_remove]
                roles_to_remove_objs = [role for role in roles_to_remove_objs if role]

                if roles_to_remove_objs:
                    try:
                        await member.remove_roles(*roles_to_remove_objs, reason="Attribution automatique des rôles combinés.")
                        removed_roles = ", ".join([role.mention for role in roles_to_remove_objs])
                        logger.info(f"Rôles retirés de {member.display_name}: {removed_roles}")
                    except discord.Forbidden:
                        logger.error(f"Permissions insuffisantes pour retirer des rôles à {member.display_name}.")
                        await self.notify_moderation_channel(
                            guild_id,
                            f"Le bot n'a pas pu retirer les rôles de {member.mention} ({member.display_name}). Assurez-vous que les permissions sont correctes."
                        )
                    except Exception as e:
                        logger.exception(f"Erreur lors du retrait des rôles à {member.display_name}: {e}")
                        await self.notify_moderation_channel(
                            guild_id,
                            f"Une erreur s'est produite lors du retrait des rôles de {member.mention} ({member.display_name}). Détails : {e}"
                        )

                # Ajouter les rôles combinés
                roles_to_add_objs = [member.guild.get_role(role_id) for role_id in roles_to_add]
                roles_to_add_objs = [role for role in roles_to_add_objs if role]

                if roles_to_add_objs:
                    try:
                        await member.add_roles(*roles_to_add_objs, reason="Attribution automatique des rôles combinés.")
                        added_roles = ", ".join([role.mention for role in roles_to_add_objs])
                        logger.info(f"Rôles ajoutés à {member.display_name}: {added_roles}")
                    except discord.Forbidden:
                        logger.error(f"Permissions insuffisantes pour ajouter des rôles à {member.display_name}.")
                        await self.notify_moderation_channel(
                            guild_id,
                            f"Le bot n'a pas pu ajouter les rôles à {member.mention} ({member.display_name}). Assurez-vous que les permissions sont correctes."
                        )
                    except Exception as e:
                        logger.exception(f"Erreur lors de l'ajout des rôles à {member.display_name}: {e}")
                        await self.notify_moderation_channel(
                            guild_id,
                            f"Une erreur s'est produite lors de l'ajout des rôles à {member.mention} ({member.display_name}). Détails : {e}"
                        )

            except Exception as e:
                logger.exception(f"Erreur dans assign_combined_roles pour {member.display_name}: {e}")
            finally:
                # Vérifiez avant de supprimer le verrou
                if member.id in self.member_locks:
                    del self.member_locks[member.id]

    async def notify_moderation_channel(self, guild_id: int, message: str):
        """
        Envoie un message dans le salon de modération configuré pour un serveur.
        """
        try:
            # Requête à la base de données pour trouver le salon de modération
            channel_id = await self.get_moderation_channel(guild_id)
            if not channel_id:
                logger.warning(f"Aucun salon de modération configuré pour le serveur {guild_id}.")
                return

            # Récupérer l'objet du salon
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"Impossible de trouver le salon avec ID {channel_id} pour le serveur {guild_id}.")
                return

            # Envoyer le message
            await channel.send(message)
            logger.info(f"Message envoyé au salon de modération ({channel_id}) : {message}")

        except Exception as e:
            logger.exception(f"Erreur lors de l'envoi d'un message au salon de modération : {e}")

    
async def setup(bot: commands.Bot):
    await bot.add_cog(RoleCombination(bot))
    logger.info("RoleCombination Cog chargé.")
