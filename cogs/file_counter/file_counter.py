import discord
from discord.ext import commands
import logging
from typing import Optional
from cogs.file_counter.services.file_counter_service import FileCounterService

logger = logging.getLogger("cogs.file_counter")

class CounterView(discord.ui.View):
    def __init__(self, server_db_id: int, channel_id: int, message_id: int, ajouter_count: int, terminer_count: int):
        super().__init__(timeout=None)  # Persistent view
        self.server_db_id = server_db_id
        self.channel_id = channel_id
        self.message_id = message_id
        self.ajouter_count = ajouter_count
        self.terminer_count = terminer_count

    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.green, custom_id="file_counter:ajouter")
    async def ajouter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Vérifier que l'Interaction vient du bon serveur
        if interaction.guild is None:
            await interaction.response.send_message("Cette interaction ne peut être utilisée que sur un serveur.", ephemeral=True)
            return

        # On vérifie que le server_db_id correspond au serveur actuel
        # Ce n'est pas strictement nécessaire si tu n'héberges qu'un seul message par guild
        # Sinon, on pourrait aussi stocker l'ID discord brut et vérifier.
        # Pour simplifier, on omet la vérification.

        await interaction.response.defer(thinking=True)
        updated = await FileCounterService.update_counts(self.server_db_id, self.channel_id, ajouter=True)
        if updated:
            self.ajouter_count = updated['ajouter_count']
            self.terminer_count = updated['terminer_count']
            await self.update_embed(interaction)
        else:
            await interaction.response.send_message("Erreur lors de la mise à jour du compteur.", ephemeral=True)

    @discord.ui.button(label="Terminer", style=discord.ButtonStyle.blurple, custom_id="file_counter:terminer")
    async def terminer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            await interaction.response.send_message("Cette interaction ne peut être utilisée que sur un serveur.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        updated = await FileCounterService.update_counts(self.server_db_id, self.channel_id, terminer=True)
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
            description=(
                f"**Fichier total**: {self.ajouter_count}\n"
                f"**Fichier terminer**: {self.terminer_count}\n"
                f"**Pourcentage de completion**: {percentage}%"
            )
        )
        try:
            channel = interaction.guild.get_channel(self.channel_id)
            if not channel:
                await interaction.response.send_message("Salon introuvable.", ephemeral=True)
                return

            message = await channel.fetch_message(self.message_id)
            await message.edit(embed=embed, view=self)
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
        self.channel_id = 1136359641899614408  # Remplace par l'ID de ton salon
        self.server_db_id: Optional[int] = None  # ID interne (table serveur_id)
        logger.info("FileCounterCog initialisé.")

    def cog_unload(self):
        """Déchargement du Cog."""
        logger.info("FileCounterCog déchargé.")

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialisation lors du démarrage du bot."""
        logger.debug("FileCounterCog en cours d'initialisation.")

        # Récupérer le salon
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            logger.error(f"Salon avec l'ID {self.channel_id} introuvable.")
            return

        guild = channel.guild
        if not guild:
            logger.error("Impossible de récupérer la guilde à partir de ce salon.")
            return

        # 1) On convertit le guild.id Discord → server_db_id
        server_db_id = await FileCounterService.get_or_create_server_record(guild.id, guild.name)
        if not server_db_id:
            logger.error("Impossible de créer/récupérer server_db_id pour ce guild.")
            return
        self.server_db_id = server_db_id

        # 2) Récupérer les données du compteur depuis la base de données
        data = await FileCounterService.get_counter(self.server_db_id, self.channel_id)
        if data:
            message_id = data['message_id']
            ajouter_count = data['ajouter_count']
            terminer_count = data['terminer_count']

            try:
                message = await channel.fetch_message(message_id)
                embed = self.create_embed(ajouter_count, terminer_count)
                view = CounterView(
                    server_db_id=self.server_db_id,
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
                message = await self.send_counter_message(channel, 0, 0)
                data['message_id'] = message.id
                await FileCounterService.create_counter(self.server_db_id, self.channel_id, message.id)
        else:
            logger.info("Aucune configuration de compteur trouvée. Création d'un nouveau message.")
            message = await self.send_counter_message(channel, 0, 0)
            await FileCounterService.create_counter(self.server_db_id, self.channel_id, message.id)

    @commands.command(name="init_counter")
    @commands.has_permissions(administrator=True)
    async def init_counter(self, ctx: commands.Context):
        """
        Commande préfixe pour initialiser ou réinitialiser le compteur de fichiers.
        Utilisation: `!init_counter`
        """
        if not self.server_db_id:
            # Créer/récupérer le server_db_id si jamais le on_ready n'a pas encore tourné
            server_db_id = await FileCounterService.get_or_create_server_record(ctx.guild.id, ctx.guild.name)
            if not server_db_id:
                await ctx.send("Impossible de configurer le compteur (server_db_id non trouvé).", delete_after=10)
                return
            self.server_db_id = server_db_id

        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            await ctx.send("Salon introuvable.", delete_after=10)
            return

        data = await FileCounterService.get_counter(self.server_db_id, self.channel_id)
        if data and data['message_id']:
            try:
                old_msg = await channel.fetch_message(data['message_id'])
                await old_msg.delete()
                logger.info("Ancien message de suivi supprimé lors de la réinitialisation.")
            except discord.NotFound:
                logger.warning("Ancien message de suivi non trouvé lors de la réinitialisation.")

        # Envoie un nouveau message
        message = await self.send_counter_message(channel, 0, 0)

        # Si le compteur existe déjà en DB, on reset
        if data:
            await FileCounterService.reset_counter(self.server_db_id, self.channel_id, message.id)
        else:
            # Sinon on crée un nouvel enregistrement
            await FileCounterService.create_counter(self.server_db_id, self.channel_id, message.id)

        await ctx.send("Le compteur a été réinitialisé avec succès.", delete_after=10)

    async def send_counter_message(self, channel: discord.TextChannel, ajouter_count: int, terminer_count: int) -> discord.Message:
        """Envoie un nouveau message de suivi avec les boutons."""
        embed = self.create_embed(ajouter_count, terminer_count)
        view = CounterView(
            server_db_id=self.server_db_id,
            channel_id=self.channel_id,
            message_id=0,  # Sera défini après l'envoi
            ajouter_count=ajouter_count,
            terminer_count=terminer_count
        )
        message = await channel.send(embed=embed, view=view)
        logger.info(f"Nouveau message de suivi envoyé avec l'ID {message.id}.")

        # Met à jour la View après avoir récupéré le message_id
        view.message_id = message.id
        self.bot.add_view(view)

        return message

    def create_embed(self, ajouter_count: int, terminer_count: int) -> discord.Embed:
        """Crée l'embed de suivi."""
        percentage = self.calculate_percentage(terminer_count, ajouter_count)
        embed = discord.Embed(
            title="Suivi des Fichiers",
            color=discord.Color.blue(),
            description=(
                f"**Fichier total**: {ajouter_count}\n"
                f"**Fichier terminer**: {terminer_count}\n"
                f"**Pourcentage de completion**: {percentage}%"
            )
        )
        return embed

    @staticmethod
    def calculate_percentage(terminer_count: int, ajouter_count: int) -> float:
        """Calcule le pourcentage de completion."""
        if ajouter_count > 0:
            percentage = (terminer_count / ajouter_count) * 100
            percentage = min(percentage, 100)
            percentage = round(percentage, 1)
            return percentage
        else:
            return 0.0

async def setup(bot: commands.Bot):
    await bot.add_cog(FileCounterCog(bot))
    logger.info("FileCounterCog chargé avec succès.")
