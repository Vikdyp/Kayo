#cogs\moderation\services\clean_service.py
import discord
import logging
from typing import Optional
from utils.database import database

logger = logging.getLogger('cogs.moderation.services.clean_service')


class CleanService:
    @staticmethod
    async def delete_all_messages(channel: discord.TextChannel, deleted_by: discord.Member) -> int:
        """Supprime tous les messages d'un salon et enregistre l'action dans la base de données."""
        try:
            deleted = await channel.purge(limit=None)
            logger.info(f"{len(deleted)} messages supprimés dans {channel.name} par {deleted_by}.")
            
            # Enregistrement dans la base de données
            await database.log_message_deletion(
                deleted_by=deleted_by.name,
                channel=channel.name,
                guild=channel.guild.name,
                deletion_type="all",
                target_user=None,
                message_count=len(deleted)
            )
            return len(deleted)
        except discord.Forbidden:
            logger.error(f"Permissions insuffisantes pour supprimer les messages dans {channel.name}.")
            raise
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de la suppression des messages dans {channel.name}: {e}")
            raise

    @staticmethod
    async def delete_user_messages(channel: discord.TextChannel, user: discord.Member, deleted_by: discord.Member) -> int:
        """Supprime les messages d'un utilisateur spécifique et enregistre l'action."""
        try:
            deleted = await channel.purge(limit=None, check=lambda m: m.author.id == user.id)
            logger.info(f"{len(deleted)} messages de {user.display_name} supprimés dans {channel.name} par {deleted_by}.")
            
            # Enregistrement dans la base de données
            await database.log_message_deletion(
                deleted_by=deleted_by.name,
                channel=channel.name,
                guild=channel.guild.name,
                deletion_type="user",
                target_user=user.name,
                message_count=len(deleted)
            )
            return len(deleted)
        except discord.Forbidden:
            logger.error(f"Permissions insuffisantes pour supprimer les messages de {user.display_name} dans {channel.name}.")
            raise
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de la suppression des messages de {user.display_name} dans {channel.name}: {e}")
            raise

    @staticmethod
    async def delete_messages_after(channel: discord.TextChannel, message_id: int, deleted_by: discord.Member) -> int:
        """Supprime les messages après un message spécifique et enregistre l'action."""
        try:
            message = await channel.fetch_message(message_id)
            deleted = await channel.purge(limit=None, check=lambda m: m.created_at > message.created_at)
            logger.info(f"{len(deleted)} messages supprimés après le message {message.id} dans {channel.name} par {deleted_by}.")
            
            # Enregistrement dans la base de données
            await database.log_message_deletion(
                deleted_by=deleted_by.name,
                channel=channel.name,
                guild=channel.guild.name,
                deletion_type="from",
                target_user=None,
                message_count=len(deleted)
            )
            return len(deleted)
        except discord.NotFound:
            logger.error(f"Message avec l'ID {message_id} introuvable dans {channel.name}.")
            raise
        except discord.Forbidden:
            logger.error(f"Permissions insuffisantes pour supprimer les messages dans {channel.name}.")
            raise
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de la suppression des messages dans {channel.name}: {e}")
            raise

    @staticmethod
    async def delete_messages_with_condition(channel: discord.TextChannel, condition: callable, deleted_by: discord.Member) -> int:
        """Supprime les messages répondant à une condition spécifique et enregistre l'action."""
        try:
            deleted = await channel.purge(limit=None, check=condition)
            logger.info(f"{len(deleted)} messages supprimés répondant à une condition dans {channel.name} par {deleted_by}.")

            # Vérifier si des messages ont été supprimés avant d'enregistrer
            if len(deleted) > 0:
                await database.log_message_deletion(
                    deleted_by=deleted_by.name,
                    channel=channel.name,
                    guild=channel.guild.name,
                    deletion_type="condition",
                    target_user=None,
                    message_count=len(deleted)
                )
            return len(deleted)
        except discord.Forbidden:
            logger.error(f"Permissions insuffisantes pour supprimer les messages répondant à une condition dans {channel.name}.")
            raise
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de la suppression des messages répondant à une condition dans {channel.name}: {e}")
            raise


