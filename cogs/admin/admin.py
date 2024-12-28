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

        # Liste des chemins de cogs autorisés
        cog_paths = [
            'cogs.configuration.channels_configuration',
            'cogs.configuration.role_mappings_configuration',
            'cogs.moderation.clean',
            'cogs.admin.admin',
            'cogs.moderation.moderation',
            'cogs.file_counter.file_counter',
            'cogs.accueil.accueil',
            'cogs.role_management.game_role',
            'cogs.ranking.assign_rank',
            'cogs.rules.rules',
            'cogs.moderation.unban_requests',
            'cogs.admin_sync',  # Inclure ce cog pour permettre son propre rechargement
        ]

        # Vérifier si le cog spécifié est dans la liste autorisée
        if cog not in [path.split('.')[-1] for path in cog_paths]:
            await interaction.response.send_message(
                f"❌ Le cog `{cog}` n'est pas autorisé ou n'existe pas.", 
                ephemeral=True
            )
            logger.warning(f"Tentative de rechargement d'un cog non autorisé : {cog}")
            return

        cog_full_path = f"cogs.{cog}" if not cog.startswith("cogs.") else cog

        try:
            await self.bot.reload_extension(cog_full_path)
            await interaction.response.send_message(f"✅ Le cog `{cog}` a été rechargé avec succès.", ephemeral=True)
            logger.info(f"Cog rechargé avec succès : {cog_full_path}")
        except commands.errors.ExtensionNotLoaded:
            try:
                await self.bot.load_extension(cog_full_path)
                await interaction.response.send_message(f"✅ Le cog `{cog}` a été chargé et rechargé avec succès.", ephemeral=True)
                logger.info(f"Cog chargé et rechargé avec succès : {cog_full_path}")
            except Exception as e:
                await interaction.response.send_message(f"❌ Erreur lors du chargement du cog `{cog}` : {e}", ephemeral=True)
                logger.error(f"Erreur lors du chargement du cog {cog_full_path} : {e}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors du rechargement du cog `{cog}` : {e}", ephemeral=True)
            logger.error(f"Erreur lors du rechargement du cog {cog_full_path} : {e}")

    @app_commands.command(name="reload_all_cogs", description="Recharge tous les cogs.")
    @app_commands.default_permissions(administrator=True)  # Restreindre aux administrateurs
    async def reload_all_cogs(self, interaction: discord.Interaction):
        """Recharge tous les cogs."""
        logger = logging.getLogger('admin')

        success_reloads = []
        failed_reloads = []

        for cog_path in cog_paths:
            try:
                await self.bot.reload_extension(cog_path)
                success_reloads.append(cog_path)
                logger.info(f"Cog rechargé avec succès : {cog_path}")
            except commands.errors.ExtensionNotLoaded:
                try:
                    await self.bot.load_extension(cog_path)
                    success_reloads.append(cog_path)
                    logger.info(f"Cog chargé et rechargé avec succès : {cog_path}")
                except Exception as e:
                    failed_reloads.append((cog_path, str(e)))
                    logger.error(f"Erreur lors du chargement du cog {cog_path} : {e}")
            except Exception as e:
                failed_reloads.append((cog_path, str(e)))
                logger.error(f"Erreur lors du rechargement du cog {cog_path} : {e}")

        # Préparer le message de réponse
        embed = discord.Embed(title="Rechargement des Cogs", color=discord.Color.blue())
        if success_reloads:
            embed.add_field(
                name="✅ Succès",
                value="\n".join([f"`{cog}`" for cog in success_reloads]),
                inline=False
            )
        if failed_reloads:
            embed.add_field(
                name="❌ Échecs",
                value="\n".join([f"`{cog}` : {error}" for cog, error in failed_reloads]),
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    ### Fin des commandes de rechargement ###

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminSync(bot))
    logger.info("AdminSync chargé.")
