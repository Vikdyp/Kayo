# cogs/ranking/conflict_resolution.py

import discord
from discord.ext import commands
from discord import app_commands
import logging

from cogs.utilities.utils import load_json, save_json

logger = logging.getLogger('discord.ranking.conflict_resolution')


class ConflictResolution(commands.Cog):
    """Cog pour gérer la résolution des conflits de liaison de compte Valorant."""

    dependencies = []

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = 'data/config.json'
        self.config = {}
        self.bot.loop.create_task(self.load_config())

    async def load_config(self) -> None:
        """Charge la configuration depuis le fichier JSON."""
        self.config = await load_json(self.config_file)
        logger.info("ConflictResolution: Configuration chargée avec succès.")

    async def save_config(self) -> None:
        """Sauvegarde la configuration dans le fichier JSON."""
        await save_json(self.config, self.config_file)
        logger.info("ConflictResolution: Configuration sauvegardée avec succès.")

    async def handle_conflict(self, selected_user_id: str, other_user_id: str, valorant_username: str) -> None:
        """
        Crée un message dans le canal de conflit avec des réactions pour la résolution.

        Parameters:
            selected_user_id (str): ID du premier utilisateur Discord.
            other_user_id (str): ID du second utilisateur Discord.
            valorant_username (str): Nom d'utilisateur Valorant en conflit.
        """
        logger.info(
            f"Résolution de conflit pour le pseudo Valorant {valorant_username} entre {selected_user_id} et {other_user_id}."
        )
        guild = self.bot.guilds[0] if self.bot.guilds else None
        if not guild:
            logger.error("Guild non trouvée lors de la résolution de conflit.")
            return

        conflict_channel_id = self.config.get("channels", {}).get("conflict")
        if not conflict_channel_id:
            logger.error("ID du canal de conflit non configuré.")
            return

        conflict_channel = guild.get_channel(conflict_channel_id)
        if not conflict_channel:
            logger.error(f"Le canal de conflit avec l'ID {conflict_channel_id} n'a pas été trouvé.")
            return

        try:
            conflict_message = await conflict_channel.send(
                f"Conflit détecté pour le pseudo Valorant `{valorant_username}` entre <@{selected_user_id}> et <@{other_user_id}>.\n"
                f"Réagissez avec ✅ pour attribuer le pseudo à <@{selected_user_id}> ou ❌ pour l'attribuer à <@{other_user_id}>."
            )
            await conflict_message.add_reaction("✅")
            await conflict_message.add_reaction("❌")
            logger.info(f"Message de conflit envoyé dans {conflict_channel.name}")
        except Exception as e:
            logger.exception(f"Erreur lors de l'envoi du message de conflit dans {conflict_channel.name}: {e}")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User) -> None:
        """
        Gère les réactions pour la résolution des conflits.

        Parameters:
            reaction (discord.Reaction): Réaction ajoutée.
            user (discord.User): Utilisateur ayant ajouté la réaction.
        """
        if user.bot:
            return

        conflict_channel_id = self.config.get("channels", {}).get("conflict")
        if reaction.message.channel.id != conflict_channel_id:
            return

        if reaction.emoji not in ["✅", "❌"]:
            return

        if len(reaction.message.mentions) < 2:
            logger.warning("Moins de deux utilisateurs mentionnés dans le message de conflit.")
            return

        user1_id = str(reaction.message.mentions[0].id)
        user2_id = str(reaction.message.mentions[1].id)
        valorant_username = reaction.message.channel.name.replace("conflit-", "").replace("-", "#")

        if reaction.emoji == "✅":
            # Choisir user1
            await self.handle_conflict_resolution(user1_id, user2_id, valorant_username)
        elif reaction.emoji == "❌":
            # Choisir user2
            await self.handle_conflict_resolution(user2_id, user1_id, valorant_username)

        # Supprimer les réactions après la résolution
        try:
            await reaction.message.clear_reactions()
            logger.info("Réactions supprimées après résolution de conflit.")
        except Exception as e:
            logger.exception(f"Erreur lors de la suppression des réactions: {e}")

    async def handle_conflict_resolution(
        self,
        selected_user_id: str,
        other_user_id: str,
        valorant_username: str
    ) -> None:
        """
        Attribue le pseudo Valorant à l'utilisateur sélectionné et enlève les données des autres.

        Parameters:
            selected_user_id (str): ID de l'utilisateur sélectionné.
            other_user_id (str): ID de l'utilisateur non sélectionné.
            valorant_username (str): Nom d'utilisateur Valorant en conflit.
        """
        try:
            # Attribuer le pseudo à l'utilisateur sélectionné
            selected_member = guild.get_member(int(selected_user_id)) if (guild := self.bot.guilds[0] if self.bot.guilds else None) else None
            if selected_member:
                await self.bot.get_cog("AssignRankRole").assign_rank_role(selected_member, valorant_username)
                logger.info(f"Pseudo Valorant `{valorant_username}` attribué à {selected_member.name}.")

            # Enlever le lien pour l'autre utilisateur
            link_cog = self.bot.get_cog("LinkValorant")
            if link_cog and other_user_id in link_cog.user_data:
                del link_cog.user_data[other_user_id]
                await link_cog.save_all_data()
                logger.info(f"Liaison de compte Valorant supprimée pour l'utilisateur ID {other_user_id}.")

            # Optionnel : Informer les utilisateurs
            if selected_member:
                try:
                    await selected_member.send(
                        f"Votre pseudo Valorant `{valorant_username}` a été confirmé et attribué avec succès."
                    )
                    logger.info(f"Message de confirmation envoyé à {selected_member.name}.")
                except Exception as e:
                    logger.exception(f"Erreur lors de l'envoi du message de confirmation à {selected_member.name}: {e}")

            other_member = guild.get_member(int(other_user_id)) if (guild := self.bot.guilds[0] if self.bot.guilds else None) else None
            if other_member:
                try:
                    await other_member.send(
                        f"Votre tentative de lier le pseudo Valorant `{valorant_username}` a échoué en raison d'un conflit."
                    )
                    logger.info(f"Message d'échec envoyé à {other_member.name}.")
                except Exception as e:
                    logger.exception(f"Erreur lors de l'envoi du message d'échec à {other_member.name}: {e}")

        except Exception as e:
            logger.exception(f"Erreur lors de la résolution du conflit pour {valorant_username}: {e}")


async def setup(bot: commands.Bot) -> None:
    """Ajoute le Cog ConflictResolution au bot."""
    await bot.add_cog(ConflictResolution(bot))
    logger.info("ConflictResolution Cog chargé avec succès.")
