#cogs\moderation\clean.py
import os
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Any, Callable, Optional
import re

from utils.request_manager import enqueue_request
from utils.confirmation_view import ConfirmationView
from cogs.moderation.services.clean_service import CleanService
from utils.database import database

logger = logging.getLogger('clean')


def is_admin():
    """Décorateur pour vérifier si un utilisateur a les permissions administratives."""
    def predicate(interaction: discord.Interaction):
        if interaction.user.guild_permissions.administrator:
            return True
        raise app_commands.MissingPermissions(["administrator"])
    return app_commands.check(predicate)


class Clean(commands.Cog):
    """Cog pour les commandes de nettoyage de messages."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
        cancel_style: discord.ButtonStyle = discord.ButtonStyle.grey
    ) -> Optional[bool]:
        """Pose une question de confirmation à l'utilisateur."""
        view = ConfirmationView(
            interaction=interaction,
            callback=callback,
            confirm_label=confirm_label,
            confirm_style=confirm_style,
            cancel_label=cancel_label,
            cancel_style=cancel_style
        )
        await interaction.followup.send(message, view=view, ephemeral=True)
        await view.wait()
        return view.value

    @app_commands.command(name="clean", description="Nettoie les messages selon le type et les options spécifiées.")
    @app_commands.describe(
        action="Type d'action de nettoyage à effectuer",
        user="L'utilisateur ciblé (pour l'action 'user')",
        count="Nombre de messages à supprimer (pour l'action 'number')",
        message_id="ID du message à partir duquel supprimer (pour l'action 'from')",
    )
    @app_commands.choices(action=ACTION_CHOICES)
    @is_admin()
    @enqueue_request()
    async def clean_execute(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        user: Optional[discord.Member] = None,
        count: Optional[int] = None,
        message_id: Optional[str] = None,
    ):
        """Exécute une action de nettoyage basée sur les choix de l'utilisateur."""
        def get_type_icon(deletion_type: str) -> str:
            """Retourne un émoji correspondant au type de suppression."""
            icons = {
                "all": "🧹",
                "user": "👤",
                "links": "🔗",
                "image": "📷",
                "gif": "🎞️",
                "condition": "⚙️",
                "from": "➡️"
            }
            return icons.get(deletion_type, "❓")

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            logger.warning("Commande utilisée en dehors d'un salon texte.")
            return await interaction.followup.send("Cette commande doit être utilisée dans un salon texte.", ephemeral=True)

        try:
            # Initialisation de confirmation_callback par défaut
            confirmation_callback = None

            if action.value == "all":
                async def confirmation_callback(value: Optional[bool]):
                    if value:
                        deleted_count = await CleanService.delete_all_messages(channel, interaction.user)
                        await interaction.followup.send(
                            f"Tous les messages dans {channel.mention} ont été supprimés ({deleted_count}).",
                            ephemeral=True
                        )
                    else:
                        await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

                await self.ask_confirmation(
                    interaction,
                    f"Confirmez-vous la suppression de **tous** les messages dans {channel.mention} ?",
                    confirmation_callback,
                    confirm_label="Supprimer",
                    confirm_style=discord.ButtonStyle.red
                )

            elif action.value == "user":
                if not user:
                    await interaction.followup.send("Veuillez spécifier un utilisateur.", ephemeral=True)
                    return

                async def confirmation_callback(value: Optional[bool]):
                    if value:
                        deleted_count = await CleanService.delete_user_messages(channel, user, interaction.user)
                        await interaction.followup.send(
                            f"{deleted_count} messages de {user.mention} ont été supprimés dans {channel.mention}.",
                            ephemeral=True
                        )
                    else:
                        await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

                await self.ask_confirmation(
                    interaction,
                    f"Confirmez-vous la suppression des messages de {user.mention} dans {channel.mention} ?",
                    confirmation_callback,
                    confirm_label="Supprimer",
                    confirm_style=discord.ButtonStyle.red
                )

            elif action.value == "number":
                if not count or count <= 0:
                    await interaction.followup.send("Veuillez spécifier un nombre de messages valide.", ephemeral=True)
                    return

                async def confirmation_callback(value: Optional[bool]):
                    if value:
                        deleted_count = await channel.purge(limit=count)
                        await interaction.followup.send(
                            f"{deleted_count} derniers messages supprimés dans {channel.mention}.",
                            ephemeral=True
                        )
                    else:
                        await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

                await self.ask_confirmation(
                    interaction,
                    f"Confirmez-vous la suppression des {count} derniers messages dans {channel.mention} ?",
                    confirmation_callback,
                    confirm_label="Supprimer",
                    confirm_style=discord.ButtonStyle.red
                )

            elif action.value == "from":
                if not message_id:
                    await interaction.followup.send("Veuillez fournir l'ID d'un message valide.", ephemeral=True)
                    return

                try:
                    message_id = int(message_id)
                except ValueError:
                    await interaction.followup.send("L'ID de message doit être un entier.", ephemeral=True)
                    return

                async def confirmation_callback(value: Optional[bool]):
                    if value:
                        deleted_count = await CleanService.delete_messages_after(channel, message_id, interaction.user)
                        await interaction.followup.send(
                            f"{deleted_count} messages supprimés après le message {message_id} dans {channel.mention}.",
                            ephemeral=True
                        )
                    else:
                        await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

                await self.ask_confirmation(
                    interaction,
                    f"Confirmez-vous la suppression des messages après le message {message_id} dans {channel.mention} ?",
                    confirmation_callback,
                    confirm_label="Supprimer",
                    confirm_style=discord.ButtonStyle.red
                )

            elif action.value == "history":
                limit = 50
                try:
                    if limit > 100:
                        await interaction.followup.send("La limite doit être inférieure ou égale à 100.", ephemeral=True)
                        return

                    deletions = await database.get_message_deletions(limit=limit)
                    if not deletions:
                        await interaction.followup.send("Aucune suppression trouvée.", ephemeral=True)
                        return

                    table_header = (
                        "╔════╦══════════════╦═════════════╦══════════════╦═══════╦══════════════════╗\n"
                        "║ ID ║ Supprimé par ║ Salon       ║ Type         ║ Nb.   ║ Date             ║\n"
                        "╠════╬══════════════╬═════════════╬══════════════╬═══════╬══════════════════╣\n"
                    )

                    table_rows = "\n".join([
                        f"║ {d['id']:<2} ║ {d['deleted_by_user']:<12} ║ #{d['channel_name']:<10} ║ "
                        f"{get_type_icon(d['deletion_type'])} {d['deletion_type']:<9} ║ "
                        f"{d['message_count']:<5} ║ {d['timestamp'].strftime('%d/%m/%Y %H:%M'):<15} ║"
                        for d in deletions
                    ])

                    table_footer = (
                        "\n╚════╩══════════════╩═════════════╩══════════════╩═══════╩══════════════════╝"
                    )

                    history_text = f"{table_header}{table_rows}{table_footer}"

                    if len(history_text) > 2000:
                        with open("history.txt", "w", encoding="utf-8") as file:
                            file.write(history_text)
                        await interaction.followup.send(
                            "L'historique est trop long pour être affiché. Voici un fichier contenant les données :",
                            file=discord.File("history.txt"),
                            ephemeral=True
                        )
                        os.remove("history.txt")
                    else:
                        await interaction.followup.send(f"```{history_text}```", ephemeral=True)

                except Exception as e:
                    logger.error(f"Erreur lors de la récupération de l'historique des suppressions : {e}")
                    await interaction.followup.send("Une erreur est survenue lors de la récupération de l'historique.", ephemeral=True)

            elif action.value in ["image", "gif", "links"]:
                if action.value == "image":
                    condition = lambda m: any(a.url.lower().endswith(("jpg", "jpeg", "png")) for a in m.attachments)
                elif action.value == "gif":
                    condition = lambda m: any(a.url.lower().endswith("gif") for a in m.attachments) or "gif" in m.content.lower()
                elif action.value == "links":
                    condition = lambda m: re.search(r"http[s]?://", m.content)

        except Exception as e:
            logger.exception(f"Erreur lors de l'exécution de la commande de nettoyage : {e}")
            await interaction.followup.send("Une erreur est survenue.", ephemeral=True)


    @clean_execute.error
    async def clean_command_error(self, interaction: discord.Interaction, error: Exception):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.followup.send(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors d'une commande clean : {error}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Clean(bot))
    logger.info("Clean Cog chargé avec succès.")
