import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional
import re

from cogs.utilities.request_manager import enqueue_request
from cogs.utilities.permission_manager import is_admin
from cogs.utilities.confirmation_view import PurgeConfirmationView

logger = logging.getLogger('discord.moderation.clean')

class Clean(commands.Cog):
    """Cog pour les commandes de nettoyage de messages."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    clean_group = app_commands.Group(
        name="clean",
        description="Commandes pour nettoyer les messages"
    )

    ACTION_CHOICES = [
        app_commands.Choice(name="Supprimer tous les messages", value="all"),
        app_commands.Choice(name="Supprimer les messages d'un utilisateur", value="user"),
        app_commands.Choice(name="Supprimer un nombre de messages", value="number"),
        app_commands.Choice(name="Supprimer à partir d'un message", value="from"),
        app_commands.Choice(name="Supprimer les messages avec images", value="image"),
        app_commands.Choice(name="Supprimer les messages avec GIFs", value="gif"),
        app_commands.Choice(name="Supprimer les messages avec liens", value="links"),
    ]

    async def ask_confirmation(self, interaction: discord.Interaction, message: str, count: Optional[int] = None):
        view = PurgeConfirmationView(interaction, interaction.channel, count)
        await interaction.followup.send(message, view=view, ephemeral=True)
        await view.wait()  # Attend que l'utilisateur interagisse ou que le timeout expire
        return view.value  # Retourne True, False ou None

    @clean_group.command(name="execute", description="Nettoie les messages selon le type et les options spécifiées.")
    @app_commands.describe(
        action="Type d'action de nettoyage à effectuer",
        user="L'utilisateur ciblé (pour l'action 'user')",
        count="Nombre de messages à supprimer (pour l'action 'number')",
        message_id="ID du message à partir duquel supprimer (pour l'action 'from')",
        scope="Portée: 'channel' ou 'all' (pour l'action 'user')"
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
        scope: Optional[str] = "channel"
    ):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send("Cette commande doit être utilisée dans un salon texte.", ephemeral=True)

        try:
            if action.value == "all":
                confirmation = await self.ask_confirmation(interaction, f"Confirmez-vous la suppression de **tous** les messages dans {channel.mention} ?")
                if confirmation:
                    deleted = await channel.purge(limit=None)
                    await interaction.followup.send(f"Tous les messages dans {channel.mention} ont été supprimés ({len(deleted)}).", ephemeral=True)
                else:
                    logger.info(f"Action annulée ou expirée par {interaction.user}.")
                    await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

            elif action.value == "user":
                if not user:
                    return await interaction.followup.send("Veuillez spécifier un utilisateur pour cette action.", ephemeral=True)
                if scope not in ("channel", "all"):
                    return await interaction.followup.send("Scope invalide. Utilisez 'channel' ou 'all'.", ephemeral=True)
                # Scope spécifique
                if scope == "channel":
                    confirmation = await self.ask_confirmation(interaction, f"Confirmez-vous la suppression de tous les messages de {user.mention} dans {channel.mention} ?")
                    if confirmation:
                        deleted = await channel.purge(limit=None, check=lambda m: m.author.id == user.id)
                        await interaction.followup.send(f"{len(deleted)} messages de {user.mention} supprimés dans {channel.mention}.", ephemeral=True)
                    else:
                        logger.info(f"Action annulée ou expirée par {interaction.user}.")
                        await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

                else:  # Scope global
                    confirmation = await self.ask_confirmation(interaction, f"Confirmez-vous la suppression de tous les messages de {user.mention} dans tous les salons du serveur ?")
                    if confirmation:
                        total_deleted = 0
                        for ch in interaction.guild.text_channels:
                            del_in_channel = await ch.purge(limit=None, check=lambda m: m.author.id == user.id)
                            total_deleted += len(del_in_channel)
                        await interaction.followup.send(f"{total_deleted} messages de {user.mention} supprimés dans tous les salons du serveur.", ephemeral=True)
                    else:
                        logger.info(f"Action annulée ou expirée par {interaction.user}.")
                        await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

            elif action.value == "number":
                if not count or count < 1 or count > 100:
                    return await interaction.followup.send("Le nombre de messages doit être entre 1 et 100.", ephemeral=True)
                confirmation = await self.ask_confirmation(interaction, f"Confirmez-vous la suppression des {count} derniers messages dans {channel.mention} ?", count=count)
                if confirmation:
                    deleted = await channel.purge(limit=count)
                    await interaction.followup.send(f"{len(deleted)} messages supprimés dans {channel.mention}.", ephemeral=True)
                else:
                    logger.info(f"Action annulée ou expirée par {interaction.user}.")
                    await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

            elif action.value == "from":
                if not message_id:
                    return await interaction.followup.send("Veuillez spécifier un ID de message pour cette action.", ephemeral=True)
                
                # Extraction de l'ID numérique à partir de la chaîne
                match = re.fullmatch(r'(\d{17,20})', message_id)
                if not match:
                    return await interaction.followup.send("Veuillez fournir un ID de message valide (seulement des chiffres).", ephemeral=True)
                try:
                    msg_id_int = int(match.group(1))
                    msg = await channel.fetch_message(msg_id_int)
                except (discord.NotFound, ValueError):
                    return await interaction.followup.send("Message introuvable ou ID invalide.", ephemeral=True)
                
                confirmation = await self.ask_confirmation(interaction, f"Confirmez-vous la suppression de tous les messages à partir du message `{msg_id_int}` dans {channel.mention} ?")
                if confirmation:
                    def after_check(m):
                        return m.id >= msg.id
                    deleted = await channel.purge(limit=None, check=after_check)
                    await interaction.followup.send(f"{len(deleted)} messages supprimés dans {channel.mention} après le message `{msg_id_int}`.", ephemeral=True)
                else:
                    logger.info(f"Action annulée ou expirée par {interaction.user}.")
                    await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

            elif action.value == "image":
                confirmation = await self.ask_confirmation(interaction, f"Confirmez-vous la suppression de tous les messages avec images dans {channel.mention} ?")
                if confirmation:
                    def image_check(m: discord.Message):
                        return any(att.content_type.startswith("image/") for att in m.attachments if att.content_type) or any(e.image or e.thumbnail for e in m.embeds)
                    deleted = await channel.purge(limit=None, check=image_check)
                    await interaction.followup.send(f"{len(deleted)} messages avec images supprimés dans {channel.mention}.", ephemeral=True)
                else:
                    logger.info(f"Action annulée ou expirée par {interaction.user}.")
                    await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

            elif action.value == "gif":
                confirmation = await self.ask_confirmation(interaction, f"Confirmez-vous la suppression de tous les messages avec gifs dans {channel.mention} ?")
                if confirmation:
                    def gif_check(m: discord.Message):
                        return any("gif" in (att.content_type or "") for att in m.attachments) or ".gif" in m.content.lower()
                    deleted = await channel.purge(limit=None, check=gif_check)
                    await interaction.followup.send(f"{len(deleted)} messages avec gifs supprimés dans {channel.mention}.", ephemeral=True)
                else:
                    logger.info(f"Action annulée ou expirée par {interaction.user}.")
                    await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

            elif action.value == "links":
                confirmation = await self.ask_confirmation(interaction, f"Confirmez-vous la suppression de tous les messages avec liens dans {channel.mention} ?")
                if confirmation:
                    def links_check(m: discord.Message):
                        return "http://" in m.content.lower() or "https://" in m.content.lower()
                    deleted = await channel.purge(limit=None, check=links_check)
                    await interaction.followup.send(f"{len(deleted)} messages avec liens supprimés dans {channel.mention}.", ephemeral=True)
                else:
                    logger.info(f"Action annulée ou expirée par {interaction.user}.")
                    await interaction.followup.send("Action annulée ou confirmation expirée.", ephemeral=True)

            else:
                await interaction.followup.send("Action invalide spécifiée.", ephemeral=True)

        except discord.HTTPException as e:
            await interaction.followup.send("Une erreur est survenue lors de l'exécution.", ephemeral=True)
            logger.exception(f"Erreur HTTP lors du nettoyage dans {channel.name}: {e}")

    @clean_execute.error
    async def clean_command_error(self, interaction: discord.Interaction, error: Exception):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.followup.send(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté d'utiliser une commande clean sans les permissions requises.")
        else:
            await interaction.followup.send(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors d'une commande clean par {interaction.user}: {error}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Clean(bot))
    logger.info("Clean Cog chargé avec succès.")
