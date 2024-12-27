# cogs/admin_sync.py

import asyncpg
import discord
from discord.ext import commands
from discord import app_commands
import logging

from utils.database import database
from utils.request_manager import enqueue_request

logger = logging.getLogger('admin')

class AdminSync(commands.Cog):
    """Cog pour gérer la synchronisation et le rechargement des cogs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    COG_CHOICES = [
        app_commands.Choice(name="Tous les Cogs", value="all"),
        app_commands.Choice(name="Reconnexion à la base de données", value="reconnect_db"),
    ]

    @app_commands.command(name="sync", description="Synchronise ou recharge les cogs et commandes du bot.")
    @app_commands.describe(
        target="Le Cog à recharger, tous les cogs, ou une autre action.",
        sync_only="Synchroniser uniquement les commandes sans recharger les cogs."
    )
    @app_commands.choices(target=COG_CHOICES)
    @enqueue_request("URGENT")
    @app_commands.default_permissions(administrator=True)  # Restreindre aux administrateurs
    async def sync_commands(
        self,
        interaction: discord.Interaction,
        target: app_commands.Choice[str],
        sync_only: bool = False,
    ):
        """Synchronise les commandes slash ou recharge les cogs."""
        try:
            if sync_only:
                # Synchroniser uniquement les commandes
                synced = await self.bot.tree.sync()
                await interaction.followup.send(
                    f"Commandes synchronisées : {len(synced)} commandes disponibles.", ephemeral=True
                )
                logger.info(f"Commandes synchronisées avec succès : {len(synced)}")
                return

            if target.value == "reconnect_db":
                # Reconnexion à la base de données
                try:
                    await database.ensure_connected()  # Appel sur l'instance 'database'
                    await interaction.followup.send(
                        "Connexion à la base de données vérifiée et restaurée avec succès.", ephemeral=True
                    )
                    logger.info("Reconnexion à la base de données effectuée avec succès.")
                except Exception as e:
                    await interaction.followup.send(
                        f"Échec de la reconnexion à la base de données : {e}", ephemeral=True
                    )
                    logger.error(f"Erreur lors de la reconnexion à la base de données : {e}")
                return  # Évitez d'aller plus loin, car ce n'est pas un cog.

            if target.value == "all":
                # Recharger tous les Cogs
                reloaded_cogs = []
                for cog in list(self.bot.extensions):
                    try:
                        await self.bot.unload_extension(cog)
                        await self.bot.load_extension(cog)
                        reloaded_cogs.append(cog)
                    except commands.errors.ExtensionAlreadyLoaded:
                        logger.warning(f'Cog déjà chargé: {cog}')
                    except commands.errors.ExtensionNotFound:
                        logger.error(f'Cog non trouvé: {cog}')
                    except commands.errors.NoEntryPointError:
                        logger.error(f'Pas de fonction setup dans le cog: {cog}')
                    except Exception as e:
                        logger.exception(f'Erreur lors du rechargement du cog {cog}: {e}')
                synced = await self.bot.tree.sync()
                await interaction.followup.send(
                    f"Tous les Cogs rechargés ({len(reloaded_cogs)}). Commandes synchronisées : {len(synced)}.",
                    ephemeral=True
                )
                logger.info(f"Tous les Cogs rechargés : {reloaded_cogs}. Commandes synchronisées.")
                return

        except Exception as e:
            logger.error(f"Erreur lors de la synchronisation ou du rechargement des Cogs : {e}")
            await interaction.followup.send(f"Erreur : {e}", ephemeral=True)

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


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminSync(bot))
    logger.info("AdminSync chargé.")
