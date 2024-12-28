import discord
from discord.ext import commands
import re  # Utilisé pour détecter les messages se terminant par "quoi"
import random  # Utilisé pour choisir une réponse aléatoire

class QuoiResponder(commands.Cog):
    """Cog pour répondre automatiquement aux messages se terminant par 'quoi'."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Liste de jeux de mots comme réponses
        self.responses = [
            "feur !",
            "coubeh !",
            "de neuf ?",
            "de beau ?"
        ]
        # Phrase spéciale avec une probabilité réglable
        self.special_response = f"easter egg ! contact <@{812367371570118756}>"
        self.special_probability = 1  # Probabilité

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Événement déclenché lorsqu'un message est envoyé."""
        # Ignorer les messages du bot pour éviter les boucles
        if message.author.bot:
            return

        # Vérifie si le message se termine par "quoi" (insensible à la casse)
        if re.search(r'\bquoi\s*\?*$', message.content, re.IGNORECASE):
            if random.random() < self.special_probability:
                response = self.special_response  # Utilise la phrase spéciale selon la probabilité
            else:
                response = random.choice(self.responses)  # Choisit une réponse aléatoire
            await message.channel.send(response)

async def setup(bot: commands.Bot):
    await bot.add_cog(QuoiResponder(bot))
