# cogs/ranking/assign_rank_role.py

import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import logging
from typing import Optional, Any
from cogs.utilities.data_manager import DataManager
from cogs.utilities.request_manager import enqueue_request
from cogs.utilities.permission_manager import is_admin
from cogs.utilities.confirmation_view import ConfirmationView

logger = logging.getLogger('discord.ranking.assign_rank_role')

VALID_RANKS = ["Fer", "Bronze", "Argent", "Or", "Platine", "Diamant", "Ascendant", "Immortel", "Radiant"]

class AssignRankRole(commands.Cog):
    """Cog pour attribuer des rôles basés sur le rang Valorant."""

    dependencies = []

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.valorant_api_key = bot.valorant_api_key
        self.config_file = 'data/config.json'
        self.config = {}
        self.data = DataManager()
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        self.config = await self.data.get_config()
        logger.info("AssignRankRole: Configuration chargée avec succès.")

    async def save_config(self) -> None:
        await self.data.save_config(self.config)
        logger.info("AssignRankRole: Configuration sauvegardée avec succès.")

    async def assign_rank_role(self, member: discord.Member, valorant_username: str) -> None:
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
                        logger.error(f"Erreur lors de la récupération du rang pour {valorant_username}: Status {response.status}")
                        return
                    data = await response.json()
                    rank = data['data']['segments'][0]['stats']['rank']['metadata']['tierName']
                    role_name = rank  # Utilise directement le rang sans le préfixe "Valorant"
                    guild = member.guild
                    role_id = self.config.get("role_mappings", {}).get(role_name)
                    if role_id:
                        role = guild.get_role(role_id)
                        if role:
                            # Retirer les rôles Valorant précédents
                            valorant_roles = [r for r in guild.roles if r.name in VALID_RANKS]
                            if valorant_roles:
                                await member.remove_roles(*valorant_roles, reason="Mise à jour du rang Valorant.")
                                logger.info(f"Rôles Valorant précédents retirés pour {member.name}.")
                            # Ajouter le nouveau rôle
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

    async def ask_confirmation(self, interaction: Any, message: str):
        view = ConfirmationView(interaction, None)
        await interaction.followup.send(message, view=view, ephemeral=True)
        await view.wait()
        return view.value

    @app_commands.command(name="refresh_rank", description="Forcer la mise à jour du rôle Valorant d'un utilisateur.")
    @app_commands.describe(user="Utilisateur à mettre à jour.")
    @is_admin()
    @enqueue_request()
    async def refresh_rank(self, interaction: Any, user: discord.Member):
        if not await self.ask_confirmation(interaction, f"Confirmez-vous la mise à jour du rôle Valorant pour {user.mention} ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)
        # Ici on suppose que vous avez un link valorant
        link_cog = self.bot.get_cog("LinkValorant")
        if link_cog:
            discord_user_id = str(user.id)
            valorant_username = link_cog.user_data.get(discord_user_id)
            if valorant_username:
                await self.assign_rank_role(user, valorant_username)
                await interaction.followup.send(f"Rôle Valorant mis à jour pour {user.mention}.", ephemeral=True)
            else:
                await interaction.followup.send(f"{user.mention} n'a pas de compte Valorant lié.", ephemeral=True)
        else:
            await interaction.followup.send("Le cog LinkValorant est introuvable.", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AssignRankRole(bot))
    logger.info("AssignRankRole Cog chargé avec succès.")
