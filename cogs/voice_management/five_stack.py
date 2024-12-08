# cogs/voice_management/five_stack.py

import discord
from discord.ext import commands
from discord import app_commands  # Correction ici
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from cogs.utilities.utils import load_json, save_json

logger = logging.getLogger('discord.voice_management.five_stack')

class FiveStack(commands.Cog):
    """Cog pour la commande de création de salons vocaux temporaires pour 5 personnes maximum."""
    
    dependencies = ["cogs.voice_management.cleanup"]

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.config: Dict[str, Any] = {}
        self.tracked_channels: Dict[int, Dict[str, Any]] = {}
        self.allowed_text_channels: Dict[str, str] = {}
        self.roles_to_monitor: set = set()
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration depuis le fichier JSON."""
        self.config = await load_json(self.config_file)
        self.allowed_text_channels = self.config.get("allowed_text_channels", {})
        self.roles_to_monitor = set(self.config.get("roles_to_monitor", []))
        logger.info("FiveStack: Configuration chargée avec succès.")

    async def save_config(self) -> None:
        """Sauvegarde la configuration dans le fichier JSON."""
        self.config['allowed_text_channels'] = self.allowed_text_channels
        self.config['roles_to_monitor'] = list(self.roles_to_monitor)
        await save_json(self.config_file, self.config)
        logger.info("FiveStack: Configuration sauvegardée avec succès.")

    @app_commands.command(name="five_stack", description="Créer un salon vocal temporaire pour 5 personnes maximum")
    async def five_stack(self, interaction: discord.Interaction) -> None:
        """
        Crée un salon vocal temporaire pour l'utilisateur si les conditions sont remplies.
        
        Parameters:
            interaction (discord.Interaction): L'interaction de l'utilisateur.
        """
        channel_name = interaction.channel.name.lower()
        if channel_name not in self.allowed_text_channels:
            await interaction.response.send_message(
                "Cette commande doit être envoyée dans un salon texte autorisé (fer, bronze, argent, or, platine, diamant, ascendant, immortel).",
                ephemeral=True
            )
            logger.warning(f"Utilisateur {interaction.user} a tenté d'utiliser /five_stack dans un salon non autorisé: {interaction.channel.name}")
            return

        role_name = self.allowed_text_channels[channel_name]
        role_id = self.config.get("role_mappings", {}).get(role_name)
        if not role_id:
            await interaction.response.send_message(
                f"Aucun mapping de rôle trouvé pour `{role_name}`. Veuillez contacter un administrateur.",
                ephemeral=True
            )
            logger.error(f"Aucun mapping de rôle trouvé pour `{role_name}`")
            return

        guild = interaction.guild
        role = guild.get_role(role_id)
        if not role:
            await interaction.response.send_message(
                f"Le rôle `{role_name}` n'a pas été trouvé sur ce serveur. Veuillez contacter un administrateur.",
                ephemeral=True
            )
            logger.error(f"Rôle `{role_name}` avec ID {role_id} introuvable sur le serveur.")
            return

        existing_channel = None
        user_roles = {role.name for role in interaction.user.roles}
        for channel in guild.voice_channels:
            if channel.name.endswith("'s Channel") and role in channel.overwrites:
                channel_roles = {role.name for member in channel.members for role in member.roles}
                if self.roles_to_monitor.intersection(user_roles) and not self.roles_to_monitor.intersection(channel_roles):
                    existing_channel = channel
                    break

        if existing_channel:
            try:
                if interaction.user.voice:
                    await interaction.user.move_to(existing_channel)
                    await interaction.response.send_message(
                        f"Vous avez été déplacé vers le salon vocal existant : {existing_channel.name}",
                        ephemeral=True
                    )
                    logger.info(f"{interaction.user} déplacé vers le salon existant {existing_channel.name}")
                else:
                    await interaction.response.send_message(
                        "Vous devez être dans un salon vocal pour utiliser cette commande.",
                        ephemeral=True
                    )
                    logger.info(f"{interaction.user} a tenté de rejoindre {existing_channel.name} sans être dans un salon vocal.")
            except discord.Forbidden:
                await interaction.response.send_message(
                    "Le bot n'a pas les permissions nécessaires pour déplacer l'utilisateur.",
                    ephemeral=True
                )
                logger.error(f"Permission refusée pour déplacer {interaction.user} vers {existing_channel.name}.")
            except discord.HTTPException as e:
                await interaction.response.send_message(
                    f"Une erreur s'est produite lors du déplacement vers le salon vocal : {e}",
                    ephemeral=True
                )
                logger.error(f"Erreur HTTP lors du déplacement de {interaction.user} vers {existing_channel.name}: {e}")
        else:
            voice_channel_name = f"{interaction.user.name}'s Channel"
            try:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(connect=False),
                    role: discord.PermissionOverwrite(connect=True, speak=True),
                    interaction.user: discord.PermissionOverwrite(connect=True, speak=True)
                }

                voice_channel = await guild.create_voice_channel(
                    voice_channel_name,
                    user_limit=self.config.get("max_members_per_channel", 5),
                    overwrites=overwrites
                )

                invite = await voice_channel.create_invite(max_age=3600, max_uses=5)
                logger.info(f"Salon vocal créé: {voice_channel.name}, Invitation: {invite.url}")

                await interaction.response.send_message(
                    f"Salon vocal créé : **{voice_channel.name}**\nVoici le lien d'invitation : {invite.url}",
                    ephemeral=True
                )

                # Obtenir le cog VoiceChannelCleanup pour ajouter le salon suivi
                cleanup_cog = self.bot.get_cog("VoiceChannelCleanup")
                if cleanup_cog:
                    await cleanup_cog.add_tracked_channel(voice_channel, interaction.original_response())
                else:
                    logger.error("VoiceChannelCleanup Cog non trouvé. Impossible d'ajouter le salon aux salons suivis.")

            except discord.Forbidden:
                await interaction.response.send_message(
                    "Le bot n'a pas les permissions nécessaires pour créer un salon vocal.",
                    ephemeral=True
                )
                logger.error("Permission refusée pour créer un salon vocal.")
            except discord.HTTPException as e:
                await interaction.response.send_message(
                    f"Une erreur s'est produite lors de la création du salon vocal : {e}",
                    ephemeral=True
                )
                logger.error(f"Erreur HTTP lors de la création du salon vocal: {e}")

async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog FiveStack au bot."""
    await bot.add_cog(FiveStack(bot))
    logger.info("FiveStack Cog chargé avec succès.")
