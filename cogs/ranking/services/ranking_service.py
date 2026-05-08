# cogs/ranking/services/ranking_service.py
"""
Service metier pour le ranking Valorant.
Aucun acces DB direct - delegue aux DB services.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from database.services.valorant_db_service import ValorantDbService
from database.services.persistent_messages_service import PersistentMessagesService
from database.services.guild_roles_service import RoleConfigurationService
from database.services.guild_channels_service import ChannelConfigurationService

logger = logging.getLogger(__name__)

# Noms de role Valorant utilises dans guild_roles (key)
RANGS_VALORANT = (
    "fer", "bronze", "argent", "or", "platine",
    "diamant", "ascendant", "immortel", "radiant", "no_rank",
)

# Mapping rang API Valorant -> cle de role dans guild_roles
RANK_TO_ROLE_KEY: dict[str, str] = {
    "Iron 1": "fer", "Iron 2": "fer", "Iron 3": "fer",
    "Bronze 1": "bronze", "Bronze 2": "bronze", "Bronze 3": "bronze",
    "Silver 1": "argent", "Silver 2": "argent", "Silver 3": "argent",
    "Gold 1": "or", "Gold 2": "or", "Gold 3": "or",
    "Platinum 1": "platine", "Platinum 2": "platine", "Platinum 3": "platine",
    "Diamond 1": "diamant", "Diamond 2": "diamant", "Diamond 3": "diamant",
    "Ascendant 1": "ascendant", "Ascendant 2": "ascendant", "Ascendant 3": "ascendant",
    "Immortal 1": "immortel", "Immortal 2": "immortel", "Immortal 3": "immortel",
    "Radiant": "radiant",
    "Unrated": "no_rank",
}
RANK_TO_ROLE_KEY_LOWER = {rank.lower(): key for rank, key in RANK_TO_ROLE_KEY.items()}


class RankingService:
    """
    Service metier pour le ranking Valorant.
    Recoit les DB services en injection.
    """

    def __init__(
        self,
        valorant_db_svc: ValorantDbService,
        channel_config_svc: ChannelConfigurationService,
        role_config_svc: RoleConfigurationService,
        persistent_msg_svc: PersistentMessagesService,
    ):
        self._valo_db = valorant_db_svc
        self._channel_config = channel_config_svc
        self._role_config = role_config_svc
        self._persistent_msg = persistent_msg_svc

        # Cache local des role mappings par guild
        self._role_cache: dict[int, dict[str, int]] = {}
        self._role_cache_lock = asyncio.Lock()

    # ==================== channels ====================

    async def get_channel_id(self, guild_id: int, key: str) -> Optional[int]:
        return await self._channel_config.get_one(guild_id, key)

    # ==================== persistent messages ====================

    async def get_persistent_message(
        self, guild_id: int, msg_type: str
    ) -> Optional[dict]:
        info = await self._persistent_msg.get(guild_id, msg_type)
        if not info:
            return None
        return {"channel_id": info.channel_id, "message_id": info.message_id}

    async def store_persistent_message(
        self,
        guild_id: int,
        guild_name: str | None,
        channel_id: int,
        message_id: int,
        msg_type: str,
    ) -> bool:
        try:
            await self._persistent_msg.save(
                guild_id, guild_name, msg_type, channel_id, message_id,
            )
            return True
        except Exception as e:
            logger.error(f"[store_persistent_message] Erreur: {e}")
            return False

    # ==================== compte Valorant ====================

    async def link_account(
        self, discord_id: int, pseudo: str, tag: str
    ) -> bool:
        return await self._valo_db.link_account(discord_id, pseudo, tag)

    async def delete_account(self, discord_id: int) -> bool:
        return await self._valo_db.delete_account(discord_id)

    async def account_linked(self, discord_id: int) -> bool:
        return await self._valo_db.account_exists(discord_id)

    async def get_user_by_pseudo_tag(
        self, pseudo: str, tag: str
    ) -> Optional[int]:
        """Retourne le discord_id associe a ce pseudo#tag."""
        return await self._valo_db.get_by_pseudo_tag(pseudo, tag)

    async def reset_for_account_change(
        self, discord_id: int, pseudo: str, tag: str
    ) -> bool:
        return await self._valo_db.reset_for_account_change(discord_id, pseudo, tag)

    # ==================== pipeline ====================

    async def get_users_for_pipeline(self, limit: int = 50) -> list[dict]:
        return await self._valo_db.get_users_for_pipeline(limit)

    async def update_pipeline_success(
        self,
        discord_id: int,
        *,
        puuid: str | None = None,
        region: str | None = None,
        platform: str | None = None,
        rank: str | None = None,
        elo: int | None = None,
        pseudo: str | None = None,
        tag: str | None = None,
        current_season: int | None = None,
        current_act: int | None = None,
    ) -> bool:
        return await self._valo_db.update_pipeline_success(
            discord_id,
            puuid=puuid, region=region, platform=platform,
            rank=rank, elo=elo, pseudo=pseudo, tag=tag,
            current_season=current_season, current_act=current_act,
        )

    async def update_pipeline_error(self, discord_id: int) -> bool:
        return await self._valo_db.update_pipeline_error(discord_id)

    # ==================== activite ====================

    async def mark_inactive(self, discord_id: int) -> bool:
        return await self._valo_db.mark_inactive(discord_id)

    async def reactivate(self, discord_id: int) -> bool:
        return await self._valo_db.reactivate(discord_id)

    async def get_all_discord_ids(self) -> list[int]:
        return await self._valo_db.get_all_discord_ids()

    async def sync_presence(
        self,
        active_discord_ids: set[int],
        all_discord_ids: set[int],
    ) -> tuple[int, int]:
        """Reactive les presents, desactive les absents. Retourne (reactivated, deactivated)."""
        return await self._valo_db.sync_presence(active_discord_ids, all_discord_ids)

    # ==================== notification ====================

    async def get_last_notification(
        self, discord_id: int
    ) -> Optional[datetime]:
        return await self._valo_db.get_last_notification(discord_id)

    async def update_last_notification(
        self, discord_id: int, ts: datetime
    ) -> bool:
        return await self._valo_db.update_last_notification(discord_id, ts)

    # ==================== roles ====================

    async def get_role_mappings(self, guild_id: int) -> Optional[dict[str, int]]:
        """
        Retourne le mapping role_key -> role_id pour les rangs Valorant.
        Utilise un cache local avec invalidation horaire.
        """
        async with self._role_cache_lock:
            if guild_id in self._role_cache:
                return self._role_cache[guild_id]

        all_roles = await self._role_config.get_all(guild_id)
        if not all_roles:
            return None

        # Filtrer sur les cles de rangs Valorant
        role_mappings = {
            k: v for k, v in all_roles.items()
            if k in RANGS_VALORANT
        }

        if not role_mappings:
            return None

        async with self._role_cache_lock:
            self._role_cache[guild_id] = role_mappings
        return role_mappings

    async def refresh_role_mappings(self, guild_id: int) -> None:
        async with self._role_cache_lock:
            self._role_cache.pop(guild_id, None)
        await self.get_role_mappings(guild_id)

    async def get_ban_role_id(self, guild_id: int) -> Optional[int]:
        return await self._role_config.get_one(guild_id, "ban")

    @staticmethod
    def get_role_key_for_rank(rank_name: str | None) -> Optional[str]:
        """Retourne la cle de role guild_roles pour un rang Valorant API."""
        if not rank_name:
            return None
        return RANK_TO_ROLE_KEY_LOWER.get(rank_name.strip().lower())

    # ==================== stats ====================

    async def get_user_stats(self) -> dict[str, int]:
        return await self._valo_db.get_user_stats()
