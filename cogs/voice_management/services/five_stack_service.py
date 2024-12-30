from typing import Optional, List, Tuple, Dict
import logging
from utils.database import database

logger = logging.getLogger("matchmaking_service")

class MatchmakingService:
    @staticmethod
    async def get_user_info(discord_id: int) -> Optional[Dict]:
        """
        Récupère les informations Valorant d'un utilisateur à partir de la base de données.

        Args:
            discord_id (int): L'ID Discord de l'utilisateur.

        Returns:
            dict: Un dictionnaire contenant le MMR et la région Valorant si trouvé.
            None: Si l'utilisateur n'a pas d'informations disponibles ou en cas d'erreur.
        """
        query = """
        SELECT valorant_elo, valorant_region
        FROM user_id
        WHERE discord_id = $1;
        """
        try:
            row = await database.fetchrow(query, discord_id)
            if row:
                return {
                    "elo": row["valorant_elo"],
                    "region": row["valorant_region"]
                }
            logger.warning(f"Informations Valorant non trouvées pour Discord ID {discord_id}.")
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des informations utilisateur : {e}")
        return None

    @staticmethod
    async def get_server_id(guild_id: int) -> Optional[int]:
        """
        Récupère le server_id à partir du guild_id.

        Args:
            guild_id (int): L'ID de la guilde Discord.

        Returns:
            int: L'ID du serveur si trouvé.
            None: Si aucune correspondance n'est trouvée ou en cas d'erreur.
        """
        query = """
        SELECT id
        FROM serveur_id
        WHERE guild_id = $1;
        """
        try:
            server_id = await database.fetchval(query, guild_id)
            if server_id:
                return server_id
            logger.warning(f"Serveur non trouvé pour Guild ID {guild_id}.")
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du server_id pour Guild ID {guild_id} : {e}")
        return None

    @staticmethod
    async def get_role_id(server_id: int, role_name: str) -> Optional[int]:
        """
        Récupère l'ID Discord d'un rôle spécifique pour un serveur donné.

        Args:
            server_id (int): L'ID du serveur.
            role_name (str): Le nom du rôle.

        Returns:
            int: L'ID du rôle si trouvé.
            None: Si aucune correspondance n'est trouvée ou en cas d'erreur.
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
            logger.warning(f"Rôle '{role_name}' non trouvé pour le server_id {server_id}.")
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du rôle '{role_name}' pour server_id {server_id} : {e}")
        return None

    @staticmethod
    async def get_language_roles(server_id: int) -> Dict[str, int]:
        """
        Récupère les IDs des rôles de langue pour un serveur donné.

        Args:
            server_id (int): L'ID du serveur.

        Returns:
            dict: Un dictionnaire avec les langues comme clés et les IDs des rôles comme valeurs.
        """
        language_roles = {}
        languages = ["francais", "anglais", "espagnol"]
        for lang in languages:
            try:
                role_id = await MatchmakingService.get_role_id(server_id, lang)
                if role_id:
                    language_roles[lang] = role_id
            except Exception as e:
                logger.error(f"Erreur lors de la récupération du rôle de langue '{lang}' pour server_id {server_id} : {e}")
        return language_roles

    @staticmethod
    async def get_persistent_message(guild_id: int, message_type: str) -> Optional[Tuple[int, int]]:
        """
        Récupère le channel_id et message_id pour un message persistant spécifique.
        """
        query = """
        SELECT channel_id, message_id
        FROM persistent_messages
        WHERE guild_id = $1 AND message_type = $2;
        """
        try:
            row = await database.fetchrow(query, guild_id, message_type)
            if row:
                return (row["channel_id"], row["message_id"])
            logger.warning(f"Message persistant de type '{message_type}' non trouvé pour guild_id {guild_id}.")
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du message persistant : {e}")
        return None

    @staticmethod
    async def save_persistent_message(guild_id: int, message_type: str, channel_id: int, message_id: int) -> None:
        """
        Sauvegarde ou met à jour un message persistant.
        """
        insert_query = """
        INSERT INTO persistent_messages (guild_id, message_type, channel_id, message_id)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (guild_id, message_type)
        DO UPDATE SET channel_id = EXCLUDED.channel_id, message_id = EXCLUDED.message_id;
        """
        try:
            await database.execute(insert_query, guild_id, message_type, channel_id, message_id)
            logger.info(f"Message persistant '{message_type}' sauvegardé pour guild_id {guild_id}.")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du message persistant : {e}")

    @staticmethod
    async def get_role_ids(server_id: int) -> Dict[str, int]:
        """
        Récupère les IDs des rôles Valorant pour un serveur donné.
        """
        roles = ["fill", "sentinel", "duelist", "controller", "initiator"]
        role_ids = {}
        for role in roles:
            try:
                role_id = await MatchmakingService.get_role_id(server_id, role)
                if role_id:
                    role_ids[role] = role_id
            except Exception as e:
                logger.error(f"Erreur lors de la récupération du rôle '{role}' pour server_id {server_id} : {e}")
        return role_ids
