# cogs/moderation/moderation.py
import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from datetime import datetime, timedelta
from typing import Optional

from cogs.moderation.services.moderation_service import ModerationService
from utils.confirmation_view import ConfirmationView
from utils.request_manager import enqueue_request

logger = logging.getLogger("moderation")

class Moderation(commands.Cog):
    """Cog pour gérer les bannissements, débannissements, avertissements et vérifications."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.check_bans_expired.start()
        logger.info("Initialisation du Cog de Modération.")

    def cog_unload(self):
        self.check_bans_expired.cancel()
        logger.info("Cog de Modération déchargé.")

    async def ensure_moderator_permissions(self, interaction: discord.Interaction):
        """Vérifie que l'utilisateur ayant lancé la commande dispose des permissions de modération nécessaires."""
        if not interaction.guild:
            await interaction.followup.send("Cette commande doit être exécutée dans un serveur.", ephemeral=True)
            return False

        # Exemple de vérification de permission : vérifier si le membre a la permission de bannir
        # Cela dépend de votre logique interne. Ici on vérifie la permission de bannir des membres.
        if not interaction.user.guild_permissions.ban_members:
            await interaction.followup.send(
                "Vous n'avez pas les permissions nécessaires pour utiliser cette commande.",
                ephemeral=True
            )
            return False
        return True

    @app_commands.command(name="moderation", description="Exécute des actions de modération.")
    @app_commands.describe(
        action="Action à effectuer",
        user="Utilisateur cible",
        reason="Raison de l'action (si applicable)",
        duration_minutes="Durée en minutes (pour un bannissement temporaire)"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Bannir", value="ban"),
            app_commands.Choice(name="Débannir", value="unban"),
            app_commands.Choice(name="Avertir", value="warn"),
            app_commands.Choice(name="Vérifier le statut", value="check_status")
        ]
    )
    @enqueue_request()
    async def moderation_execute(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        user: Optional[discord.Member] = None,
        reason: Optional[str] = None,
        duration_minutes: Optional[int] = None
    ):
        """Exécute une action de modération en fonction de l'option spécifiée."""
        
        if not await self.ensure_moderator_permissions(interaction):
            return

        try:
            if action.value == "ban":
                if not user or not reason:
                    await interaction.followup.send(
                        "Veuillez spécifier un utilisateur et une raison pour le bannissement.\n"
                        "Exemple : `/moderation action:Bannir user:@Utilisateur reason:VotreRaison`",
                        ephemeral=True
                    )
                    return

                ban_type = "temp" if duration_minutes else "perma"
                success = await self.ban_member(
                    guild=interaction.guild,
                    member=user,
                    ban_type=ban_type,
                    reason=reason,
                    banned_by=interaction.user,
                    duration_minutes=duration_minutes
                )
                if success:
                    await interaction.followup.send(
                        f"{user.display_name} a été banni(e) {'temporairement' if ban_type == 'temp' else 'définitivement'}.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "Une erreur est survenue lors du bannissement. Veuillez vérifier les rôles et permissions du bot.",
                        ephemeral=True
                    )

            elif action.value == "unban":
                if not user:
                    await interaction.followup.send(
                        "Veuillez spécifier un utilisateur pour le débannissement.\n"
                        "Exemple : `/moderation action:Débannir user:@Utilisateur`",
                        ephemeral=True
                    )
                    return

                await self.unban_member(
                    guild=interaction.guild,
                    user_id=user.id,
                    reason=reason
                )
                await interaction.followup.send(
                    f"{user.display_name} a été débanni(e).",
                    ephemeral=True
                )

            elif action.value == "warn":
                if not user or not reason:
                    await interaction.followup.send(
                        "Veuillez spécifier un utilisateur et une raison pour l'avertissement.\n"
                        "Exemple : `/moderation action:Avertir user:@Utilisateur reason:VotreRaison`",
                        ephemeral=True
                    )
                    return

                await ModerationService.add_warning(user.id)
                await interaction.followup.send(
                    f"{user.display_name} a été averti(e). Raison : {reason}",
                    ephemeral=True
                )

            elif action.value == "check_status":
                if not user:
                    await interaction.followup.send(
                        "Veuillez spécifier un utilisateur pour vérifier son statut.\n"
                        "Exemple : `/moderation action:Vérifier le statut user:@Utilisateur`",
                        ephemeral=True
                    )
                    return

                ban_info = await ModerationService.get_ban_info(user.id)  # user.id est l'ID Discord
                if not ban_info:
                    await interaction.followup.send(
                        f"{user.mention} n'est pas banni(e).",  # Mention cliquable pour l'utilisateur
                        ephemeral=True
                    )
                    return

                # Détails du bannissement
                ban_type = ban_info.get("type_name", "Inconnu")
                ban_reason = ban_info.get("ban_reason", "Aucune raison fournie")
                ban_end = ban_info.get("ban_end", "Permanent")
                banned_at = ban_info.get("banned_at", "Inconnu")

                # Récupération de l'utilisateur qui a banni
                banned_by_id = ban_info.get("banned_by")
                banned_by_mention = "Inconnu"
                if banned_by_id:
                    # Convertir l'ID interne en ID Discord
                    discord_banned_by_id = await ModerationService.get_discord_id(banned_by_id)
                    if discord_banned_by_id:
                        try:
                            banned_by_mention = f"<@{discord_banned_by_id}>"  # Format de mention cliquable
                        except discord.NotFound:
                            banned_by_mention = "Utilisateur introuvable"
                    else:
                        banned_by_mention = "Utilisateur inconnu"

                # Mention cliquable de l'utilisateur banni
                banned_user_mention = f"<@{user.id}>"

                await interaction.followup.send(
                    f"**Statut de {banned_user_mention}** :\n"  # Mention cliquable pour le banni
                    f"Type : {ban_type}\n"
                    f"Raison : {ban_reason}\n"
                    f"Banni(e) le : {banned_at}\n"
                    f"Fin de ban : {ban_end}\n"
                    f"Banni(e) par : {banned_by_mention}",  # Mention cliquable pour celui qui a banni
                    ephemeral=True
                )



        except Exception as e:
            logger.exception(f"Erreur dans moderation_execute : {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors du traitement de votre requête. code 001",
                ephemeral=True
            )

    async def ban_member(
        self,
        guild: discord.Guild,
        member: discord.Member,
        ban_type: str,
        reason: str,
        banned_by: discord.User,
        duration_minutes: Optional[int] = None
    ) -> bool:
        """Bannit un membre avec sauvegarde des rôles et ajout du rôle 'ban'."""
        logger.debug(f"Début du bannissement de {member.display_name} (ID: {member.id}) dans {guild.name}.")

        # Sauvegarder les rôles
        await self.backup_roles(member)

        # Retirer tous les rôles (sauf le rôle par défaut)
        roles_to_remove = [role for role in member.roles if role != guild.default_role]
        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=reason)
                logger.info(f"Rôles supprimés pour {member.display_name}: {[role.name for role in roles_to_remove]}")
        except discord.Forbidden:
            logger.error(f"Impossible de supprimer les rôles de {member.display_name}. Permissions manquantes.")
            return False
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de la suppression des rôles de {member.display_name}: {e}")
            return False

        # Ajouter le rôle 'ban'
        ban_role_id = await ModerationService.get_ban_role_id(guild.id)
        if not ban_role_id:
            logger.error("Le rôle 'ban' n'est pas configuré.")
            return False

        ban_role = guild.get_role(ban_role_id)
        if not ban_role:
            logger.error(f"Rôle 'ban' avec l'ID {ban_role_id} introuvable dans le serveur {guild.name}.")
            return False

        try:
            await member.add_roles(ban_role, reason=reason)
            logger.info(f"Rôle 'ban' appliqué à {member.display_name}.")
        except discord.Forbidden:
            logger.error(f"Impossible d'appliquer le rôle 'ban' à {member.display_name}. Permissions manquantes.")
            return False
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de l'application du rôle 'ban' à {member.display_name}: {e}")
            return False

        # Définir la durée du bannissement si temporaire
        ban_end = None
        if ban_type == "temp" and duration_minutes:
            ban_end = datetime.utcnow() + timedelta(minutes=duration_minutes)

        logger.debug(
            f"Ajout du bannissement : user_id={member.id}, ban_type_id={1 if ban_type == 'temp' else 2}, "
            f"reason={reason}, banned_by={banned_by.id}, ban_end={ban_end}"
        )

        # Ajouter les informations de bannissement dans la table 'bans'
        await ModerationService.add_ban(
            user_id=member.id,
            ban_type_id=1 if ban_type == "temp" else 2,
            reason=reason,
            banned_by=banned_by.id,
            ban_end=ban_end
        )

        # Envoyer un DM à l'utilisateur
        try:
            duration_text = "Permanente" if ban_type == "perma" else f"Jusqu'à {ban_end}"
            await member.send(
                f"Vous avez été banni(e) du serveur **{guild.name}**.\n"
                f"**Raison :** {reason}\n"
                f"**Durée :** {duration_text}\n"
                f"**Banni(e) par :** {banned_by.display_name}\n\n"
                f"Pour demander un débannissement, veuillez contacter l'administration."
            )
            logger.info(f"DM envoyé à {member.display_name} pour le bannissement.")
        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer un DM à {member.display_name}.")
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de l'envoi du DM à {member.display_name}: {e}")

        return True

    async def unban_member(self, guild: discord.Guild, user_id: int, reason: Optional[str] = None) -> None:
        """Débanni un membre et restaure ses rôles."""
        logger.debug(f"Tentative de débannissement de l'utilisateur ID: {user_id} dans {guild.name}. Raison: {reason}")

        # Convertir l'ID Discord en ID interne
        internal_id = await ModerationService.get_or_create_user_id(user_id)
        if not internal_id:
            logger.error(f"Impossible de convertir l'ID Discord {user_id} en ID interne pour le débannissement.")
            return

        # Récupérer les informations de bannissement
        ban_info = await ModerationService.get_ban_info(user_id)
        if not ban_info:
            logger.warning(f"Aucune donnée de bannissement trouvée pour l'utilisateur Discord ID {user_id}.")
            return

        member = guild.get_member(user_id)
        if member:
            # Restauration des rôles
            await self.restore_roles(member)
            # Retirer le rôle ban s'il est encore appliqué
            ban_role_id = await ModerationService.get_ban_role_id(guild.id)
            if ban_role_id:
                ban_role = guild.get_role(ban_role_id)
                if ban_role in member.roles:
                    try:
                        await member.remove_roles(ban_role, reason="Fin de ban")
                        logger.info(f"Rôle 'ban' retiré de {member.display_name}.")
                    except discord.Forbidden:
                        logger.error(f"Impossible de retirer le rôle 'ban' de {member.display_name}. Permissions manquantes.")
                    except discord.HTTPException as e:
                        logger.error(f"Erreur HTTP lors du retrait du rôle 'ban' de {member.display_name}: {e}")

        # Supprimer les informations de bannissement
        await ModerationService.remove_ban(internal_id)

        # Informer l'utilisateur via DM
        try:
            user = await self.bot.fetch_user(user_id)
            if user:
                await user.send(
                    f"Vous avez été débanni(e) du serveur **{guild.name}**.\n"
                    f"**Raison :** {reason or 'Expiration du bannissement temporaire ou décision du staff.'}"
                )
                logger.info(f"DM envoyé à l'utilisateur Discord ID {user_id} pour le débannissement.")
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de l'envoi du DM de débannissement à l'utilisateur Discord ID {user_id}: {e}")

    async def backup_roles(self, member: discord.Member) -> None:
        """Sauvegarde les rôles actuels d'un membre dans 'role_backups'."""
        roles_to_backup = [
            role.id for role in member.roles
            if role != member.guild.default_role and role.name.lower() != "ban"
        ]

        if roles_to_backup:
            # Convertir l'ID Discord en ID interne
            internal_id = await ModerationService.get_or_create_user_id(member.id)
            if internal_id:
                success = await ModerationService.save_roles_backup(internal_id, roles_to_backup)
                if success:
                    logger.info(f"Rôles de {member.display_name} sauvegardés: {roles_to_backup}")
                else:
                    logger.error(f"Échec de la sauvegarde des rôles pour {member.display_name}.")
            else:
                logger.error(f"Échec de la conversion de l'ID Discord {member.id} en ID interne pour la sauvegarde des rôles.")
        else:
            logger.warning(f"Aucun rôle à sauvegarder pour {member.display_name}.")

    async def restore_roles(self, member: discord.Member) -> None:
        """Restaure les rôles sauvegardés d'un membre."""
        # Convertir l'ID Discord en ID interne
        internal_id = await ModerationService.get_or_create_user_id(member.id)
        if not internal_id:
            logger.error(f"Impossible de convertir l'ID Discord {member.id} en ID interne pour la restauration des rôles.")
            return

        roles = await ModerationService.get_roles_backup(internal_id)

        if not roles:
            logger.warning(f"Aucune sauvegarde de rôles trouvée pour {member.display_name}.")
        else:
            roles_to_add = [
                discord.utils.get(member.guild.roles, id=role_id)
                for role_id in roles
            ]
            roles_to_add = [role for role in roles_to_add if role is not None]

            if roles_to_add:
                try:
                    await member.add_roles(*roles_to_add, reason="Restauration des rôles après débannissement.")
                    logger.info(f"Rôles restaurés pour {member.display_name}: {[role.name for role in roles_to_add]}")
                except discord.Forbidden:
                    logger.error(f"Permission refusée pour restaurer les rôles de {member.display_name}.")
                except discord.HTTPException as e:
                    logger.exception(f"Erreur lors de la restauration des rôles de {member.display_name}: {e}")
            else:
                logger.warning(f"Aucun rôle valide à restaurer pour {member.display_name}.")

        await ModerationService.delete_roles_backup(internal_id)
        logger.debug(f"Données de rôles supprimées pour {member.display_name} après restauration.")

    @tasks.loop(minutes=1)
    async def check_bans_expired(self):
        """Vérifie régulièrement les bannissements temporaires expirés et débannit automatiquement les membres."""
        now = datetime.utcnow()
        expired_bans = await ModerationService.get_expired_bans(now)

        count = 0
        for ban in expired_bans:
            internal_user_id = ban["user_id"]  # Ceci est l'ID interne
            # Récupérer l'ID Discord à partir de l'ID interne
            discord_id = await ModerationService.get_discord_id(internal_user_id)
            if not discord_id:
                logger.error(f"Impossible de récupérer l'ID Discord pour l'ID interne {internal_user_id}.")
                continue

            for guild in self.bot.guilds:
                # Tenter de débannir dans chaque guilde où l'utilisateur est banni
                await self.unban_member(guild, discord_id, reason="Expiration du bannissement temporaire")
                count += 1

        if count > 0:
            logger.info(f"{count} bannissement(s) expiré(s) traité(s) avec succès.")

    @check_bans_expired.before_loop
    async def before_check_bans_expired(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
    logger.info("Moderation Cog chargé avec succès.")
