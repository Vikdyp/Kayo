# cogs/configuration/channels_configuration.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Dict, List, Optional

from utils.confirmation_view import ConfirmationView
# On importe le nouveau service combiné
from cogs.configuration.services.channel_service import ServerChannelService

logger = logging.getLogger(__name__)

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
        ("welcome", "Salon d'acceuil"),
        ("stat_embed", "Salon embed statistiques"),
        ("rules", "Salon des regle du serveur"),
        ("introductions", "salon pour la presentation du serveur"),
        ("modération", "salon de modération"),
        ("rang", "salon pour definir les rang"),
        ("twitch", "salon des notif twitch"),
        ("valorant_shop", "Salon des shops Valorant"),
        ("temp_vocal_category", "Categorie des vocaux temporaires"),
        ("temp_vocal_lobby", "Salon lobby vocal (creation VC)"),
        ("voice_cleaner_category", "Categorie nettoyee (voice cleaner)"),
        ("voice_cleaner_afk", "Salon AFK a exclure (voice cleaner)"),
        ("matchmaking_voice_category", "Categorie vocale matchmaking"),
        ("deban_category", "Categorie des demande de deban"),
        ("rank_up", "Salon de notif de rang"),
    ]

    ACTION_CHOICES = [
        app_commands.Choice(name="Afficher ce qu'il manque", value="status"),
        app_commands.Choice(name="Afficher les salons configurés", value="get"),
        app_commands.Choice(name="Configurer un salon", value="set"),
        app_commands.Choice(name="Supprimer un salon", value="remove")
    ]

    @app_commands.command(name="salon", description="Gérer la configuration des salons.")
    @app_commands.describe(
        action="Action à effectuer",
        salon_action="Type de salon à gérer",
        channel="Salon Discord (nécessaire pour 'set')"
    )
    @app_commands.choices(action=ACTION_CHOICES)
    @app_commands.default_permissions(administrator=True)
    async def channels_execute(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        salon_action: Optional[str] = None,
        channel: Optional[discord.abc.GuildChannel] = None
    ):
        """Exécute une action de configuration de salon en fonction de l'option spécifiée."""
        try:
            await interaction.response.defer(thinking=True)
            logger.debug(f"Execution de channels_execute avec action={action.value}, salon_action={salon_action}, channel={channel}")

            if not interaction.guild:
                await interaction.followup.send(
                    "Cette commande doit être exécutée dans un serveur.", ephemeral=True
                )
                return

            guild_id = interaction.guild.id
            guild_name = interaction.guild.name

            action_lower = action.value.lower()

            # =========== GET ===========
            if action_lower == "get":
                channels = await ServerChannelService.get_channels_config(guild_id, guild_name)
                embed = self.build_channels_status_embed(interaction.guild, channels)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
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

            # =========== STATUS ===========
            elif action_lower == "status":
                channels = await ServerChannelService.get_channels_config(guild_id, guild_name)
                embed = self.build_channels_status_embed(interaction.guild, channels)
                await interaction.followup.send(embed=embed, ephemeral=True)

            # =========== SET ===========
            elif action_lower == "set":
                if not salon_action or not channel:
                    await interaction.followup.send(
                        "Veuillez spécifier le type de salon (`salon_action`) et un salon Discord (`channel`).", 
                        ephemeral=True
                    )
                    return

                success = await ServerChannelService.set_channel_for_action(
                    guild_id, guild_name, salon_action, channel.id
                )
                if success:
                    await interaction.followup.send(
                        f"Salon {channel.mention} configuré pour **{self.get_action_display_name(salon_action)}**.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "Une erreur est survenue lors de la configuration du salon.", ephemeral=True
                    )

            # =========== REMOVE ===========
            elif action_lower == "remove":
                if not salon_action:
                    await interaction.followup.send(
                        "Veuillez spécifier le type de salon (`salon_action`) à supprimer.", ephemeral=True
                    )
                    return

                channels = await ServerChannelService.get_channels_config(guild_id, guild_name)
                if salon_action not in channels:
                    await interaction.followup.send(
                        f"Aucune configuration trouvée pour **{self.get_action_display_name(salon_action)}**.",
                        ephemeral=True
                    )
                    return

                # Confirmation pour la suppression
                async def confirmation_callback(result: Optional[bool]):
                    if result is True:
                        success = await ServerChannelService.remove_channel_for_action(
                            guild_id, guild_name, salon_action
                        )
                        if success:
                            await interaction.followup.send(
                                f"Configuration pour **{self.get_action_display_name(salon_action)}** supprimée.",
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
                    f"Êtes-vous sûr de vouloir supprimer la configuration pour **{self.get_action_display_name(salon_action)}** ?",
                    view=view,
                    ephemeral=True
                )

            else:
                await interaction.followup.send(
                    f"Action non prise en charge : **{action.value}**.",
                    ephemeral=True
                )

        except Exception as e:
            logger.exception(f"Erreur dans channels_execute pour action={action.value}: {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors de l'exécution de cette commande.", ephemeral=True
            )

    def build_channels_status_embed(
        self, guild: discord.Guild, channels: Optional[Dict[str, int]]
    ) -> discord.Embed:
        channels = channels or {}
        missing_actions = [key for key, _ in self.PREDEFINED_ACTIONS if key not in channels]

        embed = discord.Embed(title="Configuration des salons", color=discord.Color.green())
        configured_text = self.format_configured_channels(guild, channels) or "Aucun salon configure."
        missing_text = self.format_missing_actions(missing_actions) or "Rien a configurer."

        embed.add_field(name=f"Configures ({len(channels)})", value=configured_text, inline=False)
        embed.add_field(name=f"A configurer ({len(missing_actions)})", value=missing_text, inline=False)
        embed.add_field(
            name="Astuce",
            value="`/salon action:set salon_action:<cle> channel:<salon>`",
            inline=False,
        )
        return embed

    def format_configured_channels(self, guild: discord.Guild, channels: Dict[str, int]) -> str:
        lines: List[str] = []
        for key in sorted(channels.keys()):
            channel_id = channels[key]
            display_name = self.get_action_display_name(key)
            guild_channel = guild.get_channel(channel_id)
            if guild_channel:
                lines.append(f"- {display_name} (`{key}`): {guild_channel.mention}")
            else:
                lines.append(f"- {display_name} (`{key}`): salon non trouve")
        return self.truncate_lines(lines)

    def format_missing_actions(self, missing_actions: List[str]) -> str:
        lines = [f"- {self.get_action_display_name(key)} (`{key}`)" for key in missing_actions]
        return self.truncate_lines(lines)

    def truncate_lines(self, lines: List[str], limit: int = 1024) -> str:
        if not lines:
            return ""
        output: List[str] = []
        total = 0
        for line in lines:
            line_len = len(line) + (1 if output else 0)
            if total + line_len > limit - 40:
                remaining = len(lines) - len(output)
                output.append(f"... +{remaining} autres")
                break
            output.append(line)
            total += line_len
        return "\n".join(output)

    def get_action_display_name(self, action_key: str) -> str:
        """Retourne le nom affiché de l'action."""
        for key, description in self.PREDEFINED_ACTIONS:
            if key == action_key:
                return description
        return action_key.replace('_', ' ').capitalize()

    @channels_execute.autocomplete('salon_action')
    async def salon_action_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """
        Propose des actions connues, sans limiter les actions personnalisées.
        """
        current_lower = current.lower()
        matches: List[app_commands.Choice[str]] = []
        for action, description in self.PREDEFINED_ACTIONS:
            if current_lower in action.lower() or current_lower in description.lower():
                matches.append(app_commands.Choice(name=description, value=action))
        return matches[:25]


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelsConfiguration(bot))
    logger.info("ChannelsConfiguration Cog chargé.")
