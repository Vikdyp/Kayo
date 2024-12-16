# cogs/moderation/moderation.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable
import asyncio

from cogs.utilities.data_manager import DataManager
from cogs.utilities.confirmation_view import ConfirmationView  # Utilisation de la vue générique
from cogs.utilities.request_manager import enqueue_request  # Assurez-vous que ce module existe

logger = logging.getLogger("discord.moderation")

# Définition des constantes pour les durées des bannissements
TEMP_BAN_WARNING_DURATION_MINUTES = 10080  # 7 jours en minutes

class Moderation(commands.Cog):
    """Cog pour gérer les bannissements, débannissements, avertissements et la sauvegarde/restauration des rôles des membres."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.lock = asyncio.Lock()  # Verrou asynchrone pour la gestion des données
        self.check_bans_expired.start()
        logger.info("Initialisation du Cog de Modération.")

        # Validation des configurations au démarrage
        self.bot.loop.create_task(self.validate_configurations())

    def cog_unload(self):
        self.check_bans_expired.cancel()
        logger.info("Cog de Modération déchargé.")

    async def validate_configurations(self):
        """Valide les configurations essentielles au démarrage."""
        await self.bot.wait_until_ready()
        config = await self.data.get_config()
        ban_role_id = config.get("roles", {}).get("ban")

        if not ban_role_id:
            logger.error("L'ID du rôle 'ban' n'est pas défini dans config.json.")
            return

        for guild in self.bot.guilds:
            if isinstance(ban_role_id, str):
                if not ban_role_id.isdigit():
                    logger.error(f"L'ID du rôle 'ban' dans config.json n'est pas un entier valide: {ban_role_id}")
                    continue
                try:
                    ban_role = guild.get_role(int(ban_role_id))
                except ValueError:
                    logger.error(f"L'ID du rôle 'ban' dans config.json n'est pas convertible en entier: {ban_role_id}")
                    ban_role = None
            elif isinstance(ban_role_id, int):
                ban_role = guild.get_role(ban_role_id)
            else:
                logger.error(f"Type de l'ID du rôle 'ban' invalide: {ban_role_id} (type: {type(ban_role_id)})")
                ban_role = None

            if not ban_role:
                logger.error(f"Rôle 'ban' avec l'ID {ban_role_id} introuvable dans le serveur {guild.name} (ID: {guild.id}).")
            else:
                logger.info(f"Rôle 'ban' vérifié dans le serveur {guild.name} (ID: {guild.id}).")

    async def get_moderation_data(self) -> Dict:
        """Récupère les données de modération."""
        async with self.lock:
            return await self.data.get_moderation_data()

    async def save_moderation_data(self, mod_data: Dict) -> None:
        """Sauvegarde les données de modération."""
        async with self.lock:
            await self.data.save_moderation_data(mod_data)

    async def backup_roles(self, member: discord.Member) -> None:
        """Sauvegarde les rôles actuels d'un membre (excluant le rôle par défaut et le rôle 'ban')."""
        roles_to_backup = [
            role.id for role in member.roles 
            if role != member.guild.default_role and role.name.lower() != "ban"
        ]

        if roles_to_backup:
            async with self.lock:
                role_backup = await self.data.get_role_backup()
                role_backup[str(member.id)] = roles_to_backup
                await self.data.save_role_backup(role_backup)
            logger.info(f"Rôles de {member.display_name} sauvegardés: {roles_to_backup}")
        else:
            logger.warning(f"Aucun rôle à sauvegarder pour {member.display_name}.")

    async def restore_roles(self, member: discord.Member) -> None:
        """Restaure les rôles sauvegardés d'un membre."""
        async with self.lock:
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
        async with self.lock:
            role_backup.pop(str(member.id), None)
            await self.data.save_role_backup(role_backup)
        logger.debug(f"Données de rôles supprimées pour {member.display_name} après restauration.")

    async def ban_member(
        self, 
        guild: discord.Guild,
        member: discord.Member, 
        ban_type: str, 
        reason: str, 
        banned_by: discord.User, 
        duration_minutes: Optional[int] = None
    ) -> None:
        """Banni un membre avec sauvegarde des rôles et ajout du rôle 'ban'."""
        async with self.lock:
            mod_data = await self.get_moderation_data()

        logger.debug(f"Début du bannissement de {member.display_name} (ID: {member.id}) dans {guild.name}.")

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
            if isinstance(ban_role_id, str) and ban_role_id.isdigit():
                ban_role_id = int(ban_role_id)
            elif isinstance(ban_role_id, int):
                pass
            else:
                logger.error(f"ID du rôle 'ban' invalide dans config.json: {ban_role_id}")
                return

            ban_role = guild.get_role(ban_role_id)
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
                logger.error(f"Rôle 'ban' avec l'ID {ban_role_id} introuvable dans le serveur {guild.name}.")
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
            "warnings_count": mod_data.get("warnings", {}).get(str(member.id), 0),
            "unban_request_msg_id": None,
            "unban_request_channel_id": None
        }

        async with self.lock:
            mod_data.setdefault("bans", {})[str(member.id)] = user_data
            await self.save_moderation_data(mod_data)

        # Envoyer un DM à l'utilisateur
        try:
            await member.send(
                f"Vous avez été banni du serveur **{guild.name}**.\n"
                f"**Raison :** {reason}\n"
                f"**Banni par :** {banned_by.display_name}\n"
                f"**Note :** Après 3 avertissements, vous serez banni temporairement pendant une semaine. Après 5 avertissements, vous serez banni définitivement.\n"
                f"**Vous pouvez faire une demande de débannissement dans le salon demande-de-deban**"
            )
            logger.info(f"DM envoyé à {member.display_name} pour le bannissement.")
        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer un DM à {member.display_name}.")
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de l'envoi du DM à {member.display_name}: {e}")

    async def unban_member(self, guild: discord.Guild, user_id: int, reason: Optional[str] = None) -> None:
        """Débanni un membre et restaure ses rôles."""
        logger.debug(f"Tentative de débannissement de l'utilisateur ID: {user_id} dans {guild.name}. Raison: {reason}")

        async with self.lock:
            mod_data = await self.get_moderation_data()
            ban_info = mod_data.get("bans", {}).pop(str(user_id), None)

        if not ban_info:
            logger.warning(f"Tentative de débannissement d'un utilisateur non banni (ID: {user_id}) dans {guild.name}.")
            async with self.lock:
                await self.save_moderation_data(mod_data)
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
                    if isinstance(ban_role_id, str) and ban_role_id.isdigit():
                        ban_role_id = int(ban_role_id)
                    elif isinstance(ban_role_id, int):
                        pass
                    else:
                        logger.error(f"ID du rôle 'ban' invalide dans config.json: {ban_role_id}")
                        return

                    ban_role = guild.get_role(ban_role_id)
                    if ban_role:
                        if ban_role in member.roles:
                            await member.remove_roles(ban_role, reason=reason or "Débannissement automatique")
                            logger.info(f"Rôle 'ban' retiré de {member.display_name}.")
                        else:
                            logger.warning(f"L'utilisateur {member.display_name} n'a pas le rôle 'ban'.")
                    else:
                        logger.error(f"Rôle 'ban' avec l'ID {ban_role_id} introuvable dans le serveur {guild.name}.")
                else:
                    logger.error("ID du rôle 'ban' non trouvé dans le fichier config.json.")
            else:
                logger.warning(f"Membre avec l'ID {user_id} n'est pas présent dans le serveur {guild.name}.")
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

        async with self.lock:
            await self.save_moderation_data(mod_data)
        logger.debug(f"Données de modération mises à jour après débannissement de l'utilisateur ID: {user_id}.")

        # Informer l'utilisateur via DM si le membre est dans le serveur
        if member:
            try:
                await user.send(
                    f"Vous avez été débanni du serveur **{guild.name}**.\n**Raison :** {reason or 'Aucune raison'}"
                )
                logger.info(f"DM envoyé à l'utilisateur {user.display_name} pour le débannissement.")
            except discord.Forbidden:
                logger.warning(f"Impossible d'envoyer un DM à l'utilisateur {user.display_name}.")
            except discord.HTTPException as e:
                logger.error(f"Erreur HTTP lors de l'envoi du DM à l'utilisateur {user.display_name}: {e}")
        else:
            logger.debug(f"L'utilisateur n'est pas dans le serveur. Aucun DM envoyé.")

    @tasks.loop(minutes=1)
    async def check_bans_expired(self):
        """Vérifie régulièrement les bannissements temporaires expirés et débannit automatiquement les membres."""
        logger.debug("Début de la vérification des bannissements expirés.")
        now = datetime.utcnow()

        async with self.lock:
            mod_data = await self.get_moderation_data()
            to_unban = []
            bans = mod_data.get("bans", {}).copy()

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
                # Parcourir toutes les guildes pour débannir l'utilisateur
                for guild in self.bot.guilds:
                    await self.unban_member(guild, user_id, reason="Bannissement temporaire expiré")
            # Mettre à jour les données après les débannissements
            async with self.lock:
                for uid in to_unban:
                    bans.pop(uid, None)
                mod_data["bans"] = bans
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
        async with self.lock:
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

    # Commande de Bannissement
    @mod_group.command(name="ban", description="Bannir un utilisateur de manière permanente ou temporaire")
    @app_commands.describe(
        user="Utilisateur à bannir",
        reason="Raison du bannissement",
        duration_minutes="Durée du bannissement temporaire en minutes (optionnel)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @enqueue_request()
    async def ban(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member, 
        reason: str, 
        duration_minutes: Optional[int] = None
    ):
        """Bannit un utilisateur de manière permanente ou temporaire avec confirmation."""
        logger.debug(f"Commande '/mod ban' appelée par {interaction.user.display_name} pour {user.display_name}.")
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            logger.warning("Commande '/mod ban' utilisée en dehors d'une guilde.")
            return

        ban_type = "temp" if duration_minutes else "perma"

        if ban_type == "temp" and (duration_minutes is None or duration_minutes < 1):
            await interaction.followup.send("La durée du bannissement doit être d'au moins 1 minute.", ephemeral=True)
            logger.warning("Durée invalide spécifiée pour bannissement temporaire.")
            return

        # Callback pour la confirmation
        async def confirmation_callback(value: Optional[bool]):
            if value:
                await self.ban_member(guild, user, ban_type, reason, interaction.user, duration_minutes=duration_minutes)
                if ban_type == "temp":
                    end_time = (datetime.utcnow() + timedelta(minutes=duration_minutes)).strftime("%Y-%m-%d %H:%M:%S UTC")
                    message = f"{user.display_name} a été banni temporairement jusqu'au {end_time}. Raison : {reason}"
                else:
                    message = f"{user.display_name} a été banni définitivement. Raison : {reason}"
                await interaction.followup.send(message, ephemeral=True)
                logger.info(f"{interaction.user} a banni {user.display_name} ({ban_type}). Raison : {reason}")
            else:
                await interaction.followup.send("Action annulée.", ephemeral=True)
                logger.info(f"{interaction.user} a annulé le bannissement de {user.display_name}.")

        # Création de la vue de confirmation
        view = ConfirmationView(
            interaction=interaction, 
            callback=confirmation_callback,
            confirm_label="Accepter",
            confirm_style=discord.ButtonStyle.green,
            cancel_label="Refuser",
            cancel_style=discord.ButtonStyle.red
        )

        confirmation_message = f"Confirmez-vous le bannissement {'temporaire' if ban_type == 'temp' else 'définitif'} de {user.mention} ?"
        if ban_type == "temp":
            confirmation_message += f" Durée: {duration_minutes} minutes."

        await interaction.followup.send(
            confirmation_message, 
            view=view, 
            ephemeral=True
        )
        await view.wait()

    # Commande de Débannissement
    @mod_group.command(name="unban", description="Débannir un utilisateur")
    @app_commands.describe(
        user_id="ID de l'utilisateur à débannir",
        reason="Raison du débannissement (optionnel)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @enqueue_request()
    async def unban(
        self, 
        interaction: discord.Interaction, 
        user_id: int, 
        reason: Optional[str] = None
    ):
        """Débanni un utilisateur avec confirmation."""
        logger.debug(f"Commande '/mod unban' appelée par {interaction.user.display_name} pour l'utilisateur ID: {user_id}.")
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            logger.warning("Commande '/mod unban' utilisée en dehors d'une guilde.")
            return

        # Callback pour la confirmation
        async def confirmation_callback(value: Optional[bool]):
            if value:
                await self.unban_member(guild, user_id, reason=reason)
                try:
                    user = await self.bot.fetch_user(user_id)
                    await interaction.followup.send(
                        f"{user.mention} a été débanni. Raison : {reason or 'Aucune raison'}", 
                        ephemeral=True
                    )
                except discord.NotFound:
                    await interaction.followup.send(
                        f"L'utilisateur avec l'ID {user_id} a été débanni. Raison : {reason or 'Aucune raison'}", 
                        ephemeral=True
                    )
                logger.info(f"{interaction.user} a débanni l'utilisateur ID: {user_id}. Raison : {reason}")
            else:
                await interaction.followup.send("Action annulée.", ephemeral=True)
                logger.info(f"{interaction.user} a annulé le débannissement de l'utilisateur ID: {user_id}.")

        # Création de la vue de confirmation
        view = ConfirmationView(
            interaction=interaction, 
            callback=confirmation_callback,
            confirm_label="Accepter",
            confirm_style=discord.ButtonStyle.green,
            cancel_label="Refuser",
            cancel_style=discord.ButtonStyle.red
        )

        await interaction.followup.send(
            f"Confirmez-vous le débannissement de l'utilisateur avec l'ID {user_id} ?", 
            view=view, 
            ephemeral=True
        )
        await view.wait()

    # Commande d'Avertissement
    @mod_group.command(name="warn", description="Avertir un utilisateur")
    @app_commands.describe(
        user="Utilisateur à avertir",
        reason="Raison de l'avertissement"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @enqueue_request()
    async def warn(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member, 
        reason: str
    ):
        """Avertit un utilisateur avec confirmation et gestion des sanctions automatiques."""
        logger.debug(f"Commande '/mod warn' appelée par {interaction.user.display_name} pour {user.display_name}.")
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            logger.warning("Commande '/mod warn' utilisée en dehors d'une guilde.")
            return

        # Callback pour la confirmation
        async def confirmation_callback(value: Optional[bool]):
            if value:
                async with self.lock:
                    mod_data = await self.get_moderation_data()
                    warnings = mod_data.setdefault("warnings", {})
                    user_warnings = warnings.get(str(user.id), 0) + 1
                    warnings[str(user.id)] = user_warnings
                    await self.save_moderation_data(mod_data)
                logger.info(f"{user.display_name} a reçu un avertissement. Total avertissements: {user_warnings}")

                # Envoyer un DM à l'utilisateur avec les sanctions potentielles
                try:
                    await user.send(
                        f"Vous avez reçu un avertissement sur **{guild.name}**.\n"
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
                    await self.ban_member(guild, user, "temp", f"Avertissements : {user_warnings}", interaction.user, duration_minutes=10080)  # 1 semaine
                    response_message = f"{user.display_name} a atteint 3 avertissements et est banni temporairement pendant une semaine."
                    logger.info(f"{user.display_name} a été banni temporairement après 3 avertissements.")
                elif user_warnings == 5:
                    await self.ban_member(guild, user, "perma", f"Avertissements : {user_warnings}", interaction.user)
                    response_message = f"{user.display_name} a atteint 5 avertissements et est banni définitivement."
                    logger.info(f"{user.display_name} a été banni définitivement après 5 avertissements.")

                await interaction.followup.send(response_message, ephemeral=True)
                logger.info(f"{interaction.user} a averti {user.display_name}. Total avertissements : {user_warnings}. Raison : {reason}")
            else:
                await interaction.followup.send("Action annulée.", ephemeral=True)
                logger.info(f"{interaction.user} a annulé l'avertissement de {user.display_name}.")

        # Création de la vue de confirmation
        view = ConfirmationView(
            interaction=interaction, 
            callback=confirmation_callback,
            confirm_label="Accepter",
            confirm_style=discord.ButtonStyle.green,
            cancel_label="Refuser",
            cancel_style=discord.ButtonStyle.red
        )

        await interaction.followup.send(
            f"Confirmez-vous l'avertissement pour {user.mention} ? Raison : {reason}",
            view=view, 
            ephemeral=True
        )
        await view.wait()

    # Commande de Vérification des Avertissements
    @mod_group.command(name="check_warnings", description="Vérifier les avertissements d'un utilisateur")
    @app_commands.describe(
        user="Utilisateur à vérifier"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @enqueue_request()
    async def check_warnings(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member
    ):
        """Vérifie le nombre d'avertissements d'un utilisateur."""
        logger.debug(f"Commande '/mod check_warnings' appelée par {interaction.user.display_name} pour {user.display_name}.")
        await interaction.response.defer(ephemeral=True)

        async with self.lock:
            mod_data = await self.get_moderation_data()
            warnings = mod_data.get("warnings", {}).get(str(user.id), 0)

        await interaction.followup.send(
            f"{user.display_name} a actuellement {warnings} avertissement{'s' if warnings != 1 else ''}.",
            ephemeral=True
        )
        logger.info(f"{interaction.user} a vérifié les avertissements de {user.display_name}: {warnings}.")

    # Commande de Vérification du Statut du Bannissement
    @mod_group.command(name="check_ban_status", description="Vérifier le statut du bannissement d'un utilisateur")
    @app_commands.describe(
        user="Utilisateur à vérifier"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @enqueue_request()
    async def check_ban_status(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member
    ):
        """Vérifie le statut du bannissement d'un utilisateur."""
        logger.debug(f"Commande '/mod check_ban_status' appelée par {interaction.user.display_name} pour {user.display_name}.")
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            logger.warning("Commande '/mod check_ban_status' utilisée en dehors d'une guilde.")
            return

        async with self.lock:
            mod_data = await self.get_moderation_data()
            ban_info = mod_data.get("bans", {}).get(str(user.id), None)

        if not ban_info:
            message = f"{user.display_name} n'est actuellement pas banni."
            await interaction.followup.send(message, ephemeral=True)
            logger.info(f"{interaction.user} a vérifié le statut du ban de {user.display_name}: Non banni.")
            return

        # Récupérer les informations nécessaires
        ban_type = ban_info.get("ban_type", "Inconnu")
        ban_reason = ban_info.get("ban_reason", "Aucune raison fournie.")
        banned_by_id = ban_info.get("banned_by", None)
        banned_at = ban_info.get("banned_at", None)
        ban_end = ban_info.get("ban_end", None)

        # Récupérer l'utilisateur qui a banni
        banned_by_user = (
            self.bot.get_user(banned_by_id) or await self.bot.fetch_user(banned_by_id)
        ) if banned_by_id else "Inconnu"

        # Formater les dates
        try:
            banned_at_str = (
                datetime.fromisoformat(ban_info["banned_at"]).strftime("%Y-%m-%d %H:%M:%S UTC")
                if banned_at else "Inconnue"
            )
        except ValueError:
            banned_at_str = "Inconnue"
            logger.error(f"Format de date invalide pour 'banned_at' de l'utilisateur {user.id}: {banned_at}")

        try:
            ban_end_str = (
                datetime.fromisoformat(ban_info["ban_end"]).strftime("%Y-%m-%d %H:%M:%S UTC")
                if ban_end else "Permanent"
            )
        except ValueError:
            ban_end_str = "Inconnu"
            logger.error(f"Format de date invalide pour 'ban_end' de l'utilisateur {user.id}: {ban_end}")

        # Créer un embed pour afficher les informations de ban
        embed = discord.Embed(
            title=f"Statut du ban de {user.display_name}",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Utilisateur", value=f"{user} (ID: {user.id})", inline=False)
        embed.add_field(name="Type de ban", value=ban_type.capitalize(), inline=True)
        embed.add_field(name="Raison", value=ban_reason, inline=True)
        embed.add_field(name="Banni par", value=f"{banned_by_user}", inline=True)
        embed.add_field(name="Date de bannissement", value=banned_at_str, inline=True)
        embed.add_field(name="Date de débannissement", value=ban_end_str, inline=True)
        embed.set_footer(text="Système de Modération")

        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"{interaction.user} a vérifié le statut du ban de {user.display_name}: {ban_type.capitalize()}.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
    logger.info("Moderation Cog chargé avec succès.")
