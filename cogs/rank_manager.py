import discord
from discord.ext import commands
from discord import app_commands
import requests
import json
import os
import re
from urllib.parse import unquote

class RankManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.valorant_api_key = os.getenv("TRACKER_API_KEY")
        self.user_data_file = 'user_data.json'
        self.load_user_data()

    def load_user_data(self):
        print("Chargement des données utilisateur...")
        if not os.path.exists(self.user_data_file) or os.stat(self.user_data_file).st_size == 0:
            print("Le fichier user_data.json n'existe pas ou est vide. Initialisation avec des données vides.")
            self.user_data = {}
            self.save_user_data()
        else:
            with open(self.user_data_file, 'r') as f:
                try:
                    self.user_data = json.load(f)
                    print("Données utilisateur chargées avec succès.")
                except json.JSONDecodeError:
                    print("Erreur de décodage JSON. Initialisation avec des données vides.")
                    self.user_data = {}
                    self.save_user_data()

    def save_user_data(self):
        with open(self.user_data_file, 'w') as f:
            json.dump(self.user_data, f, indent=4)
        print("Données utilisateur sauvegardées avec succès.")

    def find_user_by_valorant_name(self, valorant_username):
        for user_id, username in self.user_data.items():
            if username == valorant_username:
                return user_id
        return None

    async def assign_rank_role(self, member, valorant_username):
        url = f"https://public-api.tracker.gg/v2/valorant/standard/profile/riot/{valorant_username}"
        headers = {
            'TRN-Api-Key': self.valorant_api_key,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        print(f"Fetching rank data for {valorant_username} from {url}")
        try:
            response = requests.get(url, headers=headers)
            print(f"API response status: {response.status_code}")
            print(f"API response text: {response.text}")

            if response.status_code != 200 or not response.text:
                print(f"Erreur lors de la récupération du rang pour {valorant_username}: Status Code {response.status_code}, Response: {response.text}")
                return

            if response.headers.get('Content-Type').startswith('text/html'):
                print("La réponse de l'API est en HTML, vérifiez votre clé API et les permissions.")
                return

            data = response.json()
            print(f"API response JSON: {data}")

            try:
                rank = data['data']['segments'][0]['stats']['rank']['metadata']['tierName']
                role_name = f"Valorant {rank}"
                guild = member.guild
                role = discord.utils.get(guild.roles, name=role_name)

                if role:
                    await member.add_roles(role)
                    print(f"Rôle {role_name} attribué à {member.name}.")
                else:
                    print(f"Le rôle {role_name} n'existe pas dans ce serveur.")
            except (KeyError, IndexError) as e:
                print(f"Erreur lors de l'extraction du rang pour {valorant_username}: {e}")

        except requests.exceptions.RequestException as e:
            print(f"Erreur lors de la requête à l'API tracker.gg: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Connecté en tant que {self.bot.user}')
        await self.bot.tree.sync()
        print("Commandes slash synchronisées avec succès.")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        print(f'Nouveau membre: {member.name}')
        if str(member.id) not in self.user_data:
            await self.prompt_link_valorant(member)

    async def prompt_link_valorant(self, member):
        try:
            await member.send("Bienvenue ! Pour accéder à ce serveur, veuillez lier votre compte Valorant en utilisant la commande `/link_valorant <valorant_tracker_url>`.")
            print(f"Message envoyé à {member.name} pour lier le compte Valorant.")
        except discord.Forbidden:
            print(f"Impossible d'envoyer un message à {member.name}.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        print(f"Mise à jour de l'état vocal pour {member.name}.")
        user_id = str(member.id)
        if user_id in self.user_data:
            valorant_username = self.user_data[user_id]
            print(f"User {member.name} is linked to Valorant account {valorant_username}. Updating rank role.")
            await self.assign_rank_role(member, valorant_username)
        else:
            print(f"User {member.name} is not linked to a Valorant account.")

    def extract_valorant_username(self, tracker_url):
        decoded_url = unquote(tracker_url)
        match = re.search(r'riot/([^/]+)/overview', decoded_url)
        if match:
            return match.group(1)
        else:
            return None

    @app_commands.command(name="link_valorant", description="Lier un compte Valorant à votre compte Discord en utilisant l'URL tracker.gg")
    async def link_valorant(self, interaction: discord.Interaction, tracker_url: str):
        valorant_username = self.extract_valorant_username(tracker_url)
        if not valorant_username:
            await interaction.response.send_message("URL invalide. Veuillez fournir une URL valide de tracker.gg.", ephemeral=True)
            return

        print(f"Demande de liaison de compte Valorant reçue: {valorant_username}")
        discord_user_id = str(interaction.user.id)
        existing_user_id = self.find_user_by_valorant_name(valorant_username)

        if existing_user_id and existing_user_id != discord_user_id:
            print(f"Conflit détecté pour le pseudo Valorant {valorant_username} entre {discord_user_id} et {existing_user_id}.")
            conflict_channel = self.bot.get_channel(self.conflict_channel_id)
            if conflict_channel:
                await conflict_channel.send(
                    f"Conflit détecté pour le pseudo Valorant `{valorant_username}` entre <@{discord_user_id}> et <@{existing_user_id}>. "
                    f"Réagissez à ce message pour initier la vérification."
                )
            await interaction.response.send_message(
                "Ce pseudo Valorant est déjà lié à un autre compte. Un conflit a été détecté et est en cours de traitement.",
                ephemeral=True
            )
        else:
            self.user_data[discord_user_id] = valorant_username
            self.save_user_data()
            print(f"Compte Valorant {valorant_username} lié avec succès à {discord_user_id}.")
            try:
                valorant_nickname = valorant_username.split('#')[0]
                await interaction.user.edit(nick=valorant_nickname)
                await self.assign_rank_role(interaction.user, valorant_username)
                await interaction.response.send_message(f"Compte Valorant `{valorant_username}` lié avec succès et nom d'utilisateur mis à jour.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("Le bot n'a pas les permissions nécessaires pour changer votre pseudo. Veuillez contacter un administrateur.", ephemeral=True)

    async def resolve_conflict(self, user1_id, user2_id, valorant_username):
        print(f"Résolution de conflit pour le pseudo Valorant {valorant_username} entre {user1_id} et {user2_id}.")
        guild = self.bot.get_guild(self.bot.guilds[0].id)
        category = await guild.create_category("Conflit Valorant")
        channel = await guild.create_text_channel(f"conflit-{valorant_username}", category=category)

        await channel.send(f"<@{user1_id}> et <@{user2_id}>, merci de prouver que `{valorant_username}` est votre compte Valorant.")
        await channel.set_permissions(guild.default_role, read_messages=False, send_messages=False)
        await channel.set_permissions(guild.get_member(user1_id), read_messages=True, send_messages=True)
        await channel.set_permissions(guild.get_member(user2_id), read_messages=True, send_messages=True)

    async def send_conflict_resolution_message(self, user1_id, user2_id, valorant_username):
        conflict_channel = self.bot.get_channel(self.conflict_channel_id)
        if conflict_channel:
            message = await conflict_channel.send(
                f"Conflit détecté pour le pseudo Valorant `{valorant_username}` entre <@{user1_id}> et <@{user2_id}>. "
                "Les modérateurs peuvent cliquer sur les réactions pour choisir qui conserve le pseudo."
            )
            await message.add_reaction("✅")
            await message.add_reaction("❌")
            self.bot.add_listener(self.on_reaction_add)

    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return
        if reaction.message.channel.id == self.conflict_channel_id:
            if reaction.emoji == "✅":
                pass
            elif reaction.emoji == "❌":
                pass

async def setup(bot):
    print("Ajout du cog RankManager...")
    await bot.add_cog(RankManager(bot))
    print("Ajout des commandes slash...")
    rank_manager = bot.get_cog("RankManager")
    if rank_manager:
        try:
            bot.tree.add_command(rank_manager.link_valorant)
        except discord.app_commands.CommandAlreadyRegistered:
            print("Commande 'link_valorant' déjà enregistrée.")
    else:
        print("Erreur : Le cog RankManager n'a pas été trouvé.")
    print("Configuration terminée.")
