# cogs/scrims/registration.py

import datetime
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from typing import List, Dict, Any, Optional, Tuple
import asyncio

from cogs.utilities.views import ResultView, ScrimsPreparationView, VoteView

from cogs.utilities.utils import load_json, save_json, save_json_atomic

logger = logging.getLogger('discord.scrims.registration')

def make_scrims_key(rank: str, list_index: int) -> str:
    """Creates a unique key for scrims data."""
    return f"{rank}-{list_index}"

class ScrimRegistration(commands.Cog):
    """Cog pour gérer l'inscription des joueurs aux scrims."""

    dependencies = ["cogs.scrims.cleanup"]

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.scrims_data_file = "data/scrims_data.json"
        self.wins_data_file = "data/wins_data.json"
        self.warnings_data_file = "data/warnings_data.json"

        self.players_by_rank: Dict[str, List[List[Dict[str, Any]]]] = {
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
        self.messages_by_rank: Dict[str, List[Optional[discord.Message]]] = {
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
        self.role_priorities: Dict[int, int] = {}  # Role ID to priority mapping
        self.scrims_data: Dict[str, Dict[str, Any]] = {}
        self.wins_data: Dict[str, int] = {}
        self.warnings_data: Dict[str, int] = {}
        self.config: Dict[str, Any] = {}
        self.data_lock = asyncio.Lock()

        # Start data loading and task
        self.bot.loop.create_task(self.load_all_data())
        self.check_scrims_status.start()  # Assurez-vous que cette méthode est définie avant

    async def load_all_data(self) -> None:
        """Charge toutes les données nécessaires depuis les fichiers JSON."""
        async with self.data_lock:
            self.config = await load_json(self.config_file)
            self.role_priorities = {int(k): v for k, v in self.config.get("role_priorities", {}).items()}

            self.wins_data = await load_json(self.wins_data_file)
            self.warnings_data = await load_json(self.warnings_data_file)
            self.scrims_data = await load_json(self.scrims_data_file)

            # Initialize players_by_rank and messages_by_rank from scrims_data
            self.players_by_rank = self.scrims_data.get("players_by_rank", self.players_by_rank)
            messages_by_rank = self.scrims_data.get("messages_by_rank", {})
            for rank, messages in messages_by_rank.items():
                self.messages_by_rank[rank] = [msg_id if msg_id is not None else None for msg_id in messages]

        await self.load_messages()
        logger.info("ScrimRegistration: Toutes les données ont été chargées avec succès.")

    async def save_all_data(self) -> None:
        """Sauvegarde toutes les données dans les fichiers JSON de manière atomique."""
        async with self.data_lock:
            self.scrims_data["players_by_rank"] = self.players_by_rank
            self.scrims_data["messages_by_rank"] = {
                rank: [msg.id if msg else None for msg in messages]
                for rank, messages in self.messages_by_rank.items()
            }
            await save_json_atomic(self.scrims_data, self.scrims_data_file)
            await save_json_atomic(self.wins_data, self.wins_data_file)
            await save_json_atomic(self.warnings_data, self.warnings_data_file)
        logger.info("ScrimRegistration: Toutes les données ont été sauvegardées avec succès.")

    async def load_messages(self) -> None:
        """Charge les messages de vote depuis les salons."""
        await self.bot.wait_until_ready()
        vote_channel = self.bot.get_channel(self.config.get("vote_channel_id"))
        if vote_channel:
            for rank, message_ids in self.messages_by_rank.items():
                for i, message_id in enumerate(message_ids):
                    if message_id:
                        try:
                            message = await vote_channel.fetch_message(message_id)
                            self.messages_by_rank[rank][i] = message
                            scrims_key = make_scrims_key(rank, i)
                            scrims_data = self.scrims_data.get(scrims_key)
                            if scrims_data:
                                if "voice_channel" in scrims_data:
                                    # Attach ResultView
                                    await message.edit(embed=self.create_scrim_embed(rank, i, [], []), view=ResultView(
                                        self, rank, i, 
                                        team_1=[{"id": pid, "name": ""} for pid in scrims_data["team_1"]], 
                                        team_2=[{"id": pid, "name": ""} for pid in scrims_data["team_2"]],
                                        channel_1_id=scrims_data["channels"][0],
                                        channel_2_id=scrims_data["channels"][1]
                                    ))
                                else:
                                    # Attach VoteView
                                    await message.edit(embed=self.create_scrim_embed(rank, i, [], []), view=VoteView(self, rank, i))
                            else:
                                # Attach default VoteView
                                await self.attach_views(rank, i, message)
                            logger.info(f"Vue réattachée au message pour {rank} - Liste {i + 1}.")
                        except discord.NotFound:
                            self.messages_by_rank[rank][i] = None
                            logger.warning(f"Message de vote non trouvé pour {rank} - Liste {i + 1}.")
                        except discord.Forbidden:
                            self.messages_by_rank[rank][i] = None
                            logger.warning(f"Permission refusée pour accéder au message {message_id} dans le canal de vote.")
                        except Exception as e:
                            self.messages_by_rank[rank][i] = None
                            logger.exception(f"Erreur lors de la récupération du message {message_id} pour {rank} - Liste {i + 1}: {e}")

    async def attach_views(self, rank: str, list_index: int, message: discord.Message) -> None:
        """Attache la vue de vote au message."""
        try:
            await message.edit(embed=self.create_scrim_embed(rank, list_index, [], []), view=VoteView(self, rank, list_index))
            logger.info(f"Vue de vote attachée au message pour {rank} - Liste {list_index + 1}.")
        except Exception as e:
            logger.exception(f"Erreur lors de l'attachement de la vue de vote au message pour {rank} - Liste {list_index + 1}: {e}")

    def create_scrim_embed(self, rank: str, list_index: int, ready_players: List[str], voted_players: List[str], status: str = "Préparation des scrims") -> discord.Embed:
        """Crée un embed pour les scrims."""
        color = discord.Color.blurple()
        if status == "Résultats":
            color = discord.Color.green()

        embed = discord.Embed(
            title=status,
            description="Veuillez valider votre présence, voter pour l'heure des scrims, et créer un salon vocal si nécessaire.",
            color=color
        )
        embed.add_field(name="Joueurs prêts", value="\n".join(ready_players) or "Aucun", inline=False)
        embed.add_field(name="Joueurs ayant voté", value="\n".join(voted_players) or "Aucun", inline=False)
        embed.set_footer(text=f"{rank} - Liste {list_index + 1}")
        return embed

    @app_commands.command(name="register_scrim", description="Inscrire un joueur aux scrims")
    async def register_scrim(self, interaction: discord.Interaction) -> None:
        """Commande pour inscrire un joueur aux scrims."""
        await self.add_player(interaction)

    @app_commands.command(name="unregister_scrim", description="Désinscrire un joueur des scrims")
    async def unregister_scrim(self, interaction: discord.Interaction) -> None:
        """Commande pour désinscrire un joueur des scrims."""
        await self.remove_player(interaction)

    async def add_player(self, interaction: discord.Interaction) -> None:
        """Ajoute un joueur à la liste des scrims après validation."""
        async with self.data_lock:
            if interaction.channel_id != self.config.get("allowed_channel_id"):
                await interaction.response.send_message(
                    "Vous ne pouvez utiliser cette commande que dans le salon spécifié.",
                    ephemeral=True
                )
                return

            user_rank = self.get_user_rank(interaction.user)
            if user_rank is None:
                await interaction.response.send_message(
                    "Votre rôle ne correspond à aucun rang de scrims valide.",
                    ephemeral=True
                )
                return

            # Vérifier si l'utilisateur est déjà inscrit dans n'importe quel rang
            for rank, player_lists in self.players_by_rank.items():
                for player_list in player_lists:
                    if any(player['id'] == interaction.user.id for player in player_list):
                        await interaction.response.send_message(
                            "Vous êtes déjà inscrit dans une liste de scrims.",
                            ephemeral=True
                        )
                        return

            # Ajouter le joueur à la première liste disponible avec moins de 10 joueurs
            for i, player_list in enumerate(self.players_by_rank[user_rank]):
                if len(player_list) < 10:
                    player_entry = {
                        "id": interaction.user.id,
                        "name": interaction.user.display_name,
                        "rank": user_rank,
                        "wins": self.get_wins(interaction.user.id),
                        "roles": [role.id for role in interaction.user.roles if role.id in self.role_priorities]
                    }
                    player_list.append(player_entry)
                    await interaction.response.send_message(
                        "Merci pour votre inscription, nous recherchons encore des joueurs pour finaliser la création des scrims.\n"
                        "Vous recevrez un message lorsque les scrims seront créés.",
                        ephemeral=True
                    )
                    await self.update_vote_message(user_rank, i)
                    await self.save_all_data()
                    break
            else:
                # Créer une nouvelle liste si toutes les listes existantes sont complètes
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
                await self.save_all_data()

            # Vérifier si une liste est complète et créer les scrims si nécessaire
            for i, player_list in enumerate(self.players_by_rank[user_rank]):
                scrims_key = make_scrims_key(user_rank, i)
                if len(player_list) == 10 and scrims_key not in self.scrims_data:
                    await self.create_scrims(interaction, user_rank, i)
                    await self.save_all_data()

    async def remove_player(self, interaction: discord.Interaction) -> None:
        """Retire un joueur de la liste des scrims."""
        async with self.data_lock:
            user_rank = self.get_user_rank(interaction.user)
            if user_rank is None:
                await interaction.response.send_message(
                    "Votre rôle ne correspond à aucun rang de scrims valide.",
                    ephemeral=True
                )
                return

            for i, player_list in enumerate(self.players_by_rank[user_rank]):
                for player in player_list:
                    if player['id'] == interaction.user.id:
                        player_list.remove(player)
                        await interaction.response.send_message(
                            "Votre inscription a été retirée avec succès.",
                            ephemeral=True
                        )
                        if not player_list:
                            await self.delete_list(user_rank, i)
                        else:
                            await self.update_vote_message(user_rank, i)
                        await self.save_all_data()
                        return

            await interaction.response.send_message(
                "Vous n'êtes pas inscrit dans la liste.",
                ephemeral=True
            )

    def get_user_rank(self, user: discord.Member) -> Optional[str]:
        """Détermine le rang de l'utilisateur basé sur ses rôles."""
        user_roles = {role.name for role in user.roles}
        for role_id, priority in sorted(self.role_priorities.items(), key=lambda x: x[1], reverse=True):
            if role_id in user_roles:
                # Trouver le nom du rôle correspondant
                role = user.guild.get_role(role_id)
                if role:
                    return role.name
        return None

    def get_wins(self, user_id: int) -> int:
        """Retourne le nombre de victoires d'un utilisateur."""
        return self.wins_data.get(str(user_id), 0)

    def split_teams(self, rank: str, list_index: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Divise la liste des joueurs en deux équipes équilibrées."""
        players = self.players_by_rank[rank][list_index]
        sorted_players = sorted(players, key=lambda x: x['wins'], reverse=True)
        team_1 = sorted_players[::2]
        team_2 = sorted_players[1::2]
        return team_1, team_2

    @tasks.loop(minutes=5)
    async def check_scrims_status(self):
        """Tâche périodique pour vérifier l'état des scrims."""
        logger.info("Vérification de l'état des scrims...")
        # Implémentez la logique pour vérifier et mettre à jour l'état des scrims
        # Par exemple, vérifier si certains scrims doivent être terminés ou mises à jour

    @check_scrims_status.before_loop
    async def before_check_scrims_status(self):
        """Attend que le bot soit prêt avant de démarrer la tâche de vérification."""
        await self.bot.wait_until_ready()
        logger.info("Tâche de vérification des scrims démarrée.")

    async def cog_unload(self):
        """Nettoie les tâches avant de décharger le cog."""
        self.check_scrims_status.cancel()
        logger.info("Tâche de vérification des scrims annulée.")

    # Ajoutez d'autres méthodes comme `update_vote_message`, `delete_list`, etc., si nécessaire

async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog ScrimRegistration au bot."""
    await bot.add_cog(ScrimRegistration(bot))
    logger.info("ScrimRegistration Cog chargé avec succès.")
