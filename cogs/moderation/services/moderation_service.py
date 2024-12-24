# cogs/moderation/services/moderation_service.py
from utils.database import database
import logging
from datetime import datetime
from typing import Optional, List

logger = logging.getLogger("moderation_service")

class ModerationService:
    @staticmethod
    async def get_ban_info(discord_user_id: int) -> Optional[dict]:
        # Convertir l'ID Discord en ID interne
        internal_id = await ModerationService.get_or_create_user_id(discord_user_id)
        if not internal_id:
            logger.error(f"Impossible de trouver ou créer l'ID interne pour l'utilisateur Discord {discord_user_id}.")
            return None

        query = """
        SELECT bans.user_id, ban_types.type_name, bans.ban_reason, bans.banned_by, 
               bans.banned_at, bans.ban_end, bans.warnings_count
        FROM bans
        JOIN ban_types ON bans.ban_type_id = ban_types.id
        WHERE bans.user_id = $1;
        """
        try:
            return await database.fetchrow(query, internal_id)
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des informations de ban pour Discord ID {discord_user_id}: {e}")
            return None

    @staticmethod
    async def add_ban(user_id: int, ban_type_id: int, reason: str, banned_by: int, ban_end: Optional[datetime]) -> bool:
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
        INSERT INTO bans (user_id, ban_type_id, ban_reason, banned_by, banned_at, ban_end, warnings_count)
        VALUES ($1, $2, $3, $4, NOW(), $5, 0)
        ON CONFLICT (user_id) DO UPDATE 
        SET ban_type_id = EXCLUDED.ban_type_id,
            ban_reason = EXCLUDED.ban_reason,
            banned_by = EXCLUDED.banned_by,
            banned_at = EXCLUDED.banned_at,
            ban_end = EXCLUDED.ban_end;
        """
        try:
            logger.debug(f"Exécution de la requête SQL : {query} avec paramètres "
                         f"user_id={user_table_id}, ban_type_id={ban_type_id}, reason='{reason}', "
                         f"banned_by={banned_by_table_id}, ban_end={ban_end}")
            await database.execute(query, user_table_id, ban_type_id, reason, banned_by_table_id, ban_end)
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
        Récupère le nombre d'avertissements d'un utilisateur.
        
        Retourne le nombre d'avertissements ou 0 en cas d'erreur.
        """
        query = "SELECT count FROM warnings WHERE user_id = $1;"
        try:
            result = await database.fetchval(query, user_id)
            return result if result else 0
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des avertissements pour {user_id}: {e}")
            return 0

    @staticmethod
    async def add_warning(user_id: int) -> bool:
        """
        Ajoute un avertissement à un utilisateur.
        
        Retourne True si l'opération réussit, False sinon.
        """
        query = """
        INSERT INTO warnings (user_id, count)
        VALUES ($1, 1)
        ON CONFLICT (user_id) DO UPDATE
        SET count = warnings.count + 1;
        """
        try:
            await database.execute(query, user_id)
            logger.info(f"Avertissement ajouté pour l'utilisateur {user_id}.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout d'un avertissement pour {user_id}: {e}")
            return False

    @staticmethod
    async def save_roles_backup(internal_user_id: int, roles: List[int]) -> bool:
        """
        Sauvegarde les rôles d'un utilisateur dans la table 'role_backups'.
        
        Retourne True si l'opération réussit, False sinon.
        """
        query = """
        INSERT INTO role_backups (user_id, roles)
        VALUES ($1, $2)
        ON CONFLICT (user_id) DO UPDATE
        SET roles = EXCLUDED.roles;
        """
        try:
            await database.execute(query, internal_user_id, roles)
            logger.info(f"Backup de rôles sauvegardé pour l'utilisateur interne ID {internal_user_id}.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde des rôles pour l'utilisateur interne ID {internal_user_id}: {e}")
            return False

    @staticmethod
    async def get_roles_backup(internal_user_id: int) -> List[int]:
        """
        Récupère les rôles sauvegardés d'un utilisateur depuis la table 'role_backups'.
        
        Retourne une liste d'IDs de rôles ou une liste vide en cas d'erreur.
        """
        query = "SELECT roles FROM role_backups WHERE user_id = $1;"
        try:
            result = await database.fetchval(query, internal_user_id)
            return result if result else []
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des rôles sauvegardés pour l'utilisateur interne ID {internal_user_id}: {e}")
            return []

    @staticmethod
    async def delete_roles_backup(internal_user_id: int) -> bool:
        """
        Supprime le backup des rôles d'un utilisateur de la table 'role_backups'.
        
        Retourne True si l'opération réussit, False sinon.
        """
        query = "DELETE FROM role_backups WHERE user_id = $1;"
        try:
            await database.execute(query, internal_user_id)
            logger.info(f"Backup de rôles supprimé pour l'utilisateur interne ID {internal_user_id}.")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la suppression des rôles sauvegardés pour l'utilisateur interne ID {internal_user_id}: {e}")
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
        query = """
        SELECT role_id
        FROM roles_configurations
        WHERE guild_id = $1 AND role_name = 'ban';
        """
        try:
            result = await database.fetchval(query, guild_id)
            if result:
                return result
            logger.warning(f"Aucun rôle 'ban' trouvé pour le serveur {guild_id}.")
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