import asyncpg
import discord
from discord.ext import commands
from discord import app_commands
import logging
from bot import cog_paths

from utils.database import database

logger = logging.getLogger(__name__)

class AdminSync(commands.Cog):
    """Cog pour gérer la synchronisation et le rechargement des cogs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="dbstatus", description="Affiche l'état actuel du pool de connexions à la base de données.")
    @app_commands.default_permissions(administrator=True)  # Restreindre aux administrateurs
    async def db_status(self, interaction: discord.Interaction):
        """Affiche l'état actuel du pool de connexions à la base de données."""
        try:
            await interaction.response.defer(thinking=True)
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

    ### Ajout des commandes dynamiques pour gérer les cogs ###

    @app_commands.command(name="manage_cogs", description="Gère les cogs dynamiquement (load, reload, unload).")
    @app_commands.default_permissions(administrator=True)  # Restreindre aux administrateurs
    async def manage_cog(self, interaction: discord.Interaction, action: str, cog: str):
        """Gère les cogs dynamiquement."""
        logger = logging.getLogger('admin')

        if action not in ["load", "reload", "unload", "check"]:
            await interaction.response.send_message(
                "❌ Action invalide. Utilisez `load`, `reload`, ou `unload`.", ephemeral=True
            )
            return
        
        #decommenter si besoin
        #if cog not in cog_paths:
            await interaction.response.send_message(
                f"❌ Le cog `{cog}` n'est pas autorisé ou n'existe pas.", 
                ephemeral=True
            )
            logger.warning(f"Tentative de gestion d'un cog non autorisé : {cog}")
            return

        try:
            if action == "load":
                await self.bot.load_extension(cog)
                await interaction.response.send_message(f"✅ Le cog `{cog}` a été chargé avec succès.", ephemeral=True)
                logger.info(f"Cog chargé avec succès : {cog}")

            elif action == "reload":
                await self.bot.reload_extension(cog)
                await interaction.response.send_message(f"✅ Le cog `{cog}` a été rechargé avec succès.", ephemeral=True)
                logger.info(f"Cog rechargé avec succès : {cog}")

            elif action == "unload":
                await self.bot.unload_extension(cog)
                await interaction.response.send_message(f"✅ Le cog `{cog}` a été déchargé avec succès.", ephemeral=True)
                logger.info(f"Cog déchargé avec succès : {cog}")

            elif action == "check":
                cog_statuses = []
                for cog_path in cog_paths:
                    if cog_path in self.bot.extensions:
                        cog_statuses.append(f"✅ {cog_path}")
                    else:
                        cog_statuses.append(f"❌ {cog_path}")

                if cog_statuses:
                    await interaction.response.send_message(
                        f"**Statut des Cogs :**\n- " + "\n- ".join(cog_statuses),
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message("Aucun cog autorisé n'a été trouvé.", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors de l'action `{action}` sur le cog `{cog}` : {e}", ephemeral=True)
            logger.error(f"Erreur lors de l'action `{action}` sur le cog `{cog}` : {e}")

    @manage_cog.autocomplete("action")
    async def manage_cog_action_autocomplete(self, interaction: discord.Interaction, current: str):
        """Propose les actions disponibles pour la commande manage_cog."""
        actions = ["load", "reload", "unload", "check"]
        return [
            app_commands.Choice(name=action, value=action) for action in actions if current.lower() in action.lower()
        ]

    @manage_cog.autocomplete("cog")
    async def manage_cog_cog_autocomplete(self, interaction: discord.Interaction, current: str):
        """Propose des cogs disponibles pour l'autocomplétion."""
        filtered = [
            cog for cog in cog_paths if current.lower() in cog.lower()
        ]
        return [
            app_commands.Choice(name=cog, value=cog) for cog in filtered
        ]
    

    @app_commands.command(name="sync_commands", description="Synchronise les commandes slash avec Discord.")
    @app_commands.default_permissions(administrator=True)  # Restreindre aux administrateurs
    async def sync_commands(self, interaction: discord.Interaction):
        """Synchronise les commandes slash avec Discord."""
        try:
            # Synchroniser globalement
            synced = await self.bot.tree.sync()
            await interaction.response.send_message(
                f"✅ Commandes synchronisées globalement : {len(synced)} commandes mises à jour.", ephemeral=True
            )
            logger.info(f"{len(synced)} commandes synchronisées globalement.")
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Une erreur est survenue lors de la synchronisation : {e}", ephemeral=True
            )
            logger.error(f"Erreur lors de la synchronisation des commandes : {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminSync(bot))
    logger.info("AdminSync chargé.")
