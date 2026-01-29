# cogs/moderation/services/automod_service.py

import logging
from typing import Optional, List, Dict, Any
from utils.database import database
from utils.base import get_or_create_server_record

logger = logging.getLogger(__name__)


class AutomodService:
    """Service pour gérer la configuration de l'auto-modération."""

    @staticmethod
    async def get_or_create_server_record(guild_id: int, guild_name: str) -> int:
        """Wrapper vers la fonction utilitaire."""
        return await get_or_create_server_record(guild_id, guild_name)

    @staticmethod
    async def get_config(guild_id: int, guild_name: str) -> Optional[Dict[str, Any]]:
        """
        Récupère la configuration automod pour un serveur.
        Retourne None si aucune config n'existe.
        """
        try:
            server_db_id = await AutomodService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return None

            query = """
            SELECT
                scam_detection_enabled,
                spam_detection_enabled,
                spam_channel_threshold,
                spam_time_window,
                delete_messages_on_scam,
                delete_period_hours,
                whitelisted_roles,
                whitelisted_channels,
                custom_scam_patterns,
                custom_scam_domains
            FROM automod_config
            WHERE server_id = $1;
            """
            row = await database.fetchrow(query, server_db_id)
            if row:
                return dict(row)
            return None

        except Exception as e:
            logger.error(f"Erreur get_config pour guild {guild_id}: {e}")
            return None

    @staticmethod
    async def get_or_create_config(guild_id: int, guild_name: str) -> Dict[str, Any]:
        """
        Récupère ou crée la configuration automod pour un serveur.
        Retourne toujours une config (avec valeurs par défaut si nouvelle).
        """
        config = await AutomodService.get_config(guild_id, guild_name)
        if config:
            return config

        # Créer une nouvelle config avec les valeurs par défaut
        try:
            server_db_id = await AutomodService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return AutomodService._default_config()

            query = """
            INSERT INTO automod_config (server_id)
            VALUES ($1)
            ON CONFLICT (server_id) DO NOTHING
            RETURNING *;
            """
            row = await database.fetchrow(query, server_db_id)
            if row:
                return dict(row)

            # Si RETURNING n'a rien donné (conflit), récupérer la config existante
            return await AutomodService.get_config(guild_id, guild_name) or AutomodService._default_config()

        except Exception as e:
            logger.error(f"Erreur get_or_create_config pour guild {guild_id}: {e}")
            return AutomodService._default_config()

    @staticmethod
    def _default_config() -> Dict[str, Any]:
        """Retourne la configuration par défaut."""
        return {
            'scam_detection_enabled': True,
            'spam_detection_enabled': True,
            'spam_channel_threshold': 3,
            'spam_time_window': 60,
            'delete_messages_on_scam': True,
            'delete_period_hours': 24,
            'whitelisted_roles': [],
            'whitelisted_channels': [],
            'custom_scam_patterns': [],
            'custom_scam_domains': [],
        }

    @staticmethod
    async def set_scam_detection(guild_id: int, guild_name: str, enabled: bool) -> bool:
        """Active ou désactive la détection de scam."""
        return await AutomodService._update_field(guild_id, guild_name, 'scam_detection_enabled', enabled)

    @staticmethod
    async def set_spam_detection(guild_id: int, guild_name: str, enabled: bool) -> bool:
        """Active ou désactive la détection de spam."""
        return await AutomodService._update_field(guild_id, guild_name, 'spam_detection_enabled', enabled)

    @staticmethod
    async def set_spam_threshold(guild_id: int, guild_name: str, threshold: int) -> bool:
        """Définit le seuil de salons pour la détection de spam."""
        return await AutomodService._update_field(guild_id, guild_name, 'spam_channel_threshold', threshold)

    @staticmethod
    async def set_spam_time_window(guild_id: int, guild_name: str, seconds: int) -> bool:
        """Définit la fenêtre de temps pour la détection de spam."""
        return await AutomodService._update_field(guild_id, guild_name, 'spam_time_window', seconds)

    @staticmethod
    async def _update_field(guild_id: int, guild_name: str, field: str, value: Any) -> bool:
        """Met à jour un champ de la configuration."""
        try:
            # S'assurer que la config existe
            await AutomodService.get_or_create_config(guild_id, guild_name)

            server_db_id = await AutomodService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return False

            query = f"""
            UPDATE automod_config
            SET {field} = $1, updated_at = CURRENT_TIMESTAMP
            WHERE server_id = $2;
            """
            await database.execute(query, value, server_db_id)
            logger.info(f"Automod config mise à jour: {field}={value} pour server_id={server_db_id}")
            return True

        except Exception as e:
            logger.error(f"Erreur _update_field {field} pour guild {guild_id}: {e}")
            return False

    @staticmethod
    async def add_whitelisted_role(guild_id: int, guild_name: str, role_id: int) -> bool:
        """Ajoute un rôle à la whitelist."""
        try:
            await AutomodService.get_or_create_config(guild_id, guild_name)
            server_db_id = await AutomodService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return False

            query = """
            UPDATE automod_config
            SET whitelisted_roles = array_append(whitelisted_roles, $1),
                updated_at = CURRENT_TIMESTAMP
            WHERE server_id = $2 AND NOT ($1 = ANY(whitelisted_roles));
            """
            await database.execute(query, role_id, server_db_id)
            return True

        except Exception as e:
            logger.error(f"Erreur add_whitelisted_role: {e}")
            return False

    @staticmethod
    async def remove_whitelisted_role(guild_id: int, guild_name: str, role_id: int) -> bool:
        """Retire un rôle de la whitelist."""
        try:
            server_db_id = await AutomodService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return False

            query = """
            UPDATE automod_config
            SET whitelisted_roles = array_remove(whitelisted_roles, $1),
                updated_at = CURRENT_TIMESTAMP
            WHERE server_id = $2;
            """
            await database.execute(query, role_id, server_db_id)
            return True

        except Exception as e:
            logger.error(f"Erreur remove_whitelisted_role: {e}")
            return False

    @staticmethod
    async def add_whitelisted_channel(guild_id: int, guild_name: str, channel_id: int) -> bool:
        """Ajoute un salon à la whitelist."""
        try:
            await AutomodService.get_or_create_config(guild_id, guild_name)
            server_db_id = await AutomodService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return False

            query = """
            UPDATE automod_config
            SET whitelisted_channels = array_append(whitelisted_channels, $1),
                updated_at = CURRENT_TIMESTAMP
            WHERE server_id = $2 AND NOT ($1 = ANY(whitelisted_channels));
            """
            await database.execute(query, channel_id, server_db_id)
            return True

        except Exception as e:
            logger.error(f"Erreur add_whitelisted_channel: {e}")
            return False

    @staticmethod
    async def remove_whitelisted_channel(guild_id: int, guild_name: str, channel_id: int) -> bool:
        """Retire un salon de la whitelist."""
        try:
            server_db_id = await AutomodService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return False

            query = """
            UPDATE automod_config
            SET whitelisted_channels = array_remove(whitelisted_channels, $1),
                updated_at = CURRENT_TIMESTAMP
            WHERE server_id = $2;
            """
            await database.execute(query, channel_id, server_db_id)
            return True

        except Exception as e:
            logger.error(f"Erreur remove_whitelisted_channel: {e}")
            return False

    @staticmethod
    async def add_custom_pattern(guild_id: int, guild_name: str, pattern: str) -> bool:
        """Ajoute un pattern de scam personnalisé."""
        try:
            await AutomodService.get_or_create_config(guild_id, guild_name)
            server_db_id = await AutomodService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return False

            query = """
            UPDATE automod_config
            SET custom_scam_patterns = array_append(custom_scam_patterns, $1),
                updated_at = CURRENT_TIMESTAMP
            WHERE server_id = $2 AND NOT ($1 = ANY(custom_scam_patterns));
            """
            await database.execute(query, pattern, server_db_id)
            return True

        except Exception as e:
            logger.error(f"Erreur add_custom_pattern: {e}")
            return False

    @staticmethod
    async def remove_custom_pattern(guild_id: int, guild_name: str, pattern: str) -> bool:
        """Retire un pattern de scam personnalisé."""
        try:
            server_db_id = await AutomodService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return False

            query = """
            UPDATE automod_config
            SET custom_scam_patterns = array_remove(custom_scam_patterns, $1),
                updated_at = CURRENT_TIMESTAMP
            WHERE server_id = $2;
            """
            await database.execute(query, pattern, server_db_id)
            return True

        except Exception as e:
            logger.error(f"Erreur remove_custom_pattern: {e}")
            return False

    @staticmethod
    async def add_custom_domain(guild_id: int, guild_name: str, domain: str) -> bool:
        """Ajoute un domaine de scam personnalisé."""
        try:
            await AutomodService.get_or_create_config(guild_id, guild_name)
            server_db_id = await AutomodService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return False

            # Normaliser le domaine (minuscules, sans protocole)
            domain = domain.lower().replace("https://", "").replace("http://", "").strip("/")

            query = """
            UPDATE automod_config
            SET custom_scam_domains = array_append(custom_scam_domains, $1),
                updated_at = CURRENT_TIMESTAMP
            WHERE server_id = $2 AND NOT ($1 = ANY(custom_scam_domains));
            """
            await database.execute(query, domain, server_db_id)
            return True

        except Exception as e:
            logger.error(f"Erreur add_custom_domain: {e}")
            return False

    @staticmethod
    async def remove_custom_domain(guild_id: int, guild_name: str, domain: str) -> bool:
        """Retire un domaine de scam personnalisé."""
        try:
            server_db_id = await AutomodService.get_or_create_server_record(guild_id, guild_name)
            if not server_db_id:
                return False

            domain = domain.lower().replace("https://", "").replace("http://", "").strip("/")

            query = """
            UPDATE automod_config
            SET custom_scam_domains = array_remove(custom_scam_domains, $1),
                updated_at = CURRENT_TIMESTAMP
            WHERE server_id = $2;
            """
            await database.execute(query, domain, server_db_id)
            return True

        except Exception as e:
            logger.error(f"Erreur remove_custom_domain: {e}")
            return False
