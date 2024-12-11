# cogs/moderation/moderation.py

import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from cogs.utilities.data_manager import DataManager
from cogs.utilities.confirmation_view import ModerationConfirmationView  # Assurez-vous que ce module existe et fonctionne correctement

logger = logging.getLogger("discord.moderation")

class Moderation(commands.Cog):
    """Cog pour gérer les bannissements et la sauvegarde/restauration des rôles des membres."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.check_bans_expired.start()
        logger.info("Initialisation du Cog de Modération.")

    def cog_unload(self):
        self.check_bans_expired.cancel()
        logger.info("Cog de Modération déchargé.")

    async def get_moderation_data(self) -> Dict:
        """Récupère les données de modération."""
        return await self.data.get_moderation_data()

    async def save_moderation_data(self, mod_data: Dict) -> None:
        """Sauvegarde les données de modération."""
        await self.data.save_moderation_data(mod_data)

    async def backup_roles(self, member: discord.Member) -> None:
        """Sauvegarde les rôles actuels d'un membre (excluant le rôle par défaut et le rôle 'ban')."""
        roles_to_backup = [
            role.id for role in member.roles 
            if role != member.guild.default_role and role.name.lower() != "ban"
        ]

        if roles_to_backup:
            role_backup = await self.data.get_role_backup()
            role_backup[str(member.id)] = roles_to_backup
            await self.data.save_role_backup(role_backup)
            logger.info(f"Rôles de {member.display_name} sauvegardés: {roles_to_backup}")
        else:
            logger.warning(f"Aucun rôle à sauvegarder pour {member.display_name}.")

    async def restore_roles(self, member: discord.Member) -> None:
        """Restaure les rôles sauvegardés d'un membre."""
        role_backup = await self.data.get_role_backup()
        roles = role_backup.get(str(member.id), [])

        if not roles:
            logger.warning(f"Aucune sauvegarde de rôles trouvée pour {member.display_name}.")
            return

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

        # Supprimer les données de sauvegarde après restauration
        role_backup.pop(str(member.id), None)
        await self.data.save_role_backup(role_backup)
        logger.debug(f"Données de rôles supprimées pour {member.display_name} après restauration.")

    async def ban_member(
        self, 
        member: discord.Member, 
        ban_type: str, 
        reason: str, 
        banned_by: discord.User, 
        duration_minutes: Optional[int] = None
    ) -> None:
        """Banni un membre avec sauvegarde des rôles et ajout du rôle 'ban'."""
        guild = member.guild
        mod_data = await self.get_moderation_data()

        logger.debug(f"Début du bannissement de {member.display_name} (ID: {member.id}).")

        # Sauvegarder les rôles
        await self.backup_roles(member)

        # Retirer tous les rôles (sauf le rôle par défaut)
        roles_to_remove = [role for role in member.roles if role != guild.default_role]
        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason=reason)
                logger.info(f"Rôles supprimés pour {member.display_name}: {[role.name for role in roles_to_remove]}")
            except discord.Forbidden:
                logger.error(f"Impossible de supprimer les rôles de {member.display_name}. Permissions manquantes.")
                return
            except discord.HTTPException as e:
                logger.error(f"Erreur HTTP lors de la suppression des rôles de {member.display_name}: {e}")
                return

        # Ajouter le rôle 'ban'
        config = await self.data.get_config()
        ban_role_id = config.get("roles", {}).get("ban")
        if ban_role_id:
            try:
                ban_role = guild.get_role(int(ban_role_id))  # Assure-toi que l'ID est un entier
            except ValueError:
                logger.error(f"L'ID du rôle 'ban' dans config.json n'est pas un entier valide: {ban_role_id}")
                return

            if ban_role:
                try:
                    await member.add_roles(ban_role, reason=reason)
                    logger.info(f"Rôle 'ban' appliqué à {member.display_name}.")
                except discord.Forbidden:
                    logger.error(f"Impossible d'appliquer le rôle 'ban' à {member.display_name}. Permissions manquantes.")
                    return
                except discord.HTTPException as e:
                    logger.error(f"Erreur HTTP lors de l'application du rôle 'ban' à {member.display_name}: {e}")
                    return
            else:
                logger.error(f"Rôle 'ban' avec l'ID {ban_role_id} introuvable dans le serveur.")
                return
        else:
            logger.error("ID du rôle 'ban' non trouvé dans le fichier config.json.")
            return

        # Définir la durée du bannissement si temporaire
        now = datetime.utcnow()
        ban_end = None
        if ban_type == "temp" and duration_minutes is not None:
            ban_end = (now + timedelta(minutes=duration_minutes)).isoformat()
            logger.debug(f"Bannissement temporaire pour {member.display_name} jusqu'à {ban_end}.")

        user_data = {
            "ban_type": ban_type,
            "ban_end": ban_end,
            "ban_reason": reason,
            "banned_by": banned_by.id,
            "banned_at": now.isoformat(),
            "warnings_count": 0,
            "unban_request_msg_id": None,
            "unban_request_channel_id": None
        }

        mod_data.setdefault("bans", {})[str(member.id)] = user_data
        await self.save_moderation_data(mod_data)

        # Envoyer un DM à l'utilisateur
        try:
            await member.send(
                f"Vous avez été banni du serveur **{guild.name}**.\n"
                f"**Raison :** {reason}\n"
                f"**Banni par :** {banned_by.display_name}\n"
                f"**Note :** Après 3 avertissements, vous serez banni temporairement pendant une semaine. Après 5 avertissements, vous serez banni définitivement."
            )
            logger.info(f"DM envoyé à {member.display_name} pour le bannissement.")
        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer un DM à {member.display_name}.")
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de l'envoi du DM à {member.display_name}: {e}")

    async def unban_member(self, user_id: int, reason: Optional[str] = None) -> None:
        """Débanni un membre et restaure ses rôles."""
        logger.debug(f"Tentative de débannissement de l'utilisateur ID: {user_id}. Raison: {reason}")

        # Obtenir le guild (suppose que le bot est sur un seul serveur)
        if len(self.bot.guilds) != 1:
            logger.error("Le bot est sur plusieurs serveurs. Veuillez spécifier le serveur.")
            return
        guild = self.bot.guilds[0]
        logger.debug(f"Serveur sélectionné: {guild.name} (ID: {guild.id})")

        mod_data = await self.get_moderation_data()
        logger.debug(f"Données de modération avant unban: {mod_data.get('bans', {})}")

        ban_info = mod_data.get("bans", {}).pop(str(user_id), None)
        if not ban_info:
            logger.warning(f"Tentative de débannissement d'un utilisateur non banni (ID: {user_id}).")
            await self.save_moderation_data(mod_data)  # Assure-toi de sauvegarder même si l'utilisateur n'était pas banni
            return
        logger.debug(f"Informations de bannissement trouvées pour l'utilisateur {user_id}: {ban_info}")

        # Débannir l'utilisateur en retirant le rôle 'ban'
        try:
            member = guild.get_member(user_id)
            if member:
                logger.debug(f"Utilisateur trouvé dans le serveur: {member.display_name} (ID: {member.id})")
                config = await self.data.get_config()
                ban_role_id = config.get("roles", {}).get("ban")
                if ban_role_id:
                    try:
                        ban_role = guild.get_role(int(ban_role_id))  # Assure-toi que l'ID est un entier
                    except ValueError:
                        logger.error(f"L'ID du rôle 'ban' dans config.json n'est pas un entier valide: {ban_role_id}")
                        return

                    if ban_role:
                        logger.debug(f"Rôle 'ban' trouvé: {ban_role.name} (ID: {ban_role.id})")
                        if ban_role in member.roles:
                            await member.remove_roles(ban_role, reason=reason or "Débannissement automatique")
                            logger.info(f"Rôle 'ban' retiré de {member.display_name}.")
                        else:
                            logger.warning(f"L'utilisateur {member.display_name} n'a pas le rôle 'ban'.")
                    else:
                        logger.error(f"Rôle 'ban' avec l'ID {ban_role_id} introuvable dans le serveur.")
                else:
                    logger.error("ID du rôle 'ban' non trouvé dans le fichier config.json.")
            else:
                logger.warning(f"Membre avec l'ID {user_id} n'est pas présent dans le serveur.")
        except discord.Forbidden:
            logger.error(f"Impossible de retirer le rôle 'ban' de l'utilisateur ID: {user_id}. Permissions manquantes.")
            return
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors du retrait du rôle 'ban' de l'utilisateur ID: {user_id}: {e}")
            return

        # Restauration des rôles
        try:
            user = await self.bot.fetch_user(user_id)
            if user:
                logger.debug(f"Utilisateur récupéré via fetch_user: {user.display_name} (ID: {user.id})")
                member_to_restore = guild.get_member(user_id)
                if member_to_restore:
                    await self.restore_roles(member_to_restore)
                else:
                    logger.warning(f"Utilisateur {user.display_name} non trouvé dans le serveur lors de la restauration des rôles.")
            else:
                logger.warning(f"Utilisateur avec l'ID {user_id} non trouvé via fetch_user.")
        except discord.NotFound:
            logger.warning(f"Utilisateur avec l'ID {user_id} non trouvé lors de la tentative de restauration des rôles.")
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de la restauration des rôles pour l'utilisateur ID: {user_id}: {e}")

        # Sauvegarder les données de modération mises à jour
        await self.save_moderation_data(mod_data)
        logger.debug(f"Données de modération après unban: {mod_data.get('bans', {})}")

        # Informer l'utilisateur via DM si le membre est dans le serveur
        if member:
            try:
                await user.send(
                    f"Vous avez été débanni du serveur **{guild.name}**.\n**Raison :** {reason or 'Aucune raison fournie'}"
                )
                logger.info(f"DM envoyé à l'utilisateur {user.display_name} pour le débannissement.")
            except discord.Forbidden:
                logger.warning(f"Impossible d'envoyer un DM à l'utilisateur {user.display_name}.")
            except discord.HTTPException as e:
                logger.error(f"Erreur HTTP lors de l'envoi du DM à l'utilisateur {user.display_name}: {e}")
        else:
            logger.debug(f"L'utilisateur {user.display_name} n'est pas dans le serveur. Aucun DM envoyé.")

    @tasks.loop(minutes=1)
    async def check_bans_expired(self):
        """Vérifie régulièrement les bannissements temporaires expirés et débannit automatiquement les membres."""
        logger.debug("Début de la vérification des bannissements expirés.")
        now = datetime.utcnow()
        mod_data = await self.get_moderation_data()
        to_unban = []
        bans = mod_data.get("bans", {})

        for uid, ban_info in bans.items():
            if ban_info.get("ban_type") == "temp" and ban_info.get("ban_end"):
                try:
                    end_time = datetime.fromisoformat(ban_info["ban_end"])
                    if now > end_time:
                        to_unban.append(uid)
                        logger.debug(f"Bannissement temporaire expiré pour l'utilisateur ID: {uid}.")
                except ValueError:
                    logger.error(f"Format de date invalide pour l'utilisateur {uid}: {ban_info['ban_end']}")

        if to_unban:
            logger.info(f"Nombre de membres à débannir automatiquement: {len(to_unban)}.")
            for uid in to_unban:
                user_id = int(uid)
                await self.unban_member(user_id, reason="Bannissement temporaire expiré")
            # Mettre à jour les données après les débannissements
            for uid in to_unban:
                bans.pop(uid, None)
            await self.save_moderation_data(mod_data)
            logger.info("Membres débannis automatiquement et données de modération mises à jour.")
        else:
            logger.debug("Aucun bannissement temporaire expiré trouvé.")

    @check_bans_expired.before_loop
    async def before_check_bans_expired(self):
        await self.bot.wait_until_ready()
        logger.debug("Tâche 'check_bans_expired' prête à démarrer.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Restaurer les rôles d'un membre lorsqu'il rejoint le serveur après un débannissement."""
        logger.debug(f"L'utilisateur {member.display_name} a rejoint le serveur. Vérification des rôles à restaurer.")
        mod_data = await self.get_moderation_data()
        ban_info = mod_data.get("bans", {}).get(str(member.id))
        if ban_info:
            logger.debug(f"Restauration des rôles pour l'utilisateur {member.display_name}.")
            await self.restore_roles(member)
        else:
            logger.debug(f"Aucune restauration de rôles nécessaire pour l'utilisateur {member.display_name}.")

    # Création du Groupe de Commandes 'mod'
    mod_group = app_commands.Group(
        name="mod",
        description="Commandes de modération"
    )

    # Commande Unique 'execute' avec cinq Options
    @mod_group.command(name="execute", description="Exécuter une action de modération")
    @app_commands.describe(
        action="Action de modération à effectuer",
        user="Utilisateur concerné (nécessaire pour certaines actions)",
        reason="Raison de l'action",
        duration_minutes="Durée en minutes (nécessaire pour le ban temporaire)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Bannir définitivement", value="ban_perma"),
        app_commands.Choice(name="Bannir temporairement", value="ban_temp"),
        app_commands.Choice(name="Débannir un utilisateur", value="unban"),
        app_commands.Choice(name="Avertir un utilisateur", value="avertissement"),
        app_commands.Choice(name="Vérifier les avertissements", value="check_warnings"),
        app_commands.Choice(name="Vérifier le statut du ban", value="check_ban_status")
    ])
    @commands.has_permissions(administrator=True)  # Assurez-vous que vous avez une vérification de permissions adéquate
    async def execute(
        self, 
        interaction: discord.Interaction, 
        action: app_commands.Choice[str], 
        user: Optional[discord.Member] = None, 
        reason: Optional[str] = None, 
        duration_minutes: Optional[int] = None
    ):
        """Exécute une action de modération basée sur les choix de l'utilisateur."""
        logger.debug(f"Commande 'mod execute' appelée avec l'action: {action.value} par {interaction.user.display_name}.")
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            logger.warning("Commande utilisée en dehors d'un salon texte.")
            return await interaction.response.send_message("Cette commande doit être utilisée dans un salon texte.", ephemeral=True)

        if action.value == "ban_perma":
            if not user:
                logger.warning("Utilisateur non spécifié pour bannissement définitif.")
                return await interaction.response.send_message("Veuillez spécifier un utilisateur à bannir.", ephemeral=True)
            if not reason:
                logger.warning("Raison non spécifiée pour bannissement définitif.")
                return await interaction.response.send_message("Veuillez fournir une raison pour le bannissement.", ephemeral=True)
            # Confirmation
            view = ModerationConfirmationView(interaction, None)
            await interaction.response.send_message(f"Confirmez-vous le bannissement définitif de {user.mention} ?", view=view, ephemeral=True)
            await view.wait()
            if view.value:
                await self.ban_member(user, "perma", reason, interaction.user)
                await interaction.followup.send(f"{user.display_name} a été banni définitivement. Raison : {reason}", ephemeral=True)
                logger.info(f"{interaction.user} a banni {user.display_name} définitivement. Raison : {reason}")
            else:
                await interaction.followup.send("Action annulée.", ephemeral=True)
                logger.info(f"{interaction.user} a annulé le bannissement définitif de {user.display_name}.")

        elif action.value == "ban_temp":
            if not user:
                logger.warning("Utilisateur non spécifié pour bannissement temporaire.")
                return await interaction.response.send_message("Veuillez spécifier un utilisateur à bannir.", ephemeral=True)
            if not reason:
                logger.warning("Raison non spécifiée pour bannissement temporaire.")
                return await interaction.response.send_message("Veuillez fournir une raison pour le bannissement.", ephemeral=True)
            if not duration_minutes:
                logger.warning("Durée non spécifiée pour bannissement temporaire.")
                return await interaction.response.send_message("Veuillez spécifier la durée du bannissement en minutes.", ephemeral=True)
            if duration_minutes < 1:
                logger.warning("Durée invalide spécifiée pour bannissement temporaire.")
                return await interaction.response.send_message("La durée du bannissement doit être d'au moins 1 minute.", ephemeral=True)
            # Confirmation
            view = ModerationConfirmationView(interaction, None)
            await interaction.response.send_message(f"Confirmez-vous le bannissement temporaire de {user.mention} pour {duration_minutes} minutes ?", view=view, ephemeral=True)
            await view.wait()
            if view.value:
                await self.ban_member(user, "temp", reason, interaction.user, duration_minutes=duration_minutes)
                end_time = (datetime.utcnow() + timedelta(minutes=duration_minutes)).strftime("%Y-%m-%d %H:%M:%S UTC")
                await interaction.followup.send(f"{user.display_name} a été banni temporairement jusqu'au {end_time}. Raison : {reason}", ephemeral=True)
                logger.info(f"{interaction.user} a banni {user.display_name} temporairement. Raison : {reason}, Durée : {duration_minutes}min")
            else:
                await interaction.followup.send("Action annulée.", ephemeral=True)
                logger.info(f"{interaction.user} a annulé le bannissement temporaire de {user.display_name}.")

        elif action.value == "unban":
            if not user:
                logger.warning("Utilisateur non spécifié pour débannissement.")
                return await interaction.response.send_message("Veuillez spécifier un utilisateur à débannir.", ephemeral=True)
            # Confirmation
            view = ModerationConfirmationView(interaction, None)
            await interaction.response.send_message(f"Confirmez-vous le débannissement de {user.mention} ?", view=view, ephemeral=True)
            await view.wait()
            if view.value:
                await self.unban_member(user.id, reason=reason)
                await interaction.followup.send(f"{user.mention} a été débanni. Raison : {reason or 'Aucune raison'}", ephemeral=True)
                logger.info(f"{interaction.user} a débanni {user.display_name}. Raison : {reason}")
            else:
                await interaction.followup.send("Action annulée.", ephemeral=True)
                logger.info(f"{interaction.user} a annulé le débannissement de {user.display_name}.")

        elif action.value == "avertissement":
            if not user:
                logger.warning("Utilisateur non spécifié pour avertissement.")
                return await interaction.response.send_message("Veuillez spécifier un utilisateur à avertir.", ephemeral=True)
            if not reason:
                logger.warning("Raison non spécifiée pour avertissement.")
                return await interaction.response.send_message("Veuillez fournir une raison pour l'avertissement.", ephemeral=True)
            # Confirmation
            view = ModerationConfirmationView(interaction, None)
            await interaction.response.send_message(f"Confirmez-vous l'avertissement pour {user.mention} ?", view=view, ephemeral=True)
            await view.wait()
            if not view.value:
                await interaction.followup.send("Action annulée.", ephemeral=True)
                logger.info(f"{interaction.user} a annulé l'avertissement de {user.display_name}.")
                return

            mod_data = await self.get_moderation_data()
            warnings = mod_data.setdefault("warnings", {})
            user_warnings = warnings.get(str(user.id), 0) + 1
            warnings[str(user.id)] = user_warnings
            await self.save_moderation_data(mod_data)
            logger.info(f"{user.display_name} a reçu un avertissement. Total avertissements: {user_warnings}")

            # Envoyer un DM à l'utilisateur avec les sanctions potentielles
            try:
                await user.send(
                    f"Vous avez reçu un avertissement sur **{interaction.guild.name}**.\n"
                    f"**Raison :** {reason}\n"
                    f"**Total avertissements :** {user_warnings}\n"
                    f"**Sanctions potentielles :**\n"
                    f"- À 3 avertissements : Bannissement temporaire pendant une semaine.\n"
                    f"- À 5 avertissements : Bannissement définitif."
                )
                logger.info(f"DM envoyé à {user.display_name} pour l'avertissement.")
            except discord.Forbidden:
                logger.warning(f"Impossible d'envoyer un DM à {user.display_name}.")

            response_message = f"{user.display_name} a maintenant {user_warnings} avertissement{'s' if user_warnings > 1 else ''}. Raison : {reason}"

            if user_warnings == 3:
                await self.ban_member(user, "temp", f"Avertissements : {user_warnings}", interaction.user, duration_minutes=10080)  # 1 semaine
                response_message = f"{user.display_name} a atteint 3 avertissements et est banni temporairement pendant une semaine."
                logger.info(f"{user.display_name} a été banni temporairement après 3 avertissements.")
            elif user_warnings == 5:
                await self.ban_member(user, "perma", f"Avertissements : {user_warnings}", interaction.user)
                response_message = f"{user.display_name} a atteint 5 avertissements et est banni définitivement."
                logger.info(f"{user.display_name} a été banni définitivement après 5 avertissements.")

            await interaction.followup.send(response_message, ephemeral=True)
            logger.info(f"{interaction.user} a averti {user.display_name}. Total avertissements : {user_warnings}. Raison : {reason}")

        elif action.value == "check_warnings":
            if not user:
                logger.warning("Utilisateur non spécifié pour vérifier les avertissements.")
                return await interaction.response.send_message("Veuillez spécifier un utilisateur à vérifier.", ephemeral=True)
            # Confirmation
            view = ModerationConfirmationView(interaction, None)
            await interaction.response.send_message(f"Confirmez-vous la vérification des avertissements de {user.mention} ?", view=view, ephemeral=True)
            await view.wait()
            if view.value:
                mod_data = await self.get_moderation_data()
                warnings = mod_data.get("warnings", {}).get(str(user.id), 0)
                if warnings == 0:
                    message = f"{user.display_name} n'a aucun avertissement."
                else:
                    message = f"{user.display_name} a {warnings} avertissement{'s' if warnings > 1 else ''}."
                await interaction.followup.send(message, ephemeral=True)
                logger.info(f"{interaction.user} a vérifié les avertissements de {user.display_name}: {warnings}")
            else:
                await interaction.followup.send("Action annulée.", ephemeral=True)
                logger.info(f"{interaction.user} a annulé la vérification des avertissements de {user.display_name}.")

        elif action.value == "check_ban_status":
            if not user:
                logger.warning("Utilisateur non spécifié pour vérifier le statut du ban.")
                return await interaction.followup.send("Veuillez spécifier un utilisateur à vérifier.", ephemeral=True)
            # Confirmation
            view = ModerationConfirmationView(interaction, None)  # Aucun callback spécifique ici
            await interaction.followup.send(f"Confirmez-vous la vérification du statut du ban de {user.mention} ?", view=view, ephemeral=True)
            await view.wait()
            if view.value:
                mod_data = await self.get_moderation_data()
                ban_info = mod_data.get("bans", {}).get(str(user.id), None)
                if not ban_info:
                    message = f"{user.display_name} n'est actuellement pas banni."
                    await interaction.followup.send(message, ephemeral=True)
                    logger.info(f"{interaction.user} a vérifié le statut du ban de {user.display_name}: Non banni.")
                else:
                    # Récupérer les informations nécessaires
                    ban_type = ban_info.get("ban_type", "Inconnu")
                    ban_reason = ban_info.get("ban_reason", "Aucune raison fournie.")
                    banned_by_id = ban_info.get("banned_by", None)
                    banned_at = ban_info.get("banned_at", None)
                    ban_end = ban_info.get("ban_end", None)

                    # Récupérer l'utilisateur qui a banni
                    if banned_by_id:
                        banned_by = self.bot.get_user(banned_by_id)
                        if not banned_by:
                            try:
                                banned_by = await self.bot.fetch_user(banned_by_id)
                            except discord.NotFound:
                                banned_by = None
                    else:
                        banned_by = None

                    # Formater les dates
                    try:
                        banned_at_dt = datetime.fromisoformat(banned_at) if banned_at else None
                        banned_at_str = banned_at_dt.strftime("%Y-%m-%d %H:%M:%S UTC") if banned_at_dt else "Inconnue"
                    except ValueError:
                        banned_at_str = "Format de date invalide"

                    if ban_type == "temp" and ban_end:
                        try:
                            ban_end_dt = datetime.fromisoformat(ban_end)
                            ban_end_str = ban_end_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                        except ValueError:
                            ban_end_str = "Format de date invalide"
                    else:
                        ban_end_str = "Permanent"

                    # Créer un embed pour afficher les informations de ban
                    embed = discord.Embed(
                        title=f"Statut du ban de {user.display_name}",
                        color=discord.Color.red(),
                        timestamp=datetime.utcnow()
                    )
                    embed.add_field(name="Utilisateur", value=f"{user} (ID: {user.id})", inline=False)
                    embed.add_field(name="Type de ban", value=ban_type.capitalize(), inline=True)
                    embed.add_field(name="Raison", value=ban_reason, inline=True)
                    embed.add_field(name="Banni par", value=f"{banned_by}" if banned_by else "Inconnu", inline=True)
                    embed.add_field(name="Date de bannissement", value=banned_at_str, inline=True)
                    embed.add_field(name="Date de débannissement", value=ban_end_str, inline=True)
                    embed.set_footer(text="Système de Modération")

                    await interaction.followup.send(embed=embed, ephemeral=True)
                    logger.info(f"{interaction.user} a vérifié le statut du ban de {user.display_name}: {ban_type.capitalize()}.")
            else:
                await interaction.followup.send("Action annulée.", ephemeral=True)
                logger.info(f"{interaction.user} a annulé la vérification du statut du ban de {user.display_name}.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
    logger.info("Moderation Cog chargé avec succès.")
