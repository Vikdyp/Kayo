# cogs/admin_sync.py

import asyncpg
import discord
from discord.ext import commands
from discord import app_commands
import logging
from bot import cog_paths

from utils.database import database
from utils.request_manager import enqueue_request

logger = logging.getLogger('admin')

class AdminSync(commands.Cog):
    """Cog pour gérer la synchronisation et le rechargement des cogs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="dbstatus", description="Affiche l'état actuel du pool de connexions à la base de données.")
    @enqueue_request("URGENT")
    @app_commands.default_permissions(administrator=True)  # Restreindre aux administrateurs
    async def db_status(self, interaction: discord.Interaction):
        """Affiche l'état actuel du pool de connexions à la base de données."""
        try:
            if database.pool is None:
                status = "🔴 **Pool de connexions est fermé.**"
                await interaction.followup.send(status, ephemeral=True)
                logger.info("Statut de la DB : Pool fermé.")
                return

            # Vérifier si 'pool' est une instance d'asyncpg.Pool
            if not isinstance(database.pool, asyncpg.pool.Pool):
                status = "⚠️ **Le pool n'est pas une instance valide d'asyncpg.Pool.**"
                await interaction.followup.send(status, ephemeral=True)
                logger.warning("Le pool n'est pas une instance d'asyncpg.Pool.")
                return

            # Utiliser les anciennes méthodes disponibles:
            current_size = database.pool.get_size()
            idle_size = database.pool.get_idle_size()
            used = current_size - idle_size
            min_size = database.pool.get_min_size()
            max_size = database.pool.get_max_size()

            status = (
                f"🟢 **Pool de connexions est actif.**\n"
                f"**Min Size:** {min_size}\n"
                f"**Max Size:** {max_size}\n"
                f"**Connexions Utilisées:** {used}\n"
                f"**Connexions Inactives (Disponibles):** {idle_size}\n"
                f"**Connexions Totales:** {current_size}"
            )

            await interaction.followup.send(status, ephemeral=True)
            logger.info("Statut de la DB : Informations affichées.")

        except AttributeError as ae:
            # Gérer l'attribut manquant (dans le cas extrêmement improbable)
            status = "⚠️ **Le pool de connexions ne possède pas certains attributs attendus.**"
            await interaction.followup.send(status, ephemeral=True)
            logger.error(f"Erreur lors de l'obtention du statut du pool de connexions : {ae}")
        except Exception as e:
            logger.error(f"Erreur lors de l'obtention du statut du pool de connexions : {e}")
            await interaction.followup.send(f"Erreur : {e}", ephemeral=True)

    ### Ajout des commandes de rechargement des cogs ###

    @app_commands.command(name="reload_cog", description="Recharge un cog spécifique.")
    @app_commands.default_permissions(administrator=True)  # Restreindre aux administrateurs
    async def reload_cog(self, interaction: discord.Interaction, cog: str):
        """Recharge un cog spécifique."""
        logger = logging.getLogger('admin')

        # Vérification directe du chemin complet
        if cog not in cog_paths:
            await interaction.response.send_message(
                f"❌ Le cog `{cog}` n'est pas autorisé ou n'existe pas.", 
                ephemeral=True
            )
            logger.warning(f"Tentative de rechargement d'un cog non autorisé : {cog}")
            return

        try:
            await self.bot.reload_extension(cog)
            await interaction.response.send_message(f"✅ Le cog `{cog}` a été rechargé avec succès.", ephemeral=True)
            logger.info(f"Cog rechargé avec succès : {cog}")
        except commands.errors.ExtensionNotLoaded:
            try:
                await self.bot.load_extension(cog)
                await interaction.response.send_message(f"✅ Le cog `{cog}` a été chargé et rechargé avec succès.", ephemeral=True)
                logger.info(f"Cog chargé et rechargé avec succès : {cog}")
            except Exception as e:
                await interaction.response.send_message(f"❌ Erreur lors du chargement du cog `{cog}` : {e}", ephemeral=True)
                logger.error(f"Erreur lors du chargement du cog {cog} : {e}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors du rechargement du cog `{cog}` : {e}", ephemeral=True)
            logger.error(f"Erreur lors du rechargement du cog {cog} : {e}")

    @reload_cog.autocomplete("cog")
    async def reload_cog_autocomplete(self, interaction: discord.Interaction, current: str):
        """Propose des cogs disponibles pour l'autocomplétion."""

        # Conserver les chemins complets pour l'autocomplétion
        filtered = [
            cog for cog in cog_paths if current.lower() in cog.lower()
        ]
        return [
            app_commands.Choice(name=cog, value=cog) for cog in filtered
        ]

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminSync(bot))
    logger.info("AdminSync chargé.")
