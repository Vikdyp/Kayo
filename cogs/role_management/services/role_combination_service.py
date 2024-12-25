# cogs/role_management/services/role_combination_service.py

from typing import List, Dict, Optional
from utils.database import database
import logging

logger = logging.getLogger("role_combination_service")


class RoleCombinationService:
    """Service pour gérer les combinaisons de rôles."""

    @staticmethod
    async def get_role_combinations(guild_id: int) -> List[Dict[str, int]]:
        """
        Récupère toutes les combinaisons de rôles configurées pour un serveur spécifique.

        :param guild_id: ID du serveur Discord.
        :return: Liste des combinaisons de rôles avec leurs IDs Discord.
        """
        query = """
        SELECT 
            rc.primary_role_id, 
            rc.secondary_role_id, 
            rc.combined_role_id,
            r1.role_id AS primary_role_id_discord, 
            r2.role_id AS secondary_role_id_discord, 
            r3.role_id AS combined_role_id_discord
        FROM role_combinations rc
        JOIN roles_configurations r1 ON rc.primary_role_id = r1.id
        JOIN roles_configurations r2 ON rc.secondary_role_id = r2.id
        JOIN roles_configurations r3 ON rc.combined_role_id = r3.id
        WHERE rc.guild_id = $1;
        """
        try:
            records = await database.fetch(query, guild_id)
            combinations = [
                {
                    "primary_role_id": record["primary_role_id_discord"],
                    "secondary_role_id": record["secondary_role_id_discord"],
                    "combined_role_id": record["combined_role_id_discord"],
                }
                for record in records
            ]
            logger.info(f"Combinaisons de rôles récupérées pour guild_id={guild_id}: {combinations}")
            return combinations
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des combinaisons de rôles pour guild_id={guild_id}: {e}")
            return []

    @staticmethod
    async def add_role_combination(
        guild_id: int, primary_role_id: int, secondary_role_id: int, combined_role_id: int
    ) -> bool:
        """
        Ajoute une nouvelle combinaison de rôles dans la base de données.

        :param guild_id: ID du serveur Discord.
        :param primary_role_id: ID Discord du rôle principal.
        :param secondary_role_id: ID Discord du rôle secondaire.
        :param combined_role_id: ID Discord du rôle combiné résultant.
        :return: True si réussi, False sinon.
        """
        try:
            # Récupérer les IDs de configuration des rôles depuis roles_configurations
            primary_config_id = await RoleCombinationService.get_config_id(guild_id, primary_role_id)
            secondary_config_id = await RoleCombinationService.get_config_id(guild_id, secondary_role_id)
            combined_config_id = await RoleCombinationService.get_config_id(guild_id, combined_role_id)

            logger.debug(f"Configuration IDs récupérés: primary={primary_config_id}, secondary={secondary_config_id}, combined={combined_config_id}")

            if not primary_config_id or not secondary_config_id or not combined_config_id:
                logger.warning(
                    f"Un ou plusieurs rôles spécifiés n'existent pas dans roles_configurations pour guild_id={guild_id}."
                )
                return False

            # Insérer la combinaison dans role_combinations
            query = """
            INSERT INTO role_combinations (guild_id, primary_role_id, secondary_role_id, combined_role_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, primary_role_id, secondary_role_id) DO UPDATE
            SET combined_role_id = EXCLUDED.combined_role_id;
            """
            result = await database.execute(query, guild_id, primary_config_id, secondary_config_id, combined_config_id)
            logger.info(
                f"Combinaison de rôles ajoutée pour guild_id={guild_id}: {primary_role_id} + {secondary_role_id} → {combined_role_id} - Résultat SQL: {result}"
            )
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout de la combinaison de rôles: {e}")
            return False

    @staticmethod
    async def remove_role_combination(
        guild_id: int, primary_role_id: int, secondary_role_id: int
    ) -> bool:
        """
        Supprime une combinaison de rôles de la base de données.

        :param guild_id: ID du serveur Discord.
        :param primary_role_id: ID Discord du rôle principal.
        :param secondary_role_id: ID Discord du rôle secondaire.
        :return: True si réussi, False sinon.
        """
        try:
            # Récupérer les IDs de configuration des rôles depuis roles_configurations
            primary_config_id = await RoleCombinationService.get_config_id(guild_id, primary_role_id)
            secondary_config_id = await RoleCombinationService.get_config_id(guild_id, secondary_role_id)

            if not primary_config_id or not secondary_config_id:
                logger.warning(
                    f"Un ou plusieurs rôles spécifiés n'existent pas dans roles_configurations pour guild_id={guild_id}."
                )
                return False

            # Supprimer la combinaison de role_combinations
            query = """
            DELETE FROM role_combinations
            WHERE guild_id = $1 AND primary_role_id = $2 AND secondary_role_id = $3;
            """
            result = await database.execute(query, guild_id, primary_config_id, secondary_config_id)
            logger.info(
                f"Combinaison de rôles supprimée pour guild_id={guild_id}: {primary_role_id} + {secondary_role_id} - Résultat SQL: {result}"
            )
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la suppression de la combinaison de rôles: {e}")
            return False

    @staticmethod
    async def get_config_id(guild_id: int, role_id: int) -> Optional[int]:
        """
        Récupère l'ID de configuration d'un rôle en fonction de son ID Discord et de l'ID du serveur.

        :param guild_id: ID du serveur Discord.
        :param role_id: ID Discord du rôle.
        :return: ID de configuration du rôle ou None si non trouvé.
        """
        query = """
        SELECT id FROM roles_configurations
        WHERE guild_id = $1 AND role_id = $2;
        """
        try:
            config_id = await database.fetchval(query, guild_id, role_id)
            if config_id:
                logger.debug(f"ID de configuration du rôle '{role_id}' récupéré : {config_id}")
            else:
                logger.warning(f"Rôle avec ID '{role_id}' non trouvé dans roles_configurations pour guild_id={guild_id}.")
            return config_id
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de l'ID de configuration du rôle '{role_id}': {e}")
            return None

    @staticmethod
    async def load_role_combinations():
        """
        Charge les combinaisons de rôles existantes depuis la base de données.
        (Optionnel : si vous avez besoin de charger les combinaisons au démarrage)
        """
        try:
            query = "SELECT DISTINCT guild_id FROM role_combinations;"
            guild_ids = await database.fetch(query)
            for guild in guild_ids:
                guild_id = guild["guild_id"]
                combinations = await RoleCombinationService.get_role_combinations(guild_id)
                logger.info(f"Guild ID {guild_id} a {len(combinations)} combinaisons de rôles configurées.")
        except Exception as e:
            logger.error(f"Erreur lors du chargement des combinaisons de rôles au démarrage: {e}")

    @staticmethod
    async def get_moderation_channel(self, guild_id: int) -> Optional[int]:
        """
        Récupère l'ID du salon de modération pour un serveur.
        """
        query = """
            SELECT channel_id
            FROM channel_configurations
            WHERE guild_id = $1 AND action = 'moderation'
        """
        async with self.bot.database.acquire() as connection:
            result = await connection.fetchrow(query, guild_id)
            if result:
                return result['channel_id']
            return None
