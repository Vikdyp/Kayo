import discord
from discord.ext import commands
from discord import app_commands
import logging
import re  # Pour détecter les messages se terminant par "quoi"
import random  # Pour choisir une réponse aléatoire
import asyncio
import time  # Pour obtenir l'horodatage actuel
from utils.database import database  # On suppose que ce module fournit execute() et fetch() pour interagir avec la BDD
from cogs.configuration.services.role_service import ServerRoleService

TOP3_ROLE_ID = 1236427596128976906  # ID du rôle top 3
TOP3_ROLE_ACTION = "quoicoubeh_top3"

class QuoiResponder(commands.Cog):
    """Cog pour répondre automatiquement aux messages se terminant par 'quoi'
       et enregistrer le nombre de déclenchements par utilisateur."""
       
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

    async def get_internal_server_id(self, guild: discord.Guild) -> int:
        await database.ensure_connected()
        query = "SELECT id FROM serveur_id WHERE guild_id = $1;"
        internal_id = await database.fetchval(query, guild.id)
        if not internal_id:
            logger = logging.getLogger("quoicoubeh")
            logger.error(f"Serveur non trouve pour guild_id {guild.id}.")
        return internal_id

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

            # Recherche de l'emoji personnalisé "pepe_clown" dans le serveur
            emoji_obj = discord.utils.get(message.guild.emojis, name="pepe_clown")
            if emoji_obj:
                response += " " + str(emoji_obj)
            else:
                response += " :pepe_clown:"  # Fallback en cas d'absence de l'emoji personnalisé

            await message.channel.send(response)

            # Incrémenter le compteur dans la base de données pour cet utilisateur
            try:
                server_id = await self.get_internal_server_id(message.guild)
                if not server_id:
                    return
                query = """
                INSERT INTO quoi_responses (user_id, trigger_count, last_triggered, server_id)
                VALUES ($1, 1, NOW(), $2)
                ON CONFLICT (user_id, server_id)
                DO UPDATE SET trigger_count = quoi_responses.trigger_count + 1, last_triggered = NOW();
                """
                await database.execute(query, message.author.id, server_id)
            except Exception as e:
                print(f"Erreur lors de la mise à jour du compteur: {e}")

    @app_commands.command(name="quoiclassement", description="Affiche le classement des membres ayant déclenché le 'quoi' le plus souvent.")
    async def quoiclassement(self, interaction: discord.Interaction):
        """
        Commande slash qui affiche les 10 membres ayant déclenché le QuoiResponder le plus souvent.
        Chaque utilisateur est mentionné et les 1er, 2ème et 3ème places affichent un emoji (🥇, 🥈, 🥉).
        Le texte "- déclenchements" est remplacé par "- quoicoubeh".
        De plus, le rôle top 3 (ID 1236427596128976906) est attribué aux trois premiers et retiré aux autres.
        """
        try:
            server_id = await self.get_internal_server_id(interaction.guild)
            if not server_id:
                await interaction.response.send_message("Serveur introuvable.", ephemeral=True)
                return
            query = """
            SELECT user_id, trigger_count
            FROM quoi_responses
            WHERE server_id = $1
            ORDER BY trigger_count DESC
            LIMIT 10;
            """
            rows = await database.fetch(query, server_id)
            if not rows:
                await interaction.response.send_message("Aucune donnée disponible.", ephemeral=True)
                return

            description = ""
            medal_emojis = ["🥇", "🥈", "🥉"]
            # Extraire les user_id des top 3
            top3_ids = set(row["user_id"] for row in rows[:3])
            for idx, row in enumerate(rows, start=1):
                user_mention = f"<@{row['user_id']}>"
                medal = medal_emojis[idx - 1] if idx <= 3 else ""
                description += f"{medal} **{idx}. {user_mention}** - {row['trigger_count']} quoicoubeh\n"
            embed = discord.Embed(
                title="Classement Quoi",
                description=description,
                color=discord.Color.blurple()
            )

            # Mise à jour du rôle top 3 dans la guilde
            guild = interaction.guild
            roles_config = await ServerRoleService.get_roles_config(guild.id, guild.name)
            top3_role_id = roles_config.get(TOP3_ROLE_ACTION) if roles_config else None
            top3_role = guild.get_role(top3_role_id) if top3_role_id else None
            if top3_role is not None:
                # Pour chaque membre possédant le rôle mais qui n'est plus dans le top 3, le retirer
                for member in top3_role.members:
                    if member.id not in top3_ids:
                        try:
                            await member.remove_roles(top3_role, reason="Falling out of top 3 quoicoubeh")
                        except Exception as e:
                            print(f"Erreur lors de la suppression du rôle top3 pour {member}: {e}")
                # Pour chaque membre du top 3, s'il ne possède pas encore le rôle, l'ajouter
                for user_id in top3_ids:
                    member = guild.get_member(user_id)
                    if member and top3_role not in member.roles:
                        try:
                            await member.add_roles(top3_role, reason="Entering top 3 quoicoubeh")
                        except Exception as e:
                            print(f"Erreur lors de l'ajout du rôle top3 pour {member}: {e}")
            else:
                print("Rôle top 3 non trouvé dans la guilde.")

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message("Erreur lors de la récupération du classement.", ephemeral=True)
            print(f"Erreur dans /quoiclassement: {e}")

    async def cog_unload(self):
        """Nettoie les tâches lors du déchargement du cog."""
        self.user_quoi_timestamps.clear()

async def setup(bot: commands.Bot):
    await bot.add_cog(QuoiResponder(bot))
