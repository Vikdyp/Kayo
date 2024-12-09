# cogs/moderation/clean.py
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional

from cogs.utilities.request_manager import enqueue_request
from cogs.utilities.permission_manager import is_admin
from cogs.utilities.confirmation_view import ConfirmationView

logger = logging.getLogger('discord.moderation.clean')

class Clean(commands.Cog):
    """Cog pour les commandes de nettoyage de messages."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    clean_group = app_commands.Group(
        name="clean",
        description="Commandes pour nettoyer les messages"
    )

    async def ask_confirmation(self, interaction: discord.Interaction, message: str):
        view = ConfirmationView(interaction, None)
        await interaction.followup.send(message, view=view, ephemeral=True)
        await view.wait()
        return view.value

    @clean_group.command(name="all", description="Supprime tous les messages du salon actuel.")
    @is_admin()
    @enqueue_request()
    async def clean_all(self, interaction: discord.Interaction):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send("Cette commande doit être utilisée dans un salon texte.", ephemeral=True)
        if not await self.ask_confirmation(interaction, f"Confirmez-vous la suppression de **tous** les messages dans {channel.mention} ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)
        deleted = await channel.purge(limit=None)
        await interaction.followup.send(f"Tous les messages dans {channel.mention} ont été supprimés ({len(deleted)}).", ephemeral=True)
        logger.info(f"{interaction.user} a nettoyé tous les messages dans {channel.name}.")

    @clean_group.command(name="user", description="Supprime tous les messages d'un utilisateur (dans ce salon ou tous).")
    @app_commands.describe(user="L'utilisateur dont les messages doivent être supprimés", scope="Scope: 'channel' ou 'all'")
    @is_admin()
    @enqueue_request()
    async def clean_user(self, interaction: discord.Interaction, user: discord.Member, scope: Optional[str] = "channel"):
        if scope not in ("channel", "all"):
            return await interaction.followup.send("Scope invalide. Utilisez 'channel' ou 'all'.", ephemeral=True)

        if scope == "channel":
            channel = interaction.channel
            if not isinstance(channel, discord.TextChannel):
                return await interaction.followup.send("Cette commande doit être utilisée dans un salon texte.", ephemeral=True)
            if not await self.ask_confirmation(interaction, f"Confirmez-vous la suppression de tous les messages de {user.mention} dans {channel.mention} ?"):
                return await interaction.followup.send("Action annulée.", ephemeral=True)
            deleted = await channel.purge(limit=None, check=lambda m: m.author.id == user.id)
            await interaction.followup.send(f"{len(deleted)} messages de {user.mention} supprimés dans {channel.mention}.", ephemeral=True)
            logger.info(f"{interaction.user} a nettoyé les messages de {user.display_name} dans {channel.name}.")
        else:
            if not interaction.guild:
                return await interaction.followup.send("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            if not await self.ask_confirmation(interaction, f"Confirmez-vous la suppression de tous les messages de {user.mention} dans tous les salons du serveur ?"):
                return await interaction.followup.send("Action annulée.", ephemeral=True)
            total_deleted = 0
            for ch in interaction.guild.text_channels:
                del_in_channel = await ch.purge(limit=None, check=lambda m: m.author.id == user.id)
                total_deleted += len(del_in_channel)
            await interaction.followup.send(f"{total_deleted} messages de {user.mention} supprimés dans tous les salons du serveur.", ephemeral=True)
            logger.info(f"{interaction.user} a nettoyé les messages de {user.display_name} dans tous les salons.")

    @clean_group.command(name="number", description="Supprime un nombre spécifié de messages récents.")
    @app_commands.describe(count="Nombre de messages à supprimer (1-100)")
    @is_admin()
    @enqueue_request()
    async def clean_number(self, interaction: discord.Interaction, count: int):
        if count < 1 or count > 100:
            return await interaction.followup.send("Le nombre de messages doit être entre 1 et 100.", ephemeral=True)
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send("Cette commande doit être utilisée dans un salon texte.", ephemeral=True)
        if not await self.ask_confirmation(interaction, f"Confirmez-vous la suppression des {count} derniers messages dans {channel.mention} ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)
        deleted = await channel.purge(limit=count)
        await interaction.followup.send(f"{len(deleted)} messages supprimés dans {channel.mention}.", ephemeral=True)
        logger.info(f"{interaction.user} a nettoyé {len(deleted)} messages dans {channel.name}.")

    @clean_group.command(name="from", description="Supprime tous les messages à partir d'un message donné.")
    @app_commands.describe(message_id="ID du message à partir duquel supprimer")
    @is_admin()
    @enqueue_request()
    async def clean_from(self, interaction: discord.Interaction, message_id: int):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send("Cette commande doit être utilisée dans un salon texte.", ephemeral=True)
        try:
            msg = await channel.fetch_message(message_id)
        except discord.NotFound:
            return await interaction.followup.send("Message introuvable.", ephemeral=True)
        if not await self.ask_confirmation(interaction, f"Confirmez-vous la suppression de tous les messages à partir du message {message_id} dans {channel.mention} ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)
        def after_check(m):
            return m.id >= msg.id
        deleted = await channel.purge(limit=None, check=after_check)
        await interaction.followup.send(f"{len(deleted)} messages supprimés dans {channel.mention} après le message {message_id}.", ephemeral=True)
        logger.info(f"{interaction.user} a nettoyé {len(deleted)} messages dans {channel.name} après le message {message_id}.")

    @clean_group.command(name="image", description="Supprime tous les messages avec des images dans le salon.")
    @is_admin()
    @enqueue_request()
    async def clean_image(self, interaction: discord.Interaction):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send("Cette commande doit être utilisée dans un salon texte.", ephemeral=True)
        if not await self.ask_confirmation(interaction, f"Confirmez-vous la suppression de tous les messages avec images dans {channel.mention} ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)

        def image_check(m: discord.Message):
            if m.attachments:
                for att in m.attachments:
                    if att.content_type and att.content_type.startswith("image/"):
                        return True
            for e in m.embeds:
                if e.image or e.thumbnail:
                    return True
            return False

        deleted = await channel.purge(limit=None, check=image_check)
        await interaction.followup.send(f"{len(deleted)} messages avec images supprimés dans {channel.mention}.", ephemeral=True)
        logger.info(f"{interaction.user} a nettoyé {len(deleted)} messages avec images dans {channel.name}.")

    @clean_group.command(name="gif", description="Supprime tous les messages avec des gifs dans le salon.")
    @is_admin()
    @enqueue_request()
    async def clean_gif(self, interaction: discord.Interaction):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send("Cette commande doit être utilisée dans un salon texte.", ephemeral=True)
        if not await self.ask_confirmation(interaction, f"Confirmez-vous la suppression de tous les messages avec gifs dans {channel.mention} ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)

        def gif_check(m: discord.Message):
            if m.attachments:
                for att in m.attachments:
                    if att.content_type and "gif" in att.content_type:
                        return True
            if ".gif" in m.content.lower():
                return True
            for e in m.embeds:
                if e.image and e.image.url and e.image.url.lower().endswith('.gif'):
                    return True
            return False

        deleted = await channel.purge(limit=None, check=gif_check)
        await interaction.followup.send(f"{len(deleted)} messages avec gifs supprimés dans {channel.mention}.", ephemeral=True)
        logger.info(f"{interaction.user} a nettoyé {len(deleted)} messages avec gifs dans {channel.name}.")

    @clean_group.command(name="links", description="Supprime tous les messages contenant des liens dans le salon.")
    @is_admin()
    @enqueue_request()
    async def clean_links(self, interaction: discord.Interaction):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send("Cette commande doit être utilisée dans un salon texte.", ephemeral=True)
        if not await self.ask_confirmation(interaction, f"Confirmez-vous la suppression de tous les messages avec liens dans {channel.mention} ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)

        def links_check(m: discord.Message):
            if "http://" in m.content.lower() or "https://" in m.content.lower():
                return True
            return False

        deleted = await channel.purge(limit=None, check=links_check)
        await interaction.followup.send(f"{len(deleted)} messages avec liens supprimés dans {channel.mention}.", ephemeral=True)
        logger.info(f"{interaction.user} a nettoyé {len(deleted)} messages avec liens dans {channel.name}.")

    @clean_all.error
    @clean_user.error
    @clean_number.error
    @clean_from.error
    @clean_image.error
    @clean_gif.error
    @clean_links.error
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
