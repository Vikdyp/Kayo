#cogs\other\vocal_creator.py
import asyncio
from discord.ext import commands, tasks
import discord
from cogs.other.service.vocal_services import save_persistent_message, get_persistent_message
import logging

logger = logging.getLogger("vocal.creator")

# ID de la catégorie hardcodée pour les salons vocaux temporaires
TEMP_VOCAL_CATEGORY_ID = 1328538201668980878
# Temps d'inactivité avant suppression en secondes (5 minutes)
IDLE_TIMEOUT = 5 * 60

class TempVoiceChannelButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Créer un salon vocal", style=discord.ButtonStyle.green, custom_id="create_temp_vc")
    async def create_temp_vc(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        # Vérifier si l'utilisateur possède déjà un salon temporaire
        for channel in guild.voice_channels:
            if channel.name == f"Salon de {user.name}":
                await interaction.response.send_message("Tu as déjà un salon vocal temporaire.", ephemeral=True)
                return

        # Récupérer la catégorie définie
        category = guild.get_channel(TEMP_VOCAL_CATEGORY_ID)
        if category is None:
            await interaction.response.send_message("La catégorie pour les salons vocaux temporaires n'existe pas.", ephemeral=True)
            return

        # Créer le salon vocal temporaire
        temp_channel = await guild.create_voice_channel(name=f"Salon de {user.name}", category=category)
        link = f"https://discord.com/channels/{guild.id}/{temp_channel.id}"
        await interaction.response.send_message(f"Ton salon vocal a été créé : {link}", ephemeral=True)

class VocalCreatorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Dictionnaire pour suivre les tâches de suppression des salons vides
        self.deletion_tasks = {}
        # Message persistant pour la création des salons vocaux
        self.persistent_message = None
        # Démarrage de la tâche de vérification périodique
        self.voice_check_loop.start()
        # Chargement/réattachement du message persistant au démarrage du bot
        self.bot.loop.create_task(self.load_persistent_message())

    def cog_unload(self):
        self.voice_check_loop.cancel()

    async def load_persistent_message(self):
        """
        Récupère le message persistant depuis la base et réattache la vue pour que le bouton reste interactif.
        """
        await self.bot.wait_until_ready()
        # Pour chaque guild, on tente de récupérer le message persistant pour 'vocal_creation'
        for guild in self.bot.guilds:
            result = await get_persistent_message(guild.id, "vocal_creation")
            if result:
                channel_id, message_id = result
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        msg = await channel.fetch_message(message_id)
                        self.persistent_message = msg
                        await msg.edit(view=TempVoiceChannelButton())
                        logger.info(f"Réattachement de la vue sur le message persistant pour guild {guild.id}.")
                    except Exception as e:
                        logger.error(f"Erreur lors du chargement du message persistant pour guild {guild.id}: {e}")

    @commands.command(name="set_vocal")
    @commands.has_permissions(administrator=True)
    async def set_vocal(self, ctx: commands.Context):
        """
        Envoie un embed contenant le bouton de création de salon vocal temporaire,
        et sauvegarde ce message dans la BDD pour persistance.
        """
        embed = discord.Embed(
            title="Création de Salon Vocal Temporaire",
            description="Clique sur le bouton ci-dessous pour créer un salon vocal temporaire."
        )
        view = TempVoiceChannelButton()
        message = await ctx.send(embed=embed, view=view)

        # Sauvegarde du message persistant dans la BDD
        await save_persistent_message(
            ctx.guild.id,
            "vocal_creation",
            message.channel.id,
            message.id,
            requester_id=None
        )
        await ctx.send("Embed de création de salon vocal envoyé et sauvegardé.", delete_after=10)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """
        Surveille les changements d'état dans les salons vocaux temporaires pour programmer leur suppression
        lorsque le salon devient vide, ou pour annuler la suppression si quelqu'un rejoint.
        """
        channel = before.channel
        if channel and channel.category and channel.category.id == TEMP_VOCAL_CATEGORY_ID:
            if len(channel.members) == 0:
                if channel.id not in self.deletion_tasks:
                    self.deletion_tasks[channel.id] = self.bot.loop.create_task(self.schedule_deletion(channel))
            else:
                if channel.id in self.deletion_tasks:
                    task = self.deletion_tasks.pop(channel.id)
                    task.cancel()

    async def schedule_deletion(self, channel: discord.VoiceChannel):
        """
        Attend IDLE_TIMEOUT secondes, puis supprime le salon s'il est toujours vide.
        """
        try:
            await asyncio.sleep(IDLE_TIMEOUT)
            if len(channel.members) == 0:
                await channel.delete(reason="Salon vocal temporaire inactif depuis plus de 5 minutes.")
                logger.info(f"Salon {channel.id} supprimé pour inactivité.")
        except asyncio.CancelledError:
            logger.info(f"Suppression du salon {channel.id} annulée.")
        finally:
            self.deletion_tasks.pop(channel.id, None)

    @tasks.loop(minutes=1)
    async def voice_check_loop(self):
        """
        Tâche périodique qui parcourt les salons vocaux temporaires pour s'assurer que
        ceux-ci soient supprimés en cas d'inactivité prolongée.
        """
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                if channel.category and channel.category.id == TEMP_VOCAL_CATEGORY_ID:
                    if len(channel.members) == 0 and channel.id not in self.deletion_tasks:
                        self.deletion_tasks[channel.id] = self.bot.loop.create_task(self.schedule_deletion(channel))
                    elif len(channel.members) > 0 and channel.id in self.deletion_tasks:
                        task = self.deletion_tasks.pop(channel.id)
                        task.cancel()

    @voice_check_loop.before_loop
    async def before_voice_check_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(VocalCreatorCog(bot))
