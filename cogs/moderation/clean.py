# cogs/moderation/clean.py
"""
Cog pour les commandes de nettoyage de messages.
Aucun accès DB direct - utilise CleanService.
"""

import io
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Any, Callable, Optional
import re

from cogs.moderation.presenters import DeletionHistoryEntry, format_deletion_history_table
from cogs.moderation.views.confirmation_view import ConfirmationView
from cogs.moderation.services.clean_service import CleanService

logger = logging.getLogger(__name__)


def is_admin():
    """Décorateur pour vérifier si un utilisateur a les permissions administratives."""
    def predicate(interaction: discord.Interaction):
        if interaction.user.guild_permissions.administrator:
            return True
        raise app_commands.MissingPermissions(["administrator"])
    return app_commands.check(predicate)


class Clean(commands.Cog):
    """Cog pour les commandes de nettoyage de messages."""

    def __init__(self, bot: commands.Bot, clean_service: CleanService):
        self.bot = bot
        self._clean_svc = clean_service

    async def _send_ephemeral_error(
        self,
        interaction: discord.Interaction,
        message: str,
        *,
        ephemeral: bool = True,
    ) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=ephemeral)
            return
        await interaction.response.send_message(message, ephemeral=ephemeral)

    ACTION_CHOICES = [
        app_commands.Choice(name="Supprimer tous les messages", value="all"),
        app_commands.Choice(name="Supprimer les messages d'un utilisateur", value="user"),
        app_commands.Choice(name="Supprimer un nombre de messages", value="number"),
        app_commands.Choice(name="Supprimer à partir d'un message", value="from"),
        app_commands.Choice(name="Supprimer les messages avec images", value="image"),
        app_commands.Choice(name="Supprimer les messages avec GIFs", value="gif"),
        app_commands.Choice(name="Supprimer les messages avec liens", value="links"),
        app_commands.Choice(name="Affiche l'historique des suppression", value="history"),
    ]

    async def ask_confirmation(
        self,
        interaction: discord.Interaction,
        message: str,
        callback: Callable[[Optional[bool]], Any],
        confirm_label: str = "Confirmer",
        confirm_style: discord.ButtonStyle = discord.ButtonStyle.green,
        cancel_label: str = "Annuler",
        cancel_style: discord.ButtonStyle = discord.ButtonStyle.grey,
        is_ephemeral: bool = False,
    ) -> Optional[bool]:
        """Pose une question de confirmation à l'utilisateur."""
        view = ConfirmationView(
            interaction=interaction,
            callback=callback,
            confirm_label=confirm_label,
            confirm_style=confirm_style,
            cancel_label=cancel_label,
            cancel_style=cancel_style,
            is_ephemeral=is_ephemeral,
        )
        await interaction.followup.send(message, view=view, ephemeral=is_ephemeral)
        await view.wait()
        return view.value

    async def get_user_name_or_mention(self, discord_id: Optional[int]) -> str:
        """
        Récupère le nom d'utilisateur ou mention pour un discord_id.
        Si l'utilisateur est introuvable, retourne simplement `<@ID>`.
        """
        if discord_id is None:
            return "Automatique"
        try:
            user = self.bot.get_user(discord_id) or await self.bot.fetch_user(discord_id)
            return f"@{user.display_name}" if user else f"<@{discord_id}>"
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du nom pour discord_id {discord_id} : {e}")
            return f"<@{discord_id}>"

    @app_commands.command(name="clean", description="Nettoie les messages selon le type et les options spécifiées.")
    @app_commands.describe(
        action="Type d'action de nettoyage à effectuer",
        user="L'utilisateur ciblé (pour l'action 'user')",
        count="Nombre de messages à supprimer (pour l'action 'number')",
        message_id="ID du message à partir duquel supprimer (pour l'action 'from')",
    )
    @app_commands.choices(action=ACTION_CHOICES)
    @is_admin()
    @app_commands.default_permissions(administrator=True)
    async def clean_execute(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        user: Optional[discord.Member] = None,
        count: Optional[int] = None,
        message_id: Optional[str] = None,
    ):
        """Exécute une action de nettoyage basée sur les choix de l'utilisateur."""
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            logger.warning("Commande utilisée en dehors d'un salon texte.")
            return await self._send_ephemeral_error(
                interaction,
                "Cette commande doit être utilisée dans un salon texte.",
                ephemeral=True,
            )

        try:
            await interaction.response.defer(thinking=True)

            if action.value == "all":
                async def confirmation_callback(value: Optional[bool]):
                    if value:
                        deleted_count = await self._clean_svc.delete_all_messages(channel, interaction.user)
                        await interaction.followup.send(
                            f"{deleted_count} messages ont été supprimés dans {channel.mention}.",
                            ephemeral=True,
                        )
                    else:
                        await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

                await self.ask_confirmation(
                    interaction,
                    f"Confirmez-vous la suppression des {self._clean_svc.max_purge_scan} derniers messages maximum dans {channel.mention} ?",
                    confirmation_callback,
                    confirm_label="Supprimer",
                    confirm_style=discord.ButtonStyle.red,
                    is_ephemeral=True,
                )

            elif action.value == "user":
                if not user:
                    await interaction.followup.send("Veuillez spécifier un utilisateur.", ephemeral=True)
                    return

                async def confirmation_callback(value: Optional[bool]):
                    if value:
                        deleted_count = await self._clean_svc.delete_user_messages(channel, user, interaction.user)
                        await interaction.followup.send(
                            f"{deleted_count} messages de {user.mention} ont été supprimés dans {channel.mention}.",
                            ephemeral=True,
                        )
                    else:
                        await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

                await self.ask_confirmation(
                    interaction,
                    f"Confirmez-vous la suppression des messages de {user.mention} dans {channel.mention} ?",
                    confirmation_callback,
                    confirm_label="Supprimer",
                    confirm_style=discord.ButtonStyle.red,
                    is_ephemeral=True,
                )

            elif action.value == "number":
                if not count or count <= 0:
                    await interaction.followup.send("Veuillez spécifier un nombre de messages valide.", ephemeral=True)
                    return
                if count > self._clean_svc.max_purge_scan:
                    await interaction.followup.send(
                        f"Le maximum autorisé est {self._clean_svc.max_purge_scan} messages.",
                        ephemeral=True,
                    )
                    return

                async def confirmation_callback(value: Optional[bool]):
                    if value:
                        deleted_count = await self._clean_svc.delete_last_messages(channel, count, interaction.user)
                        await interaction.followup.send(
                            f"{deleted_count} derniers messages supprimés dans {channel.mention}.",
                            ephemeral=True,
                        )
                    else:
                        await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

                await self.ask_confirmation(
                    interaction,
                    f"Confirmez-vous la suppression des {count} derniers messages dans {channel.mention} ?",
                    confirmation_callback,
                    confirm_label="Supprimer",
                    confirm_style=discord.ButtonStyle.red,
                    is_ephemeral=True,
                )

            elif action.value == "from":
                if not message_id:
                    await interaction.followup.send("Veuillez fournir l'ID d'un message valide.", ephemeral=True)
                    return

                try:
                    msg_id = int(message_id)
                except ValueError:
                    await interaction.followup.send("L'ID de message doit être un entier.", ephemeral=True)
                    return

                async def confirmation_callback(value: Optional[bool]):
                    if value:
                        deleted_count = await self._clean_svc.delete_messages_after(channel, msg_id, interaction.user)
                        await interaction.followup.send(
                            f"{deleted_count} messages supprimés après le message {msg_id} dans {channel.mention}.",
                            ephemeral=True,
                        )
                    else:
                        await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

                await self.ask_confirmation(
                    interaction,
                    f"Confirmez-vous la suppression des messages après le message {msg_id} dans {channel.mention} ?",
                    confirmation_callback,
                    confirm_label="Supprimer",
                    confirm_style=discord.ButtonStyle.red,
                    is_ephemeral=True,
                )

            elif action.value == "history":
                limit = 50
                try:
                    deletions = await self._clean_svc.get_deletion_history(interaction.guild.id, limit)
                    if not deletions:
                        await interaction.followup.send("Aucune suppression trouvée.", ephemeral=True)
                        return

                    history_entries = []
                    for d in deletions:
                        user_name = await self.get_user_name_or_mention(d.deleted_by_discord_id)
                        history_entries.append(
                            DeletionHistoryEntry(
                                id=d.id,
                                deleted_by_name=user_name,
                                channel_name=d.channel_name or "?",
                                deletion_type=d.deletion_type,
                                message_count=d.message_count,
                                created_at=d.created_at,
                            )
                        )

                    history_text = format_deletion_history_table(history_entries)

                    if len(history_text) > 2000:
                        history_file = io.BytesIO(history_text.encode("utf-8"))
                        await interaction.followup.send(
                            "L'historique est trop long pour être affiché. Voici un fichier contenant les données :",
                            file=discord.File(history_file, filename="history.txt"),
                            ephemeral=True,
                        )
                    else:
                        await interaction.followup.send(f"```{history_text}```", ephemeral=True)

                except Exception as e:
                    logger.error(f"Erreur lors de la récupération de l'historique des suppressions : {e}")
                    await interaction.followup.send(
                        "Une erreur est survenue lors de la récupération de l'historique.",
                        ephemeral=True,
                    )

            elif action.value in ["image", "gif", "links"]:
                if action.value == "image":
                    condition = lambda m: any(
                        a.filename.lower().endswith(("jpg", "jpeg", "png", "bmp", "webp", "tiff"))
                        for a in m.attachments
                    )
                    deletion_type = "image"
                    desc = "images"
                elif action.value == "gif":
                    condition = lambda m: (
                        any(a.url.lower().endswith("gif") for a in m.attachments)
                        or "gif" in m.content.lower()
                    )
                    deletion_type = "gif"
                    desc = "GIFs"
                elif action.value == "links":
                    condition = lambda m: bool(re.search(r"http[s]?://", m.content))
                    deletion_type = "links"
                    desc = "liens"

                async def confirmation_callback(value: Optional[bool]):
                    if value:
                        deleted_count = await self._clean_svc.delete_messages_with_condition(
                            channel,
                            condition,
                            interaction.user,
                            deletion_type=deletion_type,
                        )
                        await interaction.followup.send(
                            f"{deleted_count} messages contenant des {desc} ont ete supprimes dans {channel.mention}.",
                            ephemeral=True,
                        )
                    else:
                        await interaction.followup.send("Action annulee ou confirmation expiree.", ephemeral=True)

                await self.ask_confirmation(
                    interaction,
                    f"Confirmez-vous la suppression des messages contenant des {desc} dans {channel.mention} ?",
                    confirmation_callback,
                    confirm_label="Supprimer",
                    confirm_style=discord.ButtonStyle.red,
                    is_ephemeral=True,
                )

        except Exception as e:
            logger.exception(f"Erreur lors de l'exécution de la commande de nettoyage : {e}")
            await interaction.followup.send("Une erreur est survenue.", ephemeral=True)

    @clean_execute.error
    async def clean_command_error(self, interaction: discord.Interaction, error: Exception):
        if isinstance(error, app_commands.MissingPermissions):
            await self._send_ephemeral_error(
                interaction,
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True,
            )
        else:
            await self._send_ephemeral_error(
                interaction,
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True,
            )
            logger.exception(f"Erreur lors d'une commande clean : {error}")


async def setup(bot: commands.Bot):
    # Le service doit être initialisé dans bot.py et passé au cog
    clean_service = getattr(bot, "clean_service", None)
    if clean_service is None:
        logger.error("clean_service non initialisé dans le bot. Le cog Clean ne sera pas chargé.")
        return
    await bot.add_cog(Clean(bot, clean_service))
    logger.info("Clean Cog chargé avec succès.")
