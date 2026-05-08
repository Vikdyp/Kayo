# cogs/moderation/services/clean_service.py
"""
Service métier pour le nettoyage de messages.
Aucun accès DB direct - délègue à MessageDeletionsService.
"""

import discord
import logging
from typing import Callable, List, Optional

from database.services.message_deletions_service import MessageDeletionsService, MessageDeletionInfo

logger = logging.getLogger(__name__)

MAX_PURGE_SCAN = 1000


class CleanService:
    """
    Service métier pour les opérations de nettoyage de messages.
    Reçoit MessageDeletionsService en injection.
    """

    def __init__(self, message_deletions_svc: MessageDeletionsService):
        self._deletions_svc = message_deletions_svc
        self.max_purge_scan = MAX_PURGE_SCAN

    async def delete_all_messages(
        self,
        channel: discord.TextChannel,
        deleted_by: discord.Member,
    ) -> int:
        """Supprime tous les messages d'un salon et enregistre l'action."""
        try:
            deleted = await channel.purge(limit=MAX_PURGE_SCAN)
            count = len(deleted)
            logger.info(f"{count} messages supprimés dans {channel.name} par {deleted_by}.")

            if count > 0:
                await self._deletions_svc.log_deletion(
                    guild_id=channel.guild.id,
                    guild_name=channel.guild.name,
                    deleted_by_discord_id=deleted_by.id,
                    channel_id=channel.id,
                    channel_name=channel.name,
                    deletion_type="all",
                    target_user_discord_id=None,
                    target_user_tag=None,
                    message_count=count,
                )
            return count
        except discord.Forbidden:
            logger.error(f"Permissions insuffisantes pour supprimer les messages dans {channel.name}.")
            raise
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de la suppression des messages dans {channel.name}: {e}")
            raise

    async def delete_user_messages(
        self,
        channel: discord.TextChannel,
        user: discord.Member,
        deleted_by: discord.Member,
    ) -> int:
        """Supprime les messages d'un utilisateur spécifique et enregistre l'action."""
        try:
            deleted = await channel.purge(
                limit=MAX_PURGE_SCAN,
                check=lambda m: m.author.id == user.id,
            )
            count = len(deleted)
            logger.info(f"{count} messages de {user.display_name} supprimés dans {channel.name} par {deleted_by}.")

            if count > 0:
                await self._deletions_svc.log_deletion(
                    guild_id=channel.guild.id,
                    guild_name=channel.guild.name,
                    deleted_by_discord_id=deleted_by.id,
                    channel_id=channel.id,
                    channel_name=channel.name,
                    deletion_type="user",
                    target_user_discord_id=user.id,
                    target_user_tag=str(user),
                    message_count=count,
                )
            return count
        except discord.Forbidden:
            logger.error(f"Permissions insuffisantes pour supprimer les messages de {user.display_name} dans {channel.name}.")
            raise
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de la suppression des messages de {user.display_name} dans {channel.name}: {e}")
            raise

    async def delete_last_messages(
        self,
        channel: discord.TextChannel,
        count: int,
        deleted_by: discord.Member,
    ) -> int:
        """Supprime un nombre spécifique de messages et enregistre l'action."""
        try:
            count = min(count, MAX_PURGE_SCAN)
            deleted = await channel.purge(limit=count)
            actual_count = len(deleted)
            logger.info(f"{actual_count} messages supprimés dans {channel.name} par {deleted_by} (demandé: {count}).")

            if actual_count > 0:
                await self._deletions_svc.log_deletion(
                    guild_id=channel.guild.id,
                    guild_name=channel.guild.name,
                    deleted_by_discord_id=deleted_by.id,
                    channel_id=channel.id,
                    channel_name=channel.name,
                    deletion_type="number",
                    target_user_discord_id=None,
                    target_user_tag=None,
                    message_count=actual_count,
                )
            return actual_count
        except discord.Forbidden:
            logger.error(f"Permissions insuffisantes pour supprimer les messages dans {channel.name}.")
            raise
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de la suppression des messages dans {channel.name}: {e}")
            raise

    async def delete_messages_after(
        self,
        channel: discord.TextChannel,
        message_id: int,
        deleted_by: discord.Member,
    ) -> int:
        """Supprime les messages après un message spécifique et enregistre l'action."""
        try:
            message = await channel.fetch_message(message_id)
            deleted = await channel.purge(
                limit=MAX_PURGE_SCAN,
                check=lambda m: m.created_at > message.created_at,
            )
            count = len(deleted)
            logger.info(f"{count} messages supprimés après le message {message.id} dans {channel.name} par {deleted_by}.")

            if count > 0:
                await self._deletions_svc.log_deletion(
                    guild_id=channel.guild.id,
                    guild_name=channel.guild.name,
                    deleted_by_discord_id=deleted_by.id,
                    channel_id=channel.id,
                    channel_name=channel.name,
                    deletion_type="from",
                    target_user_discord_id=None,
                    target_user_tag=None,
                    message_count=count,
                )
            return count
        except discord.NotFound:
            logger.error(f"Message avec l'ID {message_id} introuvable dans {channel.name}.")
            raise
        except discord.Forbidden:
            logger.error(f"Permissions insuffisantes pour supprimer les messages dans {channel.name}.")
            raise
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de la suppression des messages dans {channel.name}: {e}")
            raise

    async def delete_messages_with_condition(
        self,
        channel: discord.TextChannel,
        condition: Callable,
        deleted_by: discord.Member,
        deletion_type: str = "condition",
    ) -> int:
        """Supprime les messages répondant à une condition spécifique et enregistre l'action."""
        try:
            deleted = await channel.purge(limit=MAX_PURGE_SCAN, check=condition)
            count = len(deleted)
            logger.info(f"{count} messages supprimés ({deletion_type}) dans {channel.name} par {deleted_by}.")

            if count > 0:
                await self._deletions_svc.log_deletion(
                    guild_id=channel.guild.id,
                    guild_name=channel.guild.name,
                    deleted_by_discord_id=deleted_by.id,
                    channel_id=channel.id,
                    channel_name=channel.name,
                    deletion_type=deletion_type,
                    target_user_discord_id=None,
                    target_user_tag=None,
                    message_count=count,
                )
            return count
        except discord.Forbidden:
            logger.error(f"Permissions insuffisantes pour supprimer les messages ({deletion_type}) dans {channel.name}.")
            raise
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de la suppression des messages ({deletion_type}) dans {channel.name}: {e}")
            raise

    async def get_deletion_history(
        self,
        guild_id: int,
        limit: int = 50,
    ) -> List[MessageDeletionInfo]:
        """Récupère l'historique des suppressions pour un serveur."""
        return await self._deletions_svc.get_recent_deletions(guild_id, limit)
