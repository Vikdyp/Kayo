import discord
from discord.ext import commands
import re  # Utilisé pour détecter les messages se terminant par "quoi"
import random  # Utilisé pour choisir une réponse aléatoire
import asyncio
import time  # Utilisé pour obtenir l'horodatage actuel

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
        self.special_probability = 0.00000001  # Probabilité

        # Paramètres de rate limiting
        self.max_responses_per_user = 5  # Nombre maximal de réponses autorisées
        self.time_window = 60  # Intervalle de temps en secondes

        # Dictionnaire pour suivre les interactions des utilisateurs
        self.user_quoi_timestamps = {}
        # Lock pour gérer l'accès concurrent au dictionnaire
        self.lock = asyncio.Lock()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Événement déclenché lorsqu'un message est envoyé."""
        # Ignorer les messages du bot pour éviter les boucles
        if message.author.bot:
            return

        # Vérifie si le message se termine par "quoi" (insensible à la casse)
        if re.search(r'\bquoi\s*\?*$', message.content, re.IGNORECASE):
            current_time = time.time()
            user_id = message.author.id

            async with self.lock:
                timestamps = self.user_quoi_timestamps.get(user_id, [])

                # Filtrer les horodatages obsolètes
                timestamps = [timestamp for timestamp in timestamps if current_time - timestamp < self.time_window]

                if len(timestamps) >= self.max_responses_per_user:
                    # Limite atteinte, ne pas répondre
                    return
                else:
                    # Ajouter l'horodatage actuel
                    timestamps.append(current_time)
                    self.user_quoi_timestamps[user_id] = timestamps

            # Choisir une réponse aléatoire ou spéciale
            if random.random() < self.special_probability:
                response = self.special_response  # Utilise la phrase spéciale selon la probabilité
            else:
                response = random.choice(self.responses)  # Choisit une réponse aléatoire

            await message.channel.send(response)

    async def cog_unload(self):
        """Nettoie les tâches lors du déchargement du cog."""
        self.user_quoi_timestamps.clear()

async def setup(bot: commands.Bot):
    await bot.add_cog(QuoiResponder(bot))
