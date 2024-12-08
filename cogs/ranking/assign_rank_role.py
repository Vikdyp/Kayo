# cogs/ranking/assign_rank_role.py

import discord
from discord.ext import commands
import aiohttp
import logging
from typing import Optional

from cogs.utilities.utils import load_json, save_json

logger = logging.getLogger('discord.ranking.assign_rank_role')


class AssignRankRole(commands.Cog):
    """Cog pour attribuer des rôles basés sur le rang Valorant."""

    dependencies = []

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.valorant_api_key = bot.valorant_api_key
        self.config_file = 'data/config.json'
        self.config = {}
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration depuis le fichier JSON."""
        self.config = await load_json(self.config_file)
        logger.info("AssignRankRole: Configuration chargée avec succès.")

    async def save_config(self) -> None:
        """Sauvegarde la configuration dans le fichier JSON."""
        await save_json(self.config, self.config_file)
        logger.info("AssignRankRole: Configuration sauvegardée avec succès.")

    async def assign_rank_role(self, member: discord.Member, valorant_username: str) -> None:
        """
        Attribue un rôle basé sur le rang Valorant de l'utilisateur.

        Parameters:
            member (discord.Member): Membre Discord.
            valorant_username (str): Nom d'utilisateur Valorant.
        """
        url = f"https://public-api.tracker.gg/v2/valorant/standard/profile/riot/{valorant_username}"
        headers = {
            'TRN-Api-Key': self.valorant_api_key,
            'User-Agent': 'Mozilla/5.0',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        logger.info(f"Fetching rank data for {valorant_username} from {url}")
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    logger.info(f"API response status: {response.status}")
                    if response.status != 200:
                        logger.error(f"Erreur lors de la récupération du rang pour {valorant_username}: Status Code {response.status}")
                        return
                    data = await response.json()
                    rank = data['data']['segments'][0]['stats']['rank']['metadata']['tierName']
                    role_name = f"Valorant {rank}"
                    guild = member.guild
                    role_id = self.config.get("role_mappings", {}).get(role_name)
                    if role_id:
                        role = guild.get_role(role_id)
                        if role:
                            # Retirer tous les autres rôles Valorant
                            valorant_roles = [
                                r for r in guild.roles if r.name.startswith("Valorant ")
                            ]
                            if valorant_roles:
                                await member.remove_roles(*valorant_roles, reason="Mise à jour du rang Valorant.")
                                logger.info(f"Rôles Valorant précédents retirés pour {member.name}.")
                            await member.add_roles(role, reason="Attribution du rang Valorant.")
                            logger.info(f"Rôle {role.name} attribué à {member.name}.")
                        else:
                            logger.error(f"Le rôle avec l'ID {role_id} n'a pas été trouvé dans le serveur {guild.name}.")
                    else:
                        logger.warning(f"Aucun mapping de rôle trouvé pour {role_name}.")
            except aiohttp.ClientError as e:
                logger.error(f"Erreur lors de la requête à l'API tracker.gg: {e}")
            except KeyError as e:
                logger.error(f"Clé manquante dans la réponse de l'API pour {valorant_username}: {e}")
            except Exception as e:
                logger.exception(f"Erreur inattendue lors de l'attribution du rôle: {e}")


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog AssignRankRole au bot."""
    await bot.add_cog(AssignRankRole(bot))
    logger.info("AssignRankRole Cog chargé avec succès.")
