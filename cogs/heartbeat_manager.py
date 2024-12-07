import discord
from discord.ext import commands, tasks
import random

class HeartbeatManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.heartbeat_channel_id = 1237197721090392164  # Remplacez avec votre ID de salon
        self.heartbeat_loop.start()  # Démarrer la tâche automatique

    @tasks.loop(minutes=1)
    async def heartbeat_loop(self):
        """Envoyer des messages réguliers dans un salon spécifique pour maintenir l'activité"""
        channel = self.bot.get_channel(self.heartbeat_channel_id)
        if channel:
            try:
                message = await channel.send("Le bot est toujours actif !")
                await message.delete(delay=300)  # Supprimer le message après 5 minutes (300 secondes)
            except discord.Forbidden:
                print(f"Permission refusée pour envoyer un message dans {channel.name}")
            except discord.HTTPException as e:
                print(f"Erreur HTTP lors de l'envoi du message : {e}")

        # Générer un délai aléatoire entre 1 minute et 4 minutes
        delay_seconds = random.randint(60, 240)
        await self.heartbeat_loop.change_interval(seconds=delay_seconds)

    @heartbeat_loop.before_loop
    async def before_heartbeat_loop(self):
        await self.bot.wait_until_ready()  # Attendre que le bot soit prêt

async def setup(bot):
    await bot.add_cog(HeartbeatManager(bot))
