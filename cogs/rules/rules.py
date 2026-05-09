from __future__ import annotations

import logging

import discord
from discord.ext import commands

from cogs.rules.presenters import build_rules_embed
from cogs.rules.services import RulesService
from cogs.rules.views import AcceptRulesView

logger = logging.getLogger(__name__)


class RulesCog(commands.Cog):
    """Rules message and acceptance workflow."""

    def __init__(self, bot: commands.Bot, rules_service: RulesService) -> None:
        self.bot = bot
        self._service = rules_service
        self.bot.add_view(AcceptRulesView(self))
        logger.info("RulesCog initialized.")

    @commands.command(name="setup_rules")
    @commands.has_permissions(administrator=True)
    async def setup_rules(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await ctx.send("Cette commande doit etre executee dans un serveur.", delete_after=10)
            return

        channel_id = await self._service.get_rules_channel_id(ctx.guild.id)
        if not channel_id:
            await ctx.send("Aucun salon 'rules' configure pour cette guilde.", delete_after=10)
            return

        channel = self.bot.get_channel(channel_id)
        if not channel or not hasattr(channel, "send") or not hasattr(channel, "fetch_message"):
            await ctx.send("Le salon configure pour les regles est introuvable.", delete_after=10)
            return

        avatar = self.bot.user.display_avatar.url if self.bot.user else None
        embed = build_rules_embed(bot_avatar_url=avatar)
        view = AcceptRulesView(self)

        existing = await self._service.get_rules_message(ctx.guild.id)
        if existing:
            try:
                message = await channel.fetch_message(existing.message_id)
                await message.edit(embed=embed, view=view)
                await ctx.send("Le reglement a ete mis a jour.", delete_after=10)
                return
            except discord.NotFound:
                await self._service.delete_rules_message(ctx.guild.id)

        try:
            message = await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            await ctx.send("Je n'ai pas les permissions necessaires pour envoyer ce message.", delete_after=10)
            return

        await self._service.save_rules_message(
            guild_id=ctx.guild.id,
            guild_name=ctx.guild.name,
            channel_id=message.channel.id,
            message_id=message.id,
        )
        await ctx.send(f"Reglement envoye dans {getattr(channel, 'mention', '#rules')}.", delete_after=10)

    async def handle_rules_acceptance(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "Cette action doit etre effectuee dans un serveur.",
                ephemeral=True,
            )
            return

        result = await self._service.accept_rules(
            guild_id=interaction.guild.id,
            guild_name=interaction.guild.name,
            discord_user_id=interaction.user.id,
        )
        if result.already_accepted:
            await interaction.response.send_message(
                "Vous avez deja accepte le reglement.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Vous avez accepte le reglement. Bienvenue.",
            ephemeral=True,
        )

    @setup_rules.error
    async def setup_rules_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Vous n'avez pas les permissions necessaires.", delete_after=10)
            return
        logger.exception("setup_rules failed: %s", error)
        await ctx.send("Une erreur est survenue lors de l'execution de la commande.", delete_after=10)


async def setup(bot: commands.Bot) -> None:
    rules_service = getattr(bot, "rules_service", None)
    if rules_service is None:
        logger.error("rules_service is not initialized. RulesCog will not be loaded.")
        return
    await bot.add_cog(RulesCog(bot, rules_service))
    logger.info("RulesCog loaded.")
