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

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.scrims_data_file = "data/scrims_data.json"
        self.wins_data_file = "data/wins_data.json"
        self.warnings_data_file = "data/warnings_data.json"

        self.players_by_rank: Dict[str, List[List[Dict[str, Any]]]] = {}
        self.messages_by_rank: Dict[str, List[Optional[discord.Message]]] = {}
        self.role_priorities: Dict[int, int] = {}
        self.scrims_data: Dict[str, Dict[str, Any]] = {}
        self.wins_data: Dict[str, int] = {}
        self.warnings_data: Dict[str, int] = {}
        self.config: Dict[str, Any] = {}
        self.data_lock = asyncio.Lock()

        # Initialize rank structure
        for rank in ["Fer", "Bronze", "Argent", "Or", "Platine", "Diamant", "Ascendant", "Immortel", "Radiant"]:
            self.players_by_rank[rank] = []
            self.messages_by_rank[rank] = []

        # Start data loading and tasks
        self.bot.loop.create_task(self.load_all_data())
        self.check_scrims_status.start()

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
        vote_channel_id = self.config.get("vote_channel_id")
        if vote_channel_id is None:
            logger.warning("vote_channel_id n'est pas défini dans la configuration.")
            return
        vote_channel = self.bot.get_channel(vote_channel_id)
        if not vote_channel:
            logger.warning(f"Channel avec l'ID {vote_channel_id} pour les votes non trouvé.")
            return
        for rank, message_ids in self.messages_by_rank.items():
            for i, message_id in enumerate(message_ids):
                if message_id:
                    try:
                        message = await vote_channel.fetch_message(message_id)
                        self.messages_by_rank[rank][i] = message
                        logger.info(f"Message chargé pour {rank} - Liste {i + 1}.")
                    except discord.NotFound:
                        logger.warning(f"Message non trouvé pour {rank} - Liste {i + 1}.")
                    except discord.Forbidden:
                        logger.warning(f"Permission refusée pour accéder au message {message_id} dans le canal de vote.")
                    except Exception as e:
                        logger.exception(f"Erreur lors de la récupération du message {message_id} pour {rank} - Liste {i + 1}: {e}")

    async def attach_views(self, rank: str, list_index: int, message: discord.Message) -> None:
        """Attache la vue de vote au message."""
        try:
            await message.edit(embed=self.create_scrim_embed(rank, list_index, [], []), view=VoteView(self, rank, list_index))
            logger.info(f"Vue de vote attachée pour {rank} - Liste {list_index + 1}.")
        except Exception as e:
            logger.exception(f"Erreur lors de l'attachement de la vue de vote pour {rank} - Liste {list_index + 1}: {e}")

    def create_scrim_embed(self, rank: str, list_index: int, ready_players: List[str], voted_players: List[str], status: str = "Préparation des scrims") -> discord.Embed:
        """Crée un embed pour les scrims."""
        color = discord.Color.blurple()
        embed = discord.Embed(
            title=status,
            description="Veuillez valider votre présence, voter pour l'heure des scrims, et créer un salon vocal si nécessaire.",
            color=color
        )
        embed.add_field(name="Joueurs prêts", value="\n".join(ready_players) or "Aucun", inline=False)
        embed.add_field(name="Joueurs ayant voté", value="\n".join(voted_players) or "Aucun", inline=False)
        embed.set_footer(text=f"{rank} - Liste {list_index + 1}")
        return embed

    @tasks.loop(minutes=5)
    async def check_scrims_status(self):
        """Vérifie régulièrement le statut des scrims."""
        pass  # Implémentez la logique pour vérifier et mettre à jour le statut des scrims.

async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog ScrimRegistration au bot."""
    if bot.get_cog("ScrimRegistration"):
        logger.warning("ScrimRegistration Cog déjà chargé. Ignoré.")
        return
    await bot.add_cog(ScrimRegistration(bot))
    logger.info("ScrimRegistration Cog chargé avec succès.")
