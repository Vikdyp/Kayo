import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Dict, Optional

from utils.request_manager import enqueue_request
from utils.confirmation_view import ConfirmationView
from cogs.configuration.services.channel_service import ChannelService

logger = logging.getLogger('channels_configuration')


class ChannelsConfiguration(commands.Cog):
    """Cog pour gérer la configuration des salons."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config: Dict[str, int] = {}
        logger.info("ChannelsConfiguration initialisé.")

    PREDEFINED_ACTIONS = [
        ("demande-deban", "Demande de déban"),
        ("conflict", "Gestion des conflits"),
        ("teams_forum_id", "Forum de présentation des équipes"),
        ("inscription_tournament_channel_id", "Salon d'inscription aux tournois"),
        ("tournament_channel_id", "Salon des tournois"),
        ("fer", "Salon rang fer"),
        ("bronze", "Salon rang bronze"),
        ("argent", "Salon rang argent"),
        ("or", "Salon rang or"),
        ("platine", "Salon rang platine"),
        ("diamant", "Salon rang diamant"),
        ("ascendant", "Salon rang ascendant"),
        ("immortel", "Salon rang immortel"),
        ("radiant", "Salon rang radiant"),
    ]

    ACTION_CHOICES = [
        app_commands.Choice(name=description, value=action)
        for action, description in PREDEFINED_ACTIONS
    ]

    @app_commands.command(name="salon", description="Exécute des actions sur la configuration des salons.")
    @app_commands.describe(
        action="Action à effectuer",
        channel="Salon Discord (nécessaire pour 'set')"
    )
    @app_commands.choices(action=ACTION_CHOICES)
    @enqueue_request()
    async def channels_execute(
        self, 
        interaction: discord.Interaction, 
        action: app_commands.Choice[str], 
        channel: Optional[discord.TextChannel] = None
    ):
        """Exécute une action de configuration de salon en fonction de l'option spécifiée."""
        try:
            logger.debug(f"Execution de channels_execute avec action={action.value}, channel={channel}")

            if not interaction.guild:
                await interaction.followup.send(
                    "Cette commande doit être exécutée dans un serveur.", ephemeral=True
                )
                return

            action_lower = action.value.lower()

            if action_lower == "get":
                channels = await ChannelService.get_channels_config(interaction.guild.id)
                if not channels:
                    await interaction.followup.send("Aucun salon configuré.", ephemeral=True)
                    return

                embed = discord.Embed(title="Salons Configurés", color=discord.Color.green())
                for key, channel_id in channels.items():
                    guild_channel = interaction.guild.get_channel(channel_id)
                    display_name = self.get_action_display_name(key)
                    if guild_channel:
                        embed.add_field(name=display_name, value=guild_channel.mention, inline=False)
                    else:
                        embed.add_field(name=display_name, value="Salon non trouvé", inline=False)

                await interaction.followup.send(embed=embed, ephemeral=True)

            elif action_lower == "set":
                if not channel:
                    await interaction.followup.send(
                        "Veuillez spécifier un salon pour cette action.", ephemeral=True
                    )
                    return

                success = await ChannelService.set_channel_for_action(
                    interaction.guild.id, action_lower, channel.id
                )
                if success:
                    await interaction.followup.send(
                        f"Salon {channel.mention} configuré pour **{self.get_action_display_name(action_lower)}**.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "Une erreur est survenue lors de la configuration du salon.", ephemeral=True
                    )

            elif action_lower == "remove":
                channels = await ChannelService.get_channels_config(interaction.guild.id)
                if action_lower not in channels:
                    await interaction.followup.send(
                        f"Aucune configuration trouvée pour l'action **{self.get_action_display_name(action_lower)}**.",
                        ephemeral=True
                    )
                    return

                async def confirmation_callback(result: Optional[bool]):
                    if result is True:
                        success = await ChannelService.remove_channel_for_action(
                            interaction.guild.id, action_lower
                        )
                        if success:
                            await interaction.followup.send(
                                f"Configuration pour **{self.get_action_display_name(action_lower)}** supprimée.",
                                ephemeral=True
                            )
                        else:
                            await interaction.followup.send(
                                "Une erreur est survenue lors de la suppression.", ephemeral=True
                            )
                    elif result is False:
                        await interaction.followup.send("Suppression annulée.", ephemeral=True)
                    else:
                        await interaction.followup.send("Le délai de confirmation a expiré.", ephemeral=True)

                view = ConfirmationView(
                    interaction=interaction,
                    callback=confirmation_callback
                )
                await interaction.followup.send(
                    f"Êtes-vous sûr de vouloir supprimer la configuration pour **{self.get_action_display_name(action_lower)}** ?",
                    view=view,
                    ephemeral=True
                )

            else:
                await interaction.followup.send(
                    f"Action non prise en charge : **{self.get_action_display_name(action_lower)}**.",
                    ephemeral=True
                )
        except Exception as e:
            logger.exception(f"Erreur dans channels_execute pour action={action.value}: {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors de l'exécution de cette commande.", ephemeral=True
            )

    def get_action_display_name(self, action_key: str) -> str:
        """Retourne le nom affiché de l'action."""
        for key, description in self.PREDEFINED_ACTIONS:
            if key == action_key:
                return description
        return action_key.replace('_', ' ').capitalize()


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelsConfiguration(bot))
    logger.info("ChannelsConfiguration Cog chargé.")
