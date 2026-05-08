# cogs/moderation/views/spam_confirmation_view.py
"""Discord view used to confirm cross-channel spam alerts."""

from __future__ import annotations

import logging
from datetime import datetime

import discord
from discord.ext import commands

from cogs.moderation.discord_actions import (
    apply_ban_role_all_guilds,
    collect_restorable_role_ids,
)
from cogs.moderation.services.moderation_service import ModerationService


logger = logging.getLogger(__name__)


class SpamConfirmationView(discord.ui.View):
    """Vue avec boutons pour confirmer ou ignorer un spam détecté."""

    def __init__(
        self,
        bot: commands.Bot,
        user: discord.Member,
        message_refs: list[tuple[int, int]],
        content: str,
        guild: discord.Guild,
        moderation_service: ModerationService,
        timeout: float = 3600,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.user = user
        self.message_refs = message_refs
        self.content = content
        self.guild = guild
        self._mod_svc = moderation_service
        self.resolved = False

    @discord.ui.button(label="Bannir", style=discord.ButtonStyle.danger, emoji="🔨")
    async def ban_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Bannit l'utilisateur et supprime ses messages."""
        if self.resolved:
            await interaction.response.send_message(
                "Cette action a déjà été traitée.",
                ephemeral=True,
            )
            return

        self.resolved = True
        await interaction.response.defer()

        deleted_count = 0
        for channel_id, msg_id in self.message_refs:
            try:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    msg = await channel.fetch_message(msg_id)
                    await msg.delete()
                    deleted_count += 1
            except discord.NotFound:
                pass
            except discord.Forbidden:
                logger.warning(
                    "Pas de permission pour supprimer le message %s dans %s",
                    msg_id,
                    channel_id,
                )
            except Exception as exc:
                logger.error("Erreur lors de la suppression du message %s: %s", msg_id, exc)

        try:
            roles_to_backup = collect_restorable_role_ids(self.user)

            if roles_to_backup:
                await self._mod_svc.update_roles_backup(
                    guild_id=self.guild.id,
                    guild_name=self.guild.name,
                    discord_user_id=self.user.id,
                    roles=roles_to_backup,
                )

            await self._mod_svc.add_ban(
                guild_id=self.guild.id,
                guild_name=self.guild.name,
                user_id=self.user.id,
                ban_type="perm",
                reason="Spam multi-salons détecté (confirmé par modérateur)",
                banned_by=interaction.user.id,
                ban_end=None,
            )

            await apply_ban_role_all_guilds(
                self.bot,
                self._mod_svc,
                self.user.id,
                "Spam multi-salons détecté",
                source_member=self.user,
            )

            try:
                embed = discord.Embed(
                    title="📛 Vous avez été banni(e)",
                    description="Vous avez été banni(e) pour spam multi-salons.",
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow(),
                )
                embed.add_field(name="Serveur", value=self.guild.name, inline=False)
                embed.add_field(name="Raison", value="Spam multi-salons détecté", inline=False)
                await self.user.send(embed=embed)
            except discord.Forbidden:
                pass

            embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if embed:
                embed.color = discord.Color.red()
                embed.add_field(
                    name="✅ Action effectuée",
                    value=(
                        f"Banni par {interaction.user.mention}\n"
                        f"{deleted_count} message(s) supprimé(s)"
                    ),
                    inline=False,
                )

            for item in self.children:
                item.disabled = True

            await interaction.message.edit(embed=embed, view=self)
            logger.info(
                "Spam confirmé: %s banni par %s",
                self.user.display_name,
                interaction.user.display_name,
            )

        except Exception as exc:
            logger.exception("Erreur lors du ban pour spam: %s", exc)
            await interaction.followup.send(
                f"Erreur lors du bannissement: {exc}",
                ephemeral=True,
            )

    @discord.ui.button(label="Ignorer", style=discord.ButtonStyle.secondary, emoji="❌")
    async def ignore_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """Ignore l'alerte et ajoute l'utilisateur a une whitelist temporaire."""
        if self.resolved:
            await interaction.response.send_message(
                "Cette action a déjà été traitée.",
                ephemeral=True,
            )
            return

        self.resolved = True
        await interaction.response.defer()

        automod_cog = self.bot.get_cog("AutoMod")
        if automod_cog:
            automod_cog.add_to_spam_whitelist(self.user.id, self.guild.id)

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.color = discord.Color.light_grey()
            embed.add_field(
                name="❌ Ignoré",
                value=f"Ignoré par {interaction.user.mention}\nUtilisateur en whitelist pour 24h",
                inline=False,
            )

        for item in self.children:
            item.disabled = True

        await interaction.message.edit(embed=embed, view=self)
        logger.info(
            "Spam ignoré pour %s par %s",
            self.user.display_name,
            interaction.user.display_name,
        )

    async def on_timeout(self) -> None:
        """Called when the confirmation view expires."""
        if not self.resolved:
            logger.info("Vue de confirmation spam expirée pour %s", self.user.display_name)
