import discord
from discord.ext import commands, tasks
from discord import app_commands
from cogs.utils import load_json, save_json
from datetime import datetime, timedelta

ALLOWED_CHANNEL_ID = 1136335372423528458
VOTE_CHANNEL_ID = 1136364046430523502
SCRIMS_CATEGORY_ID = 1243609102685573261

SAVE_FILE = "scrims_data.json"
WINS_FILE = "wins_data.json"
WARNINGS_FILE = "warnings_data.json"

class ScrimsManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players_by_rank = {
            "Fer": [],
            "Bronze": [],
            "Argent": [],
            "Or": [],
            "Platine": [],
            "Diamant": [],
            "Ascendant": [],
            "Immortel": [],
            "Radiant": []
        }
        self.messages_by_rank = {
            "Fer": [],
            "Bronze": [],
            "Argent": [],
            "Or": [],
            "Platine": [],
            "Diamant": [],
            "Ascendant": [],
            "Immortel": [],
            "Radiant": []
        }
        self.role_priorities = {
            1136336081256722533: "Controller",
            1136336228892028980: "Duelist",
            1136336949376979014: "Initiator",
            1136337133691482223: "Sentinel",
        }
        self.scrims_data = {}
        self.warnings_data = load_json(WARNINGS_FILE)
        self.load_data()
        self.load_wins()
        self.bot.loop.create_task(self.load_messages())

    def load_wins(self):
        self.wins_data = load_json(WINS_FILE)

    def save_wins(self):
        save_json(self.wins_data, WINS_FILE)

    def get_wins(self, user_id):
        return self.wins_data.get(str(user_id), 0)

    def add_win(self, user_id):
        user_id = str(user_id)
        if user_id in self.wins_data:
            self.wins_data[user_id] += 1
        else:
            self.wins_data[user_id] = 1
        self.save_wins()

    async def add_player(self, interaction: discord.Interaction):
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            await interaction.response.send_message("Vous ne pouvez utiliser cette commande que dans le salon spécifié.", ephemeral=True)
            return

        user_rank = self.get_user_rank(interaction.user)
        if user_rank is None:
            await interaction.response.send_message("Votre rôle ne correspond à aucun rang de scrims valide.", ephemeral=True)
            return

        for player_list in self.players_by_rank[user_rank]:
            if any(player['id'] == interaction.user.id for player in player_list):
                await interaction.response.send_message("Vous êtes déjà inscrit dans la liste.", ephemeral=True)
                return

        for i, player_list in enumerate(self.players_by_rank[user_rank]):
            if len(player_list) < 10:
                player_list.append({
                    "id": interaction.user.id,
                    "name": interaction.user.display_name,
                    "rank": user_rank,
                    "wins": self.get_wins(interaction.user.id),
                    "roles": [role.id for role in interaction.user.roles if role.id in self.role_priorities]
                })
                await interaction.response.send_message(
                    "Merci pour votre inscription, nous recherchons encore des joueurs pour finaliser la création des scrims.\n"
                    "Vous recevrez un message lorsque les scrims seront créés.", 
                    ephemeral=True
                )
                await self.update_vote_message(user_rank, i)
                self.save_data()
                break
        else:
            new_list = [{
                "id": interaction.user.id,
                "name": interaction.user.display_name,
                "rank": user_rank,
                "wins": self.get_wins(interaction.user.id),
                "roles": [role.id for role in interaction.user.roles if role.id in self.role_priorities]
            }]
            self.players_by_rank[user_rank].append(new_list)
            self.messages_by_rank[user_rank].append(None)
            await interaction.response.send_message(
                "Merci pour votre inscription, nous recherchons encore des joueurs pour finaliser la création des scrims.\n"
                "Vous recevrez un message lorsque les scrims seront créés.", 
                ephemeral=True
            )
            await self.update_vote_message(user_rank, len(self.players_by_rank[user_rank]) - 1)
            self.save_data()

        for i, player_list in enumerate(self.players_by_rank[user_rank]):
            if len(player_list) == 10:
                await self.create_scrims(interaction, user_rank, i)
                self.save_data()

    async def remove_player(self, interaction: discord.Interaction):
        user_rank = self.get_user_rank(interaction.user)
        if user_rank is None:
            await interaction.response.send_message("Votre rôle ne correspond à aucun rang de scrims valide.", ephemeral=True)
            return

        for i, player_list in enumerate(self.players_by_rank[user_rank]):
            for player in player_list:
                if player['id'] == interaction.user.id:
                    player_list.remove(player)
                    await interaction.response.send_message("Votre inscription a été retirée avec succès.", ephemeral=True)
                    if not player_list:
                        await self.delete_list(user_rank, i)
                    else:
                        await self.update_vote_message(user_rank, i)
                    self.save_data()
                    return

        await interaction.response.send_message("Vous n'êtes pas inscrit dans la liste.", ephemeral=True)

    async def update_vote_message(self, rank: str, list_index: int):
        vote_channel = self.bot.get_channel(VOTE_CHANNEL_ID)
        if vote_channel and list_index < len(self.messages_by_rank[rank]):
            if self.messages_by_rank[rank][list_index]:
                embed = self.create_embed(rank, list_index)
                await self.messages_by_rank[rank][list_index].edit(embed=embed)
            else:
                embed = self.create_embed(rank, list_index)
                self.messages_by_rank[rank][list_index] = await vote_channel.send(embed=embed, view=VoteView(self, rank, list_index))

    def create_embed(self, rank: str, list_index: int):
        if list_index >= len(self.players_by_rank[rank]):
            return None
        player_list = "\n".join([f"{player['name']} ({player['rank']}, Scrims gagnés: {player['wins']})" for player in self.players_by_rank[rank][list_index]])
        color = discord.Color.red() if len(self.players_by_rank[rank][list_index]) < 10 else discord.Color.purple()
        embed = discord.Embed(
            title=f"Liste des joueurs inscrits pour {rank} (Liste {list_index + 1})",
            description=f"{player_list}\n\nRéagissez pour créer les scrims lorsque la liste est complète.",
            color=color
        )
        if len(self.players_by_rank[rank][list_index]) < 10:
            embed.set_footer(text="Statut : En attente de plus de membres")
        else:
            embed.set_footer(text="Statut : Création en attente")
        return embed

    async def create_scrims(self, interaction: discord.Interaction, rank: str, list_index: int):
        team_1, team_2 = self.split_teams(rank, list_index)

        guild = interaction.guild
        category = guild.get_channel(SCRIMS_CATEGORY_ID)
        if not category:
            category = await guild.create_category("Scrims")

        channel_1 = await guild.create_text_channel(f"Equipe 1 - {rank} (Liste {list_index + 1})", category=category)
        channel_2 = await guild.create_text_channel(f"Equipe 2 - {rank} (Liste {list_index + 1})", category=category)

        for player in team_1:
            member = guild.get_member(player['id'])
            await channel_1.set_permissions(member, read_messages=True, send_messages=True)
            await channel_2.set_permissions(member, read_messages=False, send_messages=False)
            await member.send(f"Vous avez été ajouté à l'Équipe 1. Voici le lien vers votre salon: {channel_1.mention}")

        for player in team_2:
            member = guild.get_member(player['id'])
            await channel_2.set_permissions(member, read_messages=True, send_messages=True)
            await channel_1.set_permissions(member, read_messages=False, send_messages=False)
            await member.send(f"Vous avez été ajouté à l'Équipe 2. Voici le lien vers votre salon: {channel_2.mention}")

        embed = self.create_embed(rank, list_index)
        embed.color = discord.Color.green()
        embed.set_footer(text="Statut : En attente des résultats")
        await self.messages_by_rank[rank][list_index].edit(embed=embed, view=ResultView(self, rank, list_index, team_1, team_2, channel_1.id, channel_2.id))

        scrims_data = {
            "team_1": [player['id'] for player in team_1],
            "team_2": [player['id'] for player in team_2],
            "ready": {player['id']: False for player in team_1 + team_2},
            "voted": {player['id']: False for player in team_1 + team_2},
            "votes": {hour: 0 for hour in range(18, 24)},
            "start_time": datetime.utcnow().isoformat()
        }
        self.scrims_data[(rank, list_index)] = scrims_data

        initial_embed = discord.Embed(
            title="Préparation des scrims",
            description="Veuillez valider votre présence, voter pour l'heure des scrims, et créer un salon vocal si nécessaire.",
            color=discord.Color.blurple()
        )
        await channel_1.send(embed=initial_embed, view=ScrimsPreparationView(self, rank, list_index))
        await channel_2.send(embed=initial_embed, view=ScrimsPreparationView(self, rank, list_index))

        self.check_scrims_status.start()

    @tasks.loop(minutes=1)
    async def check_scrims_status(self):
        now = datetime.utcnow()
        to_remove = []

        for (rank, list_index), data in self.scrims_data.items():
            start_time = datetime.fromisoformat(data["start_time"])
            if (now - start_time) > timedelta(hours=24):
                await self.handle_scrims_expiry(rank, list_index, data)
                to_remove.append((rank, list_index))

        for key in to_remove:
            del self.scrims_data[key]

    async def handle_scrims_expiry(self, rank, list_index, data):
        guild = self.bot.get_guild(self.bot.guilds[0].id)
        channels_to_delete = [guild.get_channel(cid) for cid in data.get("channels", [])]

        for channel in channels_to_delete:
            if channel:
                await channel.delete()

        unready_players = [pid for pid, ready in data["ready"].items() if not ready]
        for pid in unready_players:
            self.warnings_data[pid] = self.warnings_data.get(pid, 0) + 1

        save_json(self.warnings_data, WARNINGS_FILE)

        for pid in data["team_1"] + data["team_2"]:
            user = self.bot.get_user(pid)
            if user:
                try:
                    await user.send(f"Les scrims pour le rang {rank} ont été annulés car tous les joueurs n'ont pas validé leur présence.")
                    if pid in unready_players:
                        await user.send("Vous avez reçu un avertissement pour ne pas avoir validé votre présence.")
                except discord.Forbidden:
                    pass

        message = self.messages_by_rank[rank][list_index]
        if message:
            try:
                await message.delete()
            except discord.NotFound:
                pass

        del self.players_by_rank[rank][list_index]
        del self.messages_by_rank[rank][list_index]
        self.save_data()

    async def delete_list(self, rank: str, list_index: int):
        player_list = self.players_by_rank[rank][list_index]
        for player in player_list:
            user = self.bot.get_user(player['id'])
            if user:
                try:
                    await user.send(f"Votre inscription aux scrims pour le rang {rank} a été supprimée. Vous pouvez vous réinscrire dans le salon approprié : <#{ALLOWED_CHANNEL_ID}>.")
                except discord.Forbidden:
                    pass

        del self.players_by_rank[rank][list_index]
        message = self.messages_by_rank[rank][list_index]
        del self.messages_by_rank[rank][list_index]
        self.save_data()

        if message:
            try:
                await message.delete()
            except discord.NotFound:
                pass

    async def clear_scrims_data(self, rank: str, list_index: int):
        del self.players_by_rank[rank][list_index]
        del self.messages_by_rank[rank][list_index]
        self.save_data()

    def split_teams(self, rank: str, list_index: int):
        sorted_players = sorted(self.players_by_rank[rank][list_index], key=lambda x: x['wins'], reverse=True)
        team_1, team_2 = [], []

        for role_id in self.role_priorities:
            players_with_role = [player for player in sorted_players if role_id in player['roles']]
            for i, player in enumerate(players_with_role):
                if i % 2 == 0:
                    team_1.append(player)
                else:
                    team_2.append(player)

        remaining_players = [player for player in sorted_players if player not in team_1 and player not in team_2]
        for i, player in enumerate(remaining_players):
            if i % 2 == 0:
                team_1.append(player)
            else:
                team_2.append(player)

        return team_1, team_2

    def get_user_rank(self, user: discord.Member):
        rank_roles = {
            "Fer": "Fer",
            "Bronze": "Bronze",
            "Argent": "Argent",
            "Or": "Or",
            "Platine": "Platine",
            "Diamant": "Diamant",
            "Ascendant": "Ascendant",
            "Immortel": "Immortel",
            "Radiant": "Radiant"
        }
        for role in user.roles:
            if role.name in rank_roles:
                return rank_roles[role.name]
        return None

    def save_data(self):
        data = {
            "players_by_rank": self.players_by_rank,
            "messages_by_rank": {rank: [message.id if message else None for message in messages] for rank, messages in self.messages_by_rank.items()}
        }
        save_json(data, SAVE_FILE)

    def load_data(self):
        data = load_json(SAVE_FILE)
        self.players_by_rank = data.get("players_by_rank", self.players_by_rank)
        messages_by_rank = data.get("messages_by_rank", {})
        for rank, messages in messages_by_rank.items():
            self.messages_by_rank[rank] = [None for _ in messages]

    async def load_messages(self):
        await self.bot.wait_until_ready()
        vote_channel = self.bot.get_channel(VOTE_CHANNEL_ID)
        if vote_channel:
            for rank, message_ids in self.messages_by_rank.items():
                for i, message_id in enumerate(message_ids):
                    if message_id:
                        try:
                            message = await vote_channel.fetch_message(message_id)
                            self.messages_by_rank[rank][i] = message
                            await self.attach_views(rank, i, message)
                        except discord.NotFound:
                            self.messages_by_rank[rank][i] = None

    async def attach_views(self, rank: str, list_index: int, message: discord.Message):
        await message.edit(view=VoteView(self, rank, list_index))

    @app_commands.command(name="inscription_scrims", description="S'inscrire pour un scrims selon votre rang")
    async def inscription_scrims(self, interaction: discord.Interaction):
        await self.add_player(interaction)

    @app_commands.command(name="retirer_inscription", description="Retirer votre inscription des scrims")
    async def retirer_inscription(self, interaction: discord.Interaction):
        await self.remove_player(interaction)

class VoteView(discord.ui.View):
    def __init__(self, cog, rank, list_index):
        super().__init__(timeout=None)
        self.cog = cog
        self.rank = rank
        self.list_index = list_index

    @discord.ui.button(label="Créer les scrims", style=discord.ButtonStyle.success, custom_id="create_scrims")
    async def create_scrims_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.create_scrims(interaction, self.rank, self.list_index)

    @discord.ui.button(label="Supprimer la liste", style=discord.ButtonStyle.danger, custom_id="delete_list")
    async def delete_list_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.delete_list(self.rank, self.list_index)
        await interaction.response.send_message("La liste a été supprimée avec succès.", ephemeral=True)

class ResultView(discord.ui.View):
    def __init__(self, cog, rank, list_index, team_1, team_2, channel_1_id, channel_2_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.rank = rank
        self.list_index = list_index
        self.team_1 = team_1
        self.team_2 = team_2
        self.channel_1_id = channel_1_id
        self.channel_2_id = channel_2_id

    @discord.ui.button(label="Équipe 1 a gagné", style=discord.ButtonStyle.success, custom_id="team_1_win")
    async def team_1_win_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for player in self.team_1:
            self.cog.add_win(player['id'])
        await interaction.response.send_message("Les résultats ont été enregistrés. Équipe 1 a gagné !", ephemeral=True)
        await self.cog.clear_scrims_data(self.rank, self.list_index)
        await interaction.message.delete()
        await self.delete_channels(interaction.guild)

    @discord.ui.button(label="Équipe 2 a gagné", style=discord.ButtonStyle.success, custom_id="team_2_win")
    async def team_2_win_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for player in self.team_2:
            self.cog.add_win(player['id'])
        await interaction.response.send_message("Les résultats ont été enregistrés. Équipe 2 a gagné !", ephemeral=True)
        await self.cog.clear_scrims_data(self.rank, self.list_index)
        await interaction.message.delete()
        await self.delete_channels(interaction.guild)

    async def delete_channels(self, guild):
        channel_1 = guild.get_channel(self.channel_1_id)
        channel_2 = guild.get_channel(self.channel_2_id)
        if channel_1:
            await channel_1.delete()
        if channel_2:
            await channel_2.delete()

class ScrimsPreparationView(discord.ui.View):
    def __init__(self, cog, rank, list_index):
        super().__init__(timeout=86400)
        self.cog = cog
        self.rank = rank
        self.list_index = list_index

    @discord.ui.button(label="Valider la présence", style=discord.ButtonStyle.primary, custom_id="validate_presence")
    async def validate_presence_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        scrims_data = self.cog.scrims_data[(self.rank, self.list_index)]
        scrims_data["ready"][interaction.user.id] = True
        self.update_embed()

    @discord.ui.button(label="Créer un salon vocal", style=discord.ButtonStyle.secondary, custom_id="create_voice_channel")
    async def create_voice_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        scrims_data = self.cog.scrims_data[(self.rank, self.list_index)]
        existing_voice_channel = scrims_data.get("voice_channel")
        if existing_voice_channel:
            await interaction.response.send_message(f"Un salon vocal existe déjà : <#{existing_voice_channel}>", ephemeral=True)
        else:
            guild = interaction.guild
            category = guild.get_channel(SCRIMS_CATEGORY_ID)
            voice_channel = await guild.create_voice_channel(f"Vocal - {self.rank} (Liste {self.list_index + 1})", category=category)
            for player_id in scrims_data["team_1"] + scrims_data["team_2"]:
                member = guild.get_member(player_id)
                await voice_channel.set_permissions(member, read_messages=True, send_messages=True, connect=True, speak=True)
            scrims_data["voice_channel"] = voice_channel.id
            await interaction.response.send_message(f"Salon vocal créé : {voice_channel.mention}", ephemeral=True)
            self.start_voice_channel_cleanup(voice_channel.id)

    @discord.ui.button(label="Voter pour l'heure", style=discord.ButtonStyle.secondary, custom_id="vote_time")
    async def vote_time_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = VoteTimeModal(self.cog, self.rank, self.list_index)
        await interaction.response.send_modal(modal)

    def update_embed(self):
        scrims_data = self.cog.scrims_data[(self.rank, self.list_index)]
        ready_players = [player_id for player_id, ready in scrims_data["ready"].items() if ready]
        voted_players = [player_id for player_id, voted in scrims_data["voted"].items() if voted]
        embed = discord.Embed(
            title="Préparation des scrims",
            description="Veuillez valider votre présence, voter pour l'heure des scrims, et créer un salon vocal si nécessaire.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Joueurs prêts", value="\n".join([f"<@{player_id}>" for player_id in ready_players]) or "Aucun")
        embed.add_field(name="Joueurs ayant voté", value="\n".join([f"<@{player_id}>" for player_id in voted_players]) or "Aucun")
        message = self.cog.messages_by_rank[self.rank][self.list_index]
        self.cog.bot.loop.create_task(message.edit(embed=embed))

    def start_voice_channel_cleanup(self, voice_channel_id):
        self.cog.bot.loop.create_task(self.voice_channel_cleanup(voice_channel_id))

    async def voice_channel_cleanup(self, voice_channel_id):
        await discord.utils.sleep_until(datetime.utcnow() + timedelta(minutes=2))
        voice_channel = self.cog.bot.get_channel(voice_channel_id)
        if voice_channel and len(voice_channel.members) == 0:
            await voice_channel.delete()

class VoteTimeModal(discord.ui.Modal):
    def __init__(self, cog, rank, list_index):
        super().__init__(title="Vote pour l'heure")
        self.cog = cog
        self.rank = rank
        self.list_index = list_index
        self.hours = [str(hour) for hour in range(18, 24)]
        self.add_item(discord.ui.Select(placeholder="Choisissez l'heure", options=[discord.SelectOption(label=hour) for hour in self.hours]))

    async def callback(self, interaction: discord.Interaction):
        selected_hour = int(self.children[0].values[0])
        scrims_data = self.cog.scrims_data[(self.rank, self.list_index)]
        scrims_data["votes"][selected_hour] += 1
        scrims_data["voted"][interaction.user.id] = True
        self.update_embed(self.rank, self.list_index)
        await interaction.response.send_message(f"Merci pour votre vote pour {selected_hour}h.", ephemeral=True)
        if all(scrims_data["voted"].values()):
            most_voted_hour = max(scrims_data["votes"], key=scrims_data["votes"].get)
            message = self.cog.messages_by_rank[self.rank][self.list_index]
            await message.edit(embed=discord.Embed(
                title="Horaire des scrims",
                description=f"L'heure des scrims a été fixée à {most_voted_hour}h.",
                color=discord.Color.green()
            ))

async def setup(bot):
    await bot.add_cog(ScrimsManager(bot))
