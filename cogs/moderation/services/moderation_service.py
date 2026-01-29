# cogs\moderation\services\moderation_service.py
from utils.database import database
import logging
from datetime import datetime
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

class ModerationService:
    @staticmethod
    async def get_ban_info(discord_user_id: int) -> Optional[dict]:
        # Convertir l'ID Discord en ID interne
        internal_id = await ModerationService.get_or_create_user_id(discord_user_id)
        if not internal_id:
            logger.error(f"Impossible de trouver ou créer l'ID interne pour l'utilisateur Discord {discord_user_id}.")
            return None

        query = """
        SELECT user_id, ban_type, ban_reason, banned_by,
               banned_at, ban_end, warnings_count, roles_backup, server_id
        FROM bans
        WHERE user_id = $1;
        """
        try:
            return await database.fetchrow(query, internal_id)
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des informations de ban pour Discord ID {discord_user_id}: {e}")
            return None

    @staticmethod
    async def add_ban(user_id: int, ban_type: str, reason: str, banned_by: int, ban_end: Optional[datetime], roles_backup: Optional[List[int]] = None, server_id: Optional[int] = None) -> bool:
        """
        Ajoute ou met à jour un bannissement dans la table 'bans'.

        Retourne True si l'opération réussit, False sinon.
        """
        try:
            user_table_id = await ModerationService.get_or_create_user_id(user_id)
            banned_by_table_id = await ModerationService.get_or_create_user_id(banned_by)
        except Exception as e:
            logger.error(f"Erreur lors de l'accès à la table 'user_id' pour l'utilisateur {user_id} ou {banned_by}: {e}")
            return False

        query = """
        INSERT INTO bans (user_id, ban_type, ban_reason, banned_by, banned_at, ban_end, warnings_count, roles_backup, server_id)
        VALUES ($1, $2, $3, $4, NOW(), $5, 0, $6, $7)
        ON CONFLICT (user_id) DO UPDATE
        SET ban_type = EXCLUDED.ban_type,
            ban_reason = EXCLUDED.ban_reason,
            banned_by = EXCLUDED.banned_by,
            banned_at = EXCLUDED.banned_at,
            ban_end = EXCLUDED.ban_end,
            roles_backup = EXCLUDED.roles_backup,
            server_id = EXCLUDED.server_id;
        """
        try:
            logger.debug(f"Exécution de la requête SQL : {query} avec paramètres "
                         f"user_id={user_table_id}, ban_type={ban_type}, reason='{reason}', "
                         f"banned_by={banned_by_table_id}, ban_end={ban_end}")
            await database.execute(query, user_table_id, ban_type, reason, banned_by_table_id, ban_end, roles_backup, server_id)
            logger.info(f"Bannissement ajouté pour l'utilisateur {user_table_id}.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout du bannissement pour {user_id}: {e}")
            return False

    @staticmethod
    async def remove_ban(user_id: int) -> bool:
        """
        Supprime un bannissement de la table 'bans'.

        Retourne True si l'opération réussit, False sinon.
        """
        query = "DELETE FROM bans WHERE user_id = $1;"
        try:
            await database.execute(query, user_id)
            logger.info(f"Bannissement supprimé pour l'utilisateur {user_id}.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du bannissement pour {user_id}: {e}")
            return False

    @staticmethod
    async def get_warnings(user_id: int) -> int:
        """
        Récupère le nombre d'avertissements d'un utilisateur depuis la table bans.

        Retourne le nombre d'avertissements ou 0 en cas d'erreur.
        """
        internal_id = await ModerationService.get_or_create_user_id(user_id)
        if not internal_id:
            return 0
        query = "SELECT warnings_count FROM bans WHERE user_id = $1;"
        try:
            result = await database.fetchval(query, internal_id)
            return result if result else 0
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des avertissements pour {user_id}: {e}")
            return 0

    @staticmethod
    async def add_warning(user_id: int) -> bool:
        """
        Ajoute un avertissement à un utilisateur dans la table bans.

        Retourne True si l'opération réussit, False sinon.
        """
        internal_id = await ModerationService.get_or_create_user_id(user_id)
        if not internal_id:
            return False
        query = """
        UPDATE bans
        SET warnings_count = warnings_count + 1
        WHERE user_id = $1;
        """
        try:
            await database.execute(query, internal_id)
            logger.info(f"Avertissement ajouté pour l'utilisateur {user_id}.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout d'un avertissement pour {user_id}: {e}")
            return False

    @staticmethod
    async def get_roles_backup(discord_user_id: int) -> List[int]:
        """
        Récupère les rôles sauvegardés d'un utilisateur depuis la table 'bans'.

        Retourne une liste d'IDs de rôles ou une liste vide en cas d'erreur.
        """
        internal_id = await ModerationService.get_or_create_user_id(discord_user_id)
        if not internal_id:
            return []
        query = "SELECT roles_backup FROM bans WHERE user_id = $1;"
        try:
            result = await database.fetchval(query, internal_id)
            return result if result else []
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des rôles sauvegardés pour l'utilisateur {discord_user_id}: {e}")
            return []

    @staticmethod
    async def update_roles_backup(discord_user_id: int, roles: List[int]) -> bool:
        """
        Met à jour le backup des rôles d'un utilisateur dans la table 'bans'.

        Retourne True si l'opération réussit, False sinon.
        """
        internal_id = await ModerationService.get_or_create_user_id(discord_user_id)
        if not internal_id:
            return False
        query = "UPDATE bans SET roles_backup = $2 WHERE user_id = $1;"
        try:
            await database.execute(query, internal_id, roles)
            logger.info(f"Backup de rôles mis à jour pour l'utilisateur {discord_user_id}.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour des rôles pour l'utilisateur {discord_user_id}: {e}")
            return False

    @staticmethod
    async def clear_roles_backup(discord_user_id: int) -> bool:
        """
        Efface le backup des rôles d'un utilisateur après restauration.

        Retourne True si l'opération réussit, False sinon.
        """
        internal_id = await ModerationService.get_or_create_user_id(discord_user_id)
        if not internal_id:
            return False
        query = "UPDATE bans SET roles_backup = NULL WHERE user_id = $1;"
        try:
            await database.execute(query, internal_id)
            logger.info(f"Backup de rôles effacé pour l'utilisateur {discord_user_id}.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'effacement des rôles sauvegardés pour l'utilisateur {discord_user_id}: {e}")
            return False

    @staticmethod
    async def get_expired_bans(current_time: datetime) -> List[dict]:
        """
        Récupère les bannissements temporaires expirés.

        Retourne une liste de dictionnaires contenant 'user_id' et 'ban_end'.
        """
        query = """
        SELECT user_id, ban_end
        FROM bans
        WHERE ban_end IS NOT NULL AND ban_end <= $1;
        """
        try:
            return await database.fetch(query, current_time)
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des bannissements expirés : {e}")
            return []

    @staticmethod
    async def get_ban_role_id(guild_id: int) -> Optional[int]:
        """
        Récupère l'ID du rôle 'ban' pour un serveur spécifique à partir de la base de données.

        Retourne l'ID du rôle ou None si non trouvé.
        """
        # Premièrement, obtenir l'ID interne du serveur à partir du guild_id
        server_id_query = "SELECT id FROM serveur_id WHERE guild_id = $1;"
        try:
            internal_server_id = await database.fetchval(server_id_query, guild_id)
            if not internal_server_id:
                logger.warning(f"Aucun serveur trouvé avec guild_id {guild_id}.")
                return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de l'ID interne pour guild_id {guild_id}: {e}")
            return None

        # Maintenant, récupérer le rôle 'ban' en utilisant l'ID interne du serveur
        query = """
        SELECT role_id
        FROM roles_configurations
        WHERE server_id = $1 AND role_name = 'ban';
        """
        try:
            role_id = await database.fetchval(query, internal_server_id)
            if role_id:
                return role_id
            logger.warning(f"Aucun rôle 'ban' trouvé pour le serveur avec guild_id {guild_id}.")
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du rôle 'ban' pour le serveur {guild_id}: {e}")
            return None

    @staticmethod
    async def get_or_create_user_id(discord_user_id: int) -> Optional[int]:
        """
        Récupère ou insère un utilisateur dans la table `user_id` et retourne son ID interne.
        """
        select_query = "SELECT id FROM user_id WHERE discord_id = $1;"
        insert_query = "INSERT INTO user_id (discord_id) VALUES ($1) RETURNING id;"
        try:
            # Vérifier si l'utilisateur existe déjà
            user_id = await database.fetchval(select_query, discord_user_id)
            if user_id:
                return user_id

            # Si non, insérer l'utilisateur
            user_id = await database.fetchval(insert_query, discord_user_id)
            if user_id:
                logger.info(f"Utilisateur Discord {discord_user_id} ajouté à `user_id` avec ID interne {user_id}.")
                return user_id
            else:
                logger.error(f"Échec de l'insertion de l'utilisateur Discord {discord_user_id}.")
                return None
        except Exception as e:
            logger.exception(f"Erreur SQL lors de la récupération ou de l'insertion de l'utilisateur {discord_user_id}: {e}")
            return None

    @staticmethod
    async def get_discord_id(internal_id: int) -> Optional[int]:
        """
        Récupère l'ID Discord d'un utilisateur à partir de son ID interne.

        Retourne l'ID Discord ou None si non trouvé.
        """
        query = "SELECT discord_id FROM user_id WHERE id = $1;"
        try:
            return await database.fetchval(query, internal_id)
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de l'ID Discord pour l'ID interne {internal_id}: {e}")
            return None

    @staticmethod
    async def get_internal_server_id(guild_id: int) -> Optional[int]:
        """
        Récupère l'ID interne d'un serveur à partir de son ID Discord (guild_id).

        Retourne l'ID interne ou None si non trouvé.
        """
        query = "SELECT id FROM serveur_id WHERE guild_id = $1;"
        try:
            internal_id = await database.fetchval(query, guild_id)
            return internal_id
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de l'ID interne pour guild_id {guild_id}: {e}")
            return None

    @staticmethod
    async def get_persistent_message(guild_id: int, message_type: str) -> Optional[Dict[str, int]]:
        """
        Récupère les informations d'un message persistant depuis la base de données en fonction du guild_id et du message_type.

        Args:
            guild_id (int): L'ID interne du serveur.
            message_type (str): Le type de message persistant à récupérer (ex: 'demande_deban', 'deban_request').

        Returns:
            Optional[Dict[str, int]]: Un dictionnaire contenant 'channel_id' et 'message_id' si trouvé, sinon None.
        """
        query = """
        SELECT channel_id, message_id
        FROM persistent_messages
        WHERE server_id = $1 AND message_type = $2;
        """
        try:
            result = await database.fetchrow(query, guild_id, message_type)
            if result:
                return {
                    "channel_id": result["channel_id"],
                    "message_id": result["message_id"]
                }
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du message persistant pour server_id {guild_id} et message_type '{message_type}': {e}")
            return None

    @staticmethod
    async def get_persistent_messages_by_type(server_id: int, message_type: str) -> List[Dict[str, int]]:
        """
        Récupère toutes les informations des messages persistants d'un certain type.

        Args:
            server_id (int): L'ID interne du serveur.
            message_type (str): Le type de messages persistants à récupérer.

        Returns:
            List[Dict[str, int]]: Une liste de dictionnaires contenant 'channel_id' et 'message_id'.
        """
        query = """
        SELECT channel_id, message_id
        FROM persistent_messages
        WHERE server_id = $1 AND message_type = $2;
        """
        try:
            results = await database.fetch(query, server_id, message_type)
            return [{"channel_id": row["channel_id"], "message_id": row["message_id"]} for row in results]
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des messages persistants pour server_id {server_id} et message_type '{message_type}': {e}")
            return []

    @staticmethod
    async def get_requester_id(message_id: int) -> Optional[int]:
        """
        Récupère l'ID interne du demandeur à partir du message_id.

        Args:
            message_id (int): L'ID du message persistant.

        Returns:
            Optional[int]: L'ID interne du demandeur ou None.
        """
        query = """
        SELECT requester_id
        FROM persistent_messages
        WHERE message_id = $1 AND message_type = 'deban_request';
        """
        try:
            return await database.fetchval(query, message_id)
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du requester_id pour message_id {message_id}: {e}")
            return None

    @staticmethod
    async def get_moderation_channel_id(server_id: int) -> Optional[int]:
        """
        Récupère l'ID du salon de modération pour un serveur spécifique à partir de la base de données.

        Args:
            server_id (int): L'ID interne du serveur.

        Returns:
            Optional[int]: L'ID du salon de modération ou None si non trouvé.
        """
        query = """
        SELECT channel_id
        FROM channel_configurations
        WHERE server_id = $1 AND action = 'modération';
        """
        try:
            channel_id = await database.fetchval(query, server_id)
            if channel_id:
                return channel_id
            logger.warning(f"Aucun salon de modération trouvé pour le serveur avec ID interne {server_id}.")
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du salon de modération pour server_id {server_id}: {e}")
            return None

    @staticmethod
    async def get_deban_channel_id(server_id: int) -> Optional[int]:
        """
        Récupère l'ID du salon de demande-deban pour un serveur spécifique à partir de la base de données.

        Args:
            server_id (int): L'ID interne du serveur.

        Returns:
            Optional[int]: L'ID du salon de demande-deban ou None si non trouvé.
        """
        query = """
        SELECT channel_id
        FROM channel_configurations
        WHERE server_id = $1 AND action = 'demande-deban';
        """
        try:
            channel_id = await database.fetchval(query, server_id)
            if channel_id:
                return channel_id
            logger.warning(f"Aucun salon de demande-deban trouvé pour le serveur avec ID interne {server_id}.")
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du salon de demande-deban pour server_id {server_id}: {e}")
            return None

    @staticmethod
    async def get_deban_category_id(server_id: int) -> Optional[int]:
        """
        Récupère l'ID de la catégorie pour les demandes de déban pour un serveur spécifique.

        Args:
            server_id (int): L'ID interne du serveur.

        Returns:
            Optional[int]: L'ID de la catégorie ou None si non trouvé.
        """
        query = """
        SELECT channel_id
        FROM channel_configurations
        WHERE server_id = $1 AND action = 'deban_category';
        """
        try:
            category_id = await database.fetchval(query, server_id)
            if category_id:
                return category_id
            logger.warning(f"Aucune catégorie de déban trouvée pour le serveur avec ID interne {server_id}.")
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la catégorie de déban pour server_id {server_id}: {e}")
            return None

    @staticmethod
    async def get_role_id_by_name(server_id: int, role_name: str) -> Optional[int]:
        """
        Récupère l'ID d'un rôle par son nom pour un serveur spécifique.

        Args:
            server_id (int): L'ID interne du serveur.
            role_name (str): Le nom du rôle à récupérer (ex: 'admin', 'ban').

        Returns:
            Optional[int]: L'ID du rôle ou None si non trouvé.
        """
        query = """
        SELECT role_id
        FROM roles_configurations
        WHERE server_id = $1 AND role_name = $2;
        """
        try:
            role_id = await database.fetchval(query, server_id, role_name)
            if role_id:
                return role_id
            logger.warning(f"Aucun rôle '{role_name}' trouvé pour le serveur avec ID interne {server_id}.")
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du rôle '{role_name}' pour server_id {server_id}: {e}")
            return None

    @staticmethod
    async def delete_persistent_message(message_id: int) -> bool:
        """
        Supprime un message persistant de la table `persistent_messages` en fonction de son ID.

        Args:
            message_id (int): L'ID du message à supprimer.

        Returns:
            bool: True si la suppression réussit, False sinon.
        """
        query = """
        DELETE FROM persistent_messages
        WHERE message_id = $1;
        """
        try:
            await database.execute(query, message_id)
            logger.info(f"Message persistant ID {message_id} supprimé de la base de données.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du message persistant ID {message_id}: {e}")
            return False
