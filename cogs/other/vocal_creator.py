# cogs/other/vocal_creator.py

import asyncio
import logging
from discord.ext import commands, tasks
import discord

logger = logging.getLogger("vocal.creator")

# ID de la catégorie pour les salons vocaux temporaires
TEMP_VOCAL_CATEGORY_ID = 1328538201668980878
# ID du salon "lobby" que l'on rejoint pour créer un VC
LOBBY_CHANNEL_ID = 1384590000825303111
# Temps d'inactivité avant suppression en secondes (5 minutes)
IDLE_TIMEOUT = 5 * 60


class VocalCreatorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.deletion_tasks = {}
        self.voice_check_loop.start()

    def cog_unload(self):
        self.voice_check_loop.cancel()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState,
                                    after: discord.VoiceState):
        # 1) Création d'un nouveau salon à chaque entrée dans le lobby
        if after.channel and after.channel.id == LOBBY_CHANNEL_ID:
            guild = member.guild
            # Préparer le nom exact avec display_name
            channel_name = f"Salon de {member.display_name}"

            # Supprimer tout ancien salon vide du même nom
            for vc in list(guild.voice_channels):
                if (
                    vc.name == channel_name
                    and vc.category
                    and vc.category.id == TEMP_VOCAL_CATEGORY_ID
                    and len(vc.members) == 0
                ):
                    try:
                        await vc.delete()
                    except Exception as e:
                        logger.error(f"Erreur suppression salon vide {vc.id}: {e}")

            # Création du nouveau salon
            category = guild.get_channel(TEMP_VOCAL_CATEGORY_ID)
            if category is None:
                logger.error(f"Catégorie temporaire {TEMP_VOCAL_CATEGORY_ID} introuvable.")
                return

            new_vc = await guild.create_voice_channel(
                name=channel_name,
                category=category
            )
            # Déplacer l'utilisateur immédiatement
            await member.move_to(new_vc)

            # Planifier la suppression après inactivité
            self.deletion_tasks[new_vc.id] = self.bot.loop.create_task(
                self.schedule_deletion(new_vc)
            )

        # 2) Gestion de la suppression automatique pour tous les salons temporaires
        channel_before = before.channel
        if (channel_before
                and channel_before.category
                and channel_before.category.id == TEMP_VOCAL_CATEGORY_ID):
            if len(channel_before.members) == 0:
                if channel_before.id not in self.deletion_tasks:
                    self.deletion_tasks[channel_before.id] = \
                        self.bot.loop.create_task(self.schedule_deletion(channel_before))
            else:
                if channel_before.id in self.deletion_tasks:
                    task = self.deletion_tasks.pop(channel_before.id)
                    task.cancel()

    async def schedule_deletion(self, channel: discord.VoiceChannel):
        """
        Attend IDLE_TIMEOUT secondes, puis supprime le salon s'il est toujours vide.
        """
        try:
            await asyncio.sleep(IDLE_TIMEOUT)
            if len(channel.members) == 0:
                await channel.delete()
                logger.info(f"Salon temporaire {channel.id} supprimé après inactivité.")
        except asyncio.CancelledError:
            logger.info(f"Suppression du salon {channel.id} annulée.")
        finally:
            self.deletion_tasks.pop(channel.id, None)

    @tasks.loop(minutes=1)
    async def voice_check_loop(self):
        """
        Tâche périodique pour s'assurer de supprimer les salons vides
        et annuler les suppressions si nécessaire.
        """
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                if channel.category and channel.category.id == TEMP_VOCAL_CATEGORY_ID:
                    if len(channel.members) == 0 and channel.id not in self.deletion_tasks:
                        self.deletion_tasks[channel.id] = self.bot.loop.create_task(
                            self.schedule_deletion(channel)
                        )
                    elif len(channel.members) > 0 and channel.id in self.deletion_tasks:
                        task = self.deletion_tasks.pop(channel.id)
                        task.cancel()

    @voice_check_loop.before_loop
    async def before_voice_check_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(VocalCreatorCog(bot))
