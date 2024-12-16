#cogs\admin\admin.py
import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger('sync_commands')


class AdminSync(commands.Cog):
    """Cog pour gérer la synchronisation et le rechargement des cogs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    COG_CHOICES = [
        app_commands.Choice(name="Tous les Cogs", value="all"),
        app_commands.Choice(name="Roles Configuration", value="cogs.configuration.role_mappings_configuration"),
        app_commands.Choice(name="Channels Configuration", value="channels_configuration"),
        app_commands.Choice(name="Moderation", value="moderation"),
        # Ajoute d'autres Cogs ici selon ton projet
    ]

    @app_commands.command(name="sync", description="Synchronise ou recharge les cogs et commandes du bot.")
    @app_commands.describe(sync_only="Synchronise uniquement les commandes sans recharger les Cogs.")
    @app_commands.choices(target=COG_CHOICES)
    async def sync_commands(
        self,
        interaction: discord.Interaction,
        target: app_commands.Choice[str],
        sync_only: bool = False,
    ):
        """
        Permet de synchroniser les commandes slash, de recharger tous les Cogs ou un Cog spécifique.
        """
        try:
            if sync_only:
                # Synchronise uniquement les commandes
                synced = await self.bot.tree.sync()
                await interaction.response.send_message(
                    f"Commandes synchronisées avec succès : {len(synced)} commandes disponibles.", ephemeral=True
                )
                logger.info(f"Commandes synchronisées avec succès : {len(synced)}")
                return

            if target.value == "all":
                # Recharge tous les Cogs
                reloaded_cogs = []
                for cog in list(self.bot.extensions):
                    await self.bot.unload_extension(cog)
                    await self.bot.load_extension(cog)
                    reloaded_cogs.append(cog)
                synced = await self.bot.tree.sync()
                await interaction.response.send_message(
                    f"Tous les Cogs rechargés ({len(reloaded_cogs)}). Commandes synchronisées : {len(synced)}.",
                    ephemeral=True
                )
                logger.info(f"Tous les Cogs rechargés : {reloaded_cogs}. Commandes synchronisées.")
                return

            # Recharge un Cog spécifique
            cog_name = f"cogs.{target.value}"
            if cog_name in self.bot.extensions:
                await self.bot.unload_extension(cog_name)
                await self.bot.load_extension(cog_name)
                synced = await self.bot.tree.sync()
                await interaction.response.send_message(
                    f"Cog `{target.name}` rechargé avec succès. Commandes synchronisées : {len(synced)}.", ephemeral=True
                )
                logger.info(f"Cog `{target.name}` rechargé avec succès. Commandes synchronisées.")
            else:
                await interaction.response.send_message(
                    f"Le Cog `{target.name}` n'existe pas ou n'est pas chargé.", ephemeral=True
                )
                logger.warning(f"Tentative de recharger un Cog inexistant : {target.name}.")
        except Exception as e:
            logger.error(f"Erreur lors de la synchronisation ou du rechargement des Cogs : {e}")
            await interaction.response.send_message(
                f"Erreur : {e}", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminSync(bot))
    logger.info("AdminSync chargé.")
