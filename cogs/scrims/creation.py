# cogs/scrims/creation.py

import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from ..utilities.utils import load_json, save_json

logger = logging.getLogger('discord.scrims.creation')

def make_scrims_key(rank: str, list_index: int) -> str:
    """Creates a unique key for scrims data."""
    return f"{rank}-{list_index}"

class ScrimCreation(commands.Cog):
    """Cog pour créer les scrims une fois que les listes sont complètes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.scrims_data_file = "data/scrims_data.json"
        self.config: Dict[str, Any] = {}
        self.scrims_data: Dict[str, Dict[str, Any]] = {}
        self.data_lock = asyncio.Lock()

        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration et les données des scrims depuis les fichiers JSON."""
        async with self.data_lock:
            self.config = await load_json(self.config_file)
            self.scrims_data = await load_json(self.scrims_data_file)
        logger.info("ScrimCreation: Configuration et données des scrims chargées avec succès.")

    async def save_scrims_data(self) -> None:
        """Sauvegarde les données des scrims dans le fichier JSON."""
        async with self.data_lock:
            await save_json_atomic(self.scrims_data, self.scrims_data_file)
        logger.info("ScrimCreation: Données des scrims sauvegardées avec succès.")

    async def create_scrims(self, interaction: discord.Interaction, rank: str, list_index: int) -> None:
        """Crée les scrims une fois que la liste est complète."""
        scrims_key = make_scrims_key(rank, list_index)
        team_1, team_2 = self.split_teams(rank, list_index)

        guild = interaction.guild
        category = guild.get_channel(self.config.get("scrims_category_id"))
        if not category:
            try:
                category = await guild.create_category("Scrims")
                logger.info("Catégorie 'Scrims' créée.")
            except discord.Forbidden:
                logger.error("Permission refusée lors de la création de la catégorie 'Scrims'.")
                await interaction.response.send_message(
                    "Erreur: Permission refusée pour créer la catégorie des scrims.",
                    ephemeral=True
                )
                return
            except Exception as e:
                logger.exception("Erreur lors de la création de la catégorie 'Scrims':", exc_info=True)
                await interaction.response.send_message(
                    "Erreur inattendue lors de la création de la catégorie des scrims.",
                    ephemeral=True
                )
                return

        # Création des salons pour les équipes
        try:
            channel_1 = await guild.create_text_channel(
                f"Équipe 1 - {rank} (Liste {list_index + 1})",
                category=category
            )
            channel_2 = await guild.create_text_channel(
                f"Équipe 2 - {rank} (Liste {list_index + 1})",
                category=category
            )
            logger.info(f"Salons créés: {channel_1.name}, {channel_2.name}")
        except discord.Forbidden:
            logger.error("Permission refusée lors de la création des salons des équipes.")
            await interaction.response.send_message(
                "Erreur: Permission refusée pour créer les salons des équipes.",
                ephemeral=True
            )
            return
        except Exception as e:
            logger.exception("Erreur lors de la création des salons des équipes:", exc_info=True)
            await interaction.response.send_message(
                "Erreur inattendue lors de la création des salons des équipes.",
                ephemeral=True
            )
            return

        # Attribution des permissions et envoi des messages aux joueurs
        for player in team_1:
            member = guild.get_member(player['id'])
            if member:
                try:
                    await channel_1.set_permissions(member, read_messages=True, send_messages=True, connect=True, speak=True)
                    await channel_2.set_permissions(member, read_messages=False, send_messages=False, connect=False, speak=False)
                    await member.send(f"Vous avez été ajouté à l'Équipe 1. Voici le lien vers votre salon: {channel_1.mention}")
                except discord.Forbidden:
                    logger.warning(f"Impossible d'envoyer un message à {member.display_name} ou de modifier les permissions.")
                except Exception as e:
                    logger.exception(f"Erreur lors de l'attribution des permissions ou de l'envoi du message à {member.display_name}: {e}")

        for player in team_2:
            member = guild.get_member(player['id'])
            if member:
                try:
                    await channel_2.set_permissions(member, read_messages=True, send_messages=True, connect=True, speak=True)
                    await channel_1.set_permissions(member, read_messages=False, send_messages=False, connect=False, speak=False)
                    await member.send(f"Vous avez été ajouté à l'Équipe 2. Voici le lien vers votre salon: {channel_2.mention}")
                except discord.Forbidden:
                    logger.warning(f"Impossible d'envoyer un message à {member.display_name} ou de modifier les permissions.")
                except Exception as e:
                    logger.exception(f"Erreur lors de l'attribution des permissions ou de l'envoi du message à {member.display_name}: {e}")

        # Mise à jour de l'embed et ajout de la vue de résultats
        embed = self.create_scrim_embed(rank, list_index, [], [])
        embed.color = discord.Color.green()
        embed.set_footer(text="Statut : En attente des résultats")
        try:
            message = self.messages_by_rank[rank][list_index]
            if message:
                await message.edit(
                    embed=embed,
                    view=ResultView(
                        self, rank, list_index, 
                        team_1=team_1, 
                        team_2=team_2, 
                        channel_1_id=channel_1.id, 
                        channel_2_id=channel_2.id
                    )
                )
                logger.info(f"Résultats mis à jour pour {rank} - Liste {list_index + 1}.")
        except discord.NotFound:
            logger.warning(f"Message de vote non trouvé pour {rank} - Liste {list_index + 1} lors de la mise à jour des résultats.")
        except Exception as e:
            logger.exception(f"Erreur lors de la mise à jour des résultats pour {rank} - Liste {list_index + 1}: {e}")

        # Enregistrement des données des scrims
        self.scrims_data[scrims_key] = {
            "team_1": [player['id'] for player in team_1],
            "team_2": [player['id'] for player in team_2],
            "ready": {player['id']: False for player in team_1 + team_2},
            "voted": {player['id']: False for player in team_1 + team_2},
            "votes": {hour: 0 for hour in range(18, 24)},
            "start_time": datetime.utcnow().isoformat(),
            "channels": [channel_1.id, channel_2.id]
        }

        await self.save_scrims_data()

        # Envoi des instructions dans les salons textuels
        initial_embed = discord.Embed(
            title="Préparation des scrims",
            description="Veuillez valider votre présence, voter pour l'heure des scrims, et créer un salon vocal si nécessaire.",
            color=discord.Color.blurple()
        )
        try:
            await channel_1.send(embed=initial_embed, view=ScrimsPreparationView(self, rank, list_index))
            await channel_2.send(embed=initial_embed, view=ScrimsPreparationView(self, rank, list_index))
            logger.info(f"Instructions envoyées dans les salons {channel_1.name} et {channel_2.name}.")
        except discord.Forbidden:
            logger.error("Permission refusée lors de l'envoi des instructions dans les salons des équipes.")
            await interaction.response.send_message(
                "Erreur: Permission refusée pour envoyer des messages dans les salons des équipes.",
                ephemeral=True
            )
        except Exception as e:
            logger.exception("Erreur lors de l'envoi des instructions dans les salons des équipes:", exc_info=True)
            await interaction.response.send_message(
                "Erreur inattendue lors de l'envoi des instructions dans les salons des équipes.",
                ephemeral=True
            )

    def split_teams(self, rank: str, list_index: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Divise la liste des joueurs en deux équipes équilibrées."""
        players = self.players_by_rank[rank][list_index]
        sorted_players = sorted(players, key=lambda x: x['wins'], reverse=True)
        team_1 = sorted_players[::2]
        team_2 = sorted_players[1::2]
        return team_1, team_2

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

    async def setup(self, bot: commands.Bot) -> None:
        """Ajoute le Cog ScrimCreation au bot."""
        await bot.add_cog(ScrimCreation(bot))
        logger.info("ScrimCreation Cog chargé avec succès.")
