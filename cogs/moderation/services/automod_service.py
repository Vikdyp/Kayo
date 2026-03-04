# cogs/moderation/services/automod_service.py
"""
Service métier pour l'auto-modération.
Aucun accès DB direct - délègue à AutomodConfigService.
"""

import logging
from typing import Dict, Any, Optional, List

from database.services.automod_config_service import AutomodConfigService, AutomodConfig
from database.services.guild_channels_service import ChannelConfigurationService

logger = logging.getLogger(__name__)


class AutomodService:
    """
    Service métier pour gérer la configuration de l'auto-modération.
    Reçoit AutomodConfigService en injection.
    """

    def __init__(
        self,
        automod_config_svc: AutomodConfigService,
        channel_config_svc: ChannelConfigurationService,
    ):
        self._config_svc = automod_config_svc
        self._channel_svc = channel_config_svc

    def _config_to_dict(self, config: AutomodConfig) -> Dict[str, Any]:
        """Convertit une config en dictionnaire pour compatibilité."""
        return {
            "scam_detection_enabled": config.scam_detection_enabled,
            "spam_detection_enabled": config.spam_detection_enabled,
            "spam_channel_threshold": config.spam_channel_threshold,
            "spam_time_window": config.spam_time_window,
            "delete_messages_on_scam": config.delete_messages_on_scam,
            "delete_period_hours": config.delete_period_hours,
            "whitelisted_roles": config.whitelisted_roles,
            "whitelisted_channels": config.whitelisted_channels,
            "custom_scam_patterns": config.custom_scam_patterns,
            "custom_scam_domains": config.custom_scam_domains,
        }

    async def get_config(self, guild_id: int, guild_name: str) -> Optional[Dict[str, Any]]:
        """
        Récupère la configuration automod pour un serveur.
        Retourne None si aucune config n'existe.
        """
        try:
            config = await self._config_svc.get_config(guild_id)
            if not config:
                return None
            return self._config_to_dict(config)
        except Exception as e:
            logger.error(f"Erreur get_config pour guild {guild_id}: {e}")
            return None

    async def get_or_create_config(self, guild_id: int, guild_name: str) -> Dict[str, Any]:
        """
        Récupère ou crée la configuration automod pour un serveur.
        Retourne toujours une config (avec valeurs par défaut si nouvelle).
        """
        try:
            config = await self._config_svc.get_or_create_config(guild_id, guild_name)
            return self._config_to_dict(config)
        except Exception as e:
            logger.error(f"Erreur get_or_create_config pour guild {guild_id}: {e}")
            return self._config_to_dict(AutomodConfigService.DEFAULT_CONFIG)

    async def set_scam_detection(self, guild_id: int, guild_name: str, enabled: bool) -> bool:
        """Active ou désactive la détection de scam."""
        try:
            return await self._config_svc.set_scam_detection(guild_id, guild_name, enabled)
        except Exception as e:
            logger.error(f"Erreur set_scam_detection pour guild {guild_id}: {e}")
            return False

    async def set_spam_detection(self, guild_id: int, guild_name: str, enabled: bool) -> bool:
        """Active ou désactive la détection de spam."""
        try:
            return await self._config_svc.set_spam_detection(guild_id, guild_name, enabled)
        except Exception as e:
            logger.error(f"Erreur set_spam_detection pour guild {guild_id}: {e}")
            return False

    async def set_spam_threshold(self, guild_id: int, guild_name: str, threshold: int) -> bool:
        """Définit le seuil de salons pour la détection de spam."""
        try:
            return await self._config_svc.set_spam_threshold(guild_id, guild_name, threshold)
        except Exception as e:
            logger.error(f"Erreur set_spam_threshold pour guild {guild_id}: {e}")
            return False

    async def set_spam_time_window(self, guild_id: int, guild_name: str, seconds: int) -> bool:
        """Définit la fenêtre de temps pour la détection de spam."""
        try:
            return await self._config_svc.set_spam_time_window(guild_id, guild_name, seconds)
        except Exception as e:
            logger.error(f"Erreur set_spam_time_window pour guild {guild_id}: {e}")
            return False

    async def add_whitelisted_role(self, guild_id: int, guild_name: str, role_id: int) -> bool:
        """Ajoute un rôle à la whitelist."""
        try:
            return await self._config_svc.add_whitelisted_role(guild_id, guild_name, role_id)
        except Exception as e:
            logger.error(f"Erreur add_whitelisted_role: {e}")
            return False

    async def remove_whitelisted_role(self, guild_id: int, guild_name: str, role_id: int) -> bool:
        """Retire un rôle de la whitelist."""
        try:
            return await self._config_svc.remove_whitelisted_role(guild_id, role_id)
        except Exception as e:
            logger.error(f"Erreur remove_whitelisted_role: {e}")
            return False

    async def add_whitelisted_channel(self, guild_id: int, guild_name: str, channel_id: int) -> bool:
        """Ajoute un salon à la whitelist."""
        try:
            return await self._config_svc.add_whitelisted_channel(guild_id, guild_name, channel_id)
        except Exception as e:
            logger.error(f"Erreur add_whitelisted_channel: {e}")
            return False

    async def remove_whitelisted_channel(self, guild_id: int, guild_name: str, channel_id: int) -> bool:
        """Retire un salon de la whitelist."""
        try:
            return await self._config_svc.remove_whitelisted_channel(guild_id, channel_id)
        except Exception as e:
            logger.error(f"Erreur remove_whitelisted_channel: {e}")
            return False

    async def add_custom_pattern(self, guild_id: int, guild_name: str, pattern: str) -> bool:
        """Ajoute un pattern de scam personnalisé."""
        try:
            return await self._config_svc.add_custom_pattern(guild_id, guild_name, pattern)
        except Exception as e:
            logger.error(f"Erreur add_custom_pattern: {e}")
            return False

    async def remove_custom_pattern(self, guild_id: int, guild_name: str, pattern: str) -> bool:
        """Retire un pattern de scam personnalisé."""
        try:
            return await self._config_svc.remove_custom_pattern(guild_id, pattern)
        except Exception as e:
            logger.error(f"Erreur remove_custom_pattern: {e}")
            return False

    async def add_custom_domain(self, guild_id: int, guild_name: str, domain: str) -> bool:
        """Ajoute un domaine de scam personnalisé."""
        try:
            return await self._config_svc.add_custom_domain(guild_id, guild_name, domain)
        except Exception as e:
            logger.error(f"Erreur add_custom_domain: {e}")
            return False

    async def remove_custom_domain(self, guild_id: int, guild_name: str, domain: str) -> bool:
        """Retire un domaine de scam personnalisé."""
        try:
            return await self._config_svc.remove_custom_domain(guild_id, domain)
        except Exception as e:
            logger.error(f"Erreur remove_custom_domain: {e}")
            return False

    # --------------------------------------------------
    # CHANNELS
    # --------------------------------------------------

    async def get_mod_channel_id(self, guild_id: int) -> Optional[int]:
        """Récupère l'ID du channel de modération."""
        return await self._channel_svc.get_one(guild_id, "modération")
