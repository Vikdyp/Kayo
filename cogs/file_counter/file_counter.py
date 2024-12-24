# cogs/file_counter/file_counter_cog.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional
from cogs.file_counter.services.file_counter_service import FileCounterService
from utils.request_manager import enqueue_request

logger = logging.getLogger("cogs.file_counter")

class CounterView(discord.ui.View):
    def __init__(self, guild_id: int, channel_id: int, message_id: int, ajouter_count: int, terminer_count: int):
        super().__init__(timeout=None)  # Persistent view
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.message_id = message_id
        self.ajouter_count = ajouter_count
        self.terminer_count = terminer_count

    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.green, custom_id="file_counter:ajouter")
    async def ajouter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild.id != self.guild_id:
            await interaction.response.send_message("Cette commande n'est pas autorisée dans ce serveur.", ephemeral=True)
            return

        updated = await FileCounterService.update_counts(self.guild_id, self.channel_id, ajouter=True)
        if updated:
            self.ajouter_count = updated['ajouter_count']
            self.terminer_count = updated['terminer_count']  # Mise à jour pour recalculer le pourcentage
            await self.update_embed(interaction)
        else:
            await interaction.response.send_message("Erreur lors de la mise à jour du compteur.", ephemeral=True)

    @discord.ui.button(label="Terminer", style=discord.ButtonStyle.blurple, custom_id="file_counter:terminer")
    async def terminer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild.id != self.guild_id:
            await interaction.response.send_message("Cette commande n'est pas autorisée dans ce serveur.", ephemeral=True)
            return

        updated = await FileCounterService.update_counts(self.guild_id, self.channel_id, terminer=True)
        if updated:
            self.ajouter_count = updated['ajouter_count']
            self.terminer_count = updated['terminer_count']
            await self.update_embed(interaction)
        else:
            await interaction.response.send_message("Erreur lors de la mise à jour du compteur.", ephemeral=True)

    async def update_embed(self, interaction: discord.Interaction):
        # Calcul du pourcentage de completion
        if self.ajouter_count > 0:
            percentage = (self.terminer_count / self.ajouter_count) * 100
            percentage = min(percentage, 100)  # Cap à 100%
            percentage = round(percentage, 1)  # Arrondi à une décimale
        else:
            percentage = 0

        embed = discord.Embed(
            title="Suivi des Fichiers",
            color=discord.Color.blue(),
            description=f"**Fichier total**: {self.ajouter_count}\n**Fichier terminer**: {self.terminer_count}\n**Pourcentage de completion**: {percentage}%"
        )
        try:
            channel = interaction.guild.get_channel(self.channel_id)
            if not channel:
                await interaction.response.send_message("Salon introuvable.", ephemeral=True)
                return

            message = await channel.fetch_message(self.message_id)
            await message.edit(embed=embed, view=self)
            await interaction.response.defer()
            logger.debug(f"Embed mis à jour pour le message ID {self.message_id}.")
        except discord.NotFound:
            await interaction.response.send_message("Le message n'a pas été trouvé.", ephemeral=True)
            logger.warning(f"Message ID {self.message_id} introuvable lors de la mise à jour.")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'embed: {e}")
            await interaction.response.send_message("Une erreur est survenue lors de la mise à jour.", ephemeral=True)

class FileCounterCog(commands.Cog):
    """Cog pour gérer le suivi des fichiers avec des boutons interactifs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.channel_id = 1136359641899614408  # Remplacez par votre ID de salon
        self.guild_id = None  # Sera défini lors du chargement du cog
        logger.info("FileCounterCog initialisé.")

    def cog_unload(self):
        """Déchargement du Cog."""
        logger.info("FileCounterCog déchargé.")
        # Vous pouvez ajouter ici des actions de nettoyage si nécessaire

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialisation lors du démarrage du bot."""
        logger.debug("FileCounterCog en cours d'initialisation.")

        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            logger.error(f"Salon avec l'ID {self.channel_id} introuvable.")
            return

        guild = channel.guild
        self.guild_id = guild.id

        # Récupérer les données du compteur depuis la base de données
        data = await FileCounterService.get_counter(self.guild_id, self.channel_id)
        if data:
            message_id = data['message_id']
            ajouter_count = data['ajouter_count']
            terminer_count = data['terminer_count']

            try:
                message = await channel.fetch_message(message_id)
                embed = discord.Embed(
                    title="Suivi des Fichiers",
                    color=discord.Color.blue(),
                    description=f"**Fichier total**: {ajouter_count}\n**Fichier terminer**: {terminer_count}\n**Pourcentage de completion**: {self.calculate_percentage(terminer_count, ajouter_count)}%"
                )
                view = CounterView(
                    guild_id=self.guild_id,
                    channel_id=self.channel_id,
                    message_id=message_id,
                    ajouter_count=ajouter_count,
                    terminer_count=terminer_count
                )
                await message.edit(embed=embed, view=view)
                self.bot.add_view(view)
                logger.info("Message de suivi existant retrouvé et mis à jour.")
            except discord.NotFound:
                logger.warning("Message de suivi non trouvé. Création d'un nouveau message.")
                message = await self.send_counter_message(channel)
                data['message_id'] = message.id
                await FileCounterService.create_counter(self.guild_id, self.channel_id, message.id)
                view = CounterView(
                    guild_id=self.guild_id,
                    channel_id=self.channel_id,
                    message_id=message.id,
                    ajouter_count=0,
                    terminer_count=0
                )
                self.bot.add_view(view)
        else:
            logger.info("Aucune configuration de compteur trouvée. Création d'un nouveau message.")
            message = await self.send_counter_message(channel)
            data = {
                "message_id": message.id,
                "ajouter_count": 0,
                "terminer_count": 0
            }
            await FileCounterService.create_counter(self.guild_id, self.channel_id, message.id)
            view = CounterView(
                guild_id=self.guild_id,
                channel_id=self.channel_id,
                message_id=message.id,
                ajouter_count=0,
                terminer_count=0
            )
            self.bot.add_view(view)

    async def send_counter_message(self, channel: discord.TextChannel) -> discord.Message:
        """Envoie un nouveau message de suivi avec les boutons."""
        embed = discord.Embed(
            title="Suivi des Fichiers",
            color=discord.Color.blue(),
            description="**Fichier total**: 0\n**Fichier terminer**: 0\n**Pourcentage de completion**: 0%"
        )
        view = CounterView(
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            message_id=0,  # Sera défini après l'envoi
            ajouter_count=0,
            terminer_count=0
        )
        message = await channel.send(embed=embed, view=view)
        logger.info(f"Nouveau message de suivi envoyé avec l'ID {message.id}.")
        return message

    @staticmethod
    def calculate_percentage(terminer_count: int, ajouter_count: int) -> float:
        """Calcule le pourcentage de completion."""
        if ajouter_count > 0:
            percentage = (terminer_count / ajouter_count) * 100
            percentage = min(percentage, 100)  # Cap à 100%
            percentage = round(percentage, 1)  # Arrondi à une décimale
            return percentage
        else:
            return 0.0

    @app_commands.command(name="init_counter", description="Initialise le compteur de fichiers.")
    @app_commands.checks.has_permissions(administrator=True)
    @enqueue_request()
    async def init_counter(self, interaction: discord.Interaction):
        """Commande pour initialiser ou réinitialiser le compteur."""
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            await interaction.followup.send("Salon introuvable.", ephemeral=True)
            return

        data = await FileCounterService.get_counter(self.guild_id, self.channel_id)
        if data and data['message_id']:
            try:
                message = await channel.fetch_message(data['message_id'])
                await message.delete()
                logger.info("Message de suivi supprimé lors de la réinitialisation.")
            except discord.NotFound:
                logger.warning("Message de suivi non trouvé lors de la réinitialisation.")

        message = await self.send_counter_message(channel)
        if data:
            data['message_id'] = message.id
            data['ajouter_count'] = 0
            data['terminer_count'] = 0
            # Mise à jour des compteurs à zéro
            await FileCounterService.update_counts(self.guild_id, self.channel_id, ajouter=False, terminer=False)
        else:
            data = {
                "message_id": message.id,
                "ajouter_count": 0,
                "terminer_count": 0
            }
            await FileCounterService.create_counter(self.guild_id, self.channel_id, message.id)

        embed = discord.Embed(
            title="Suivi des Fichiers",
            color=discord.Color.blue(),
            description="**Fichier total**: 0\n**Fichier terminer**: 0\n**Pourcentage de completion**: 0%"
        )
        view = CounterView(
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            message_id=message.id,
            ajouter_count=0,
            terminer_count=0
        )
        await message.edit(embed=embed, view=view)
        self.bot.add_view(view)

        await interaction.followup.send("Le compteur a été initialisé avec succès.", ephemeral=True)

    @init_counter.error
    async def init_counter_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.followup.send("Vous n'avez pas les permissions nécessaires pour utiliser cette commande.", ephemeral=True)
        else:
            logger.error(f"Erreur dans la commande init_counter: {error}")
            await interaction.followup.send("Une erreur est survenue lors de l'exécution de la commande.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(FileCounterCog(bot))
    logger.info("FileCounterCog chargé avec succès.")
