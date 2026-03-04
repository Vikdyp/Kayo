# cogs/rules/rules.py
"""
Cog pour gérer les règles avec des boutons persistants - UI Discord uniquement.
"""

import discord
from discord.ext import commands
import logging

from cogs.rules.services.rules_service import RulesService

logger = logging.getLogger(__name__)


class AcceptRulesView(discord.ui.View):
    def __init__(self, cog: "RulesCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Accepter le règlement",
        style=discord.ButtonStyle.success,
        custom_id="button:accept_rules",
    )
    async def accept_rules_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        discord_id = interaction.user.id
        guild_id = interaction.guild_id

        already_accepted = await self.cog._service.has_accepted_rules(
            guild_id, discord_id
        )
        if already_accepted:
            await interaction.response.send_message(
                "Vous avez déjà accepté le règlement !", ephemeral=True
            )
        else:
            success = await self.cog._service.accept_rules(
                guild_id, interaction.guild.name, discord_id
            )
            if success:
                await interaction.response.send_message(
                    "Vous avez accepté le règlement. Bienvenue !",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "Une erreur est survenue. Veuillez réessayer plus tard.",
                    ephemeral=True,
                )


class RulesCog(commands.Cog):
    """Cog pour gérer les règles avec des boutons persistants."""

    def __init__(self, bot: commands.Bot, rules_service: RulesService):
        self.bot = bot
        self._service = rules_service
        logger.info("RulesCog initialisé.")
        self.bot.loop.create_task(self.reload_persistent_views())

    @commands.command(name="setup_rules")
    @commands.has_permissions(administrator=True)
    async def setup_rules(self, ctx: commands.Context):
        """Envoie l'embed du règlement et met à jour le message persistant."""
        guild_id = ctx.guild.id
        guild_name = ctx.guild.name

        channel_id = await self._service.get_rules_channel_id(guild_id)
        if not channel_id:
            await ctx.send(
                "Aucun salon 'rules' configuré pour cette guilde.", delete_after=10
            )
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send(
                "Le salon configuré pour les règles est introuvable.", delete_after=10
            )
            return

        embed = self._build_rules_embed()
        view = AcceptRulesView(self)

        # Vérifier si un message persistant existe déjà
        msg_info = await self._service.get_rules_message(guild_id)
        if msg_info:
            try:
                message = await channel.fetch_message(msg_info.message_id)
                await message.edit(embed=embed, view=view)
                await ctx.send("Le règlement a été mis à jour.", delete_after=10)
                return
            except discord.NotFound:
                logger.warning("Message persistant introuvable, recréation...")

        # Envoi d'un nouveau message
        try:
            message = await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            await ctx.send(
                "Je n'ai pas les permissions pour envoyer dans ce salon.",
                delete_after=10,
            )
            return
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi des règles: {e}")
            await ctx.send("Une erreur est survenue.", delete_after=10)
            return

        await self._service.save_rules_message(
            guild_id, guild_name, channel.id, message.id
        )
        await ctx.send(f"Règlement envoyé dans {channel.mention}.", delete_after=10)

    def _build_rules_embed(self) -> discord.Embed:
        """Construit l'embed du règlement."""
        embed = discord.Embed(
            title="Règlement du Serveur", color=discord.Color.green()
        )
        embed.add_field(
            name="1. Respect et courtoisie",
            value=(
                "> - Traitez **tous les membres** avec respect.\n"
                "> - Les propos discriminatoires sont strictement interdits.\n"
                "> - **Aucune insulte**, moquerie ou propos agressif ne sera toléré.\n"
                "> - En cas de conflit, contactez un membre du staff."
            ),
            inline=False,
        )
        embed.add_field(
            name="2. Contenu interdit",
            value=(
                "> - Interdiction de publier du contenu NSFW, explicite ou violent.\n"
                "> - Toute forme de harcèlement sera sévèrement sanctionnée.\n"
                "> - Évitez tout spam, flood ou message répétitif."
            ),
            inline=False,
        )
        embed.add_field(
            name="3. Equipe de modération",
            value=(
                "> - Respectez les décisions de l'équipe de modération.\n"
                "> - En cas de désaccord, contactez un staff en privé."
            ),
            inline=False,
        )
        embed.add_field(
            name="4. Utilisation des salons",
            value=(
                "> - Chaque salon a une vocation spécifique, respectez-la.\n"
                "> - Évitez les hors-sujets."
            ),
            inline=False,
        )
        embed.add_field(
            name="5. Publicité et promotion",
            value=(
                "> - Toute publicité non autorisée est strictement interdite.\n"
                "> - Les demandes de partenariat doivent passer par l'administration."
            ),
            inline=False,
        )
        avatar_url = self.bot.user.avatar.url if self.bot.user.avatar else None
        embed.set_footer(
            text="En cliquant sur 'Accepter le règlement', vous acceptez les conditions.",
            icon_url=avatar_url,
        )
        return embed

    async def reload_persistent_views(self):
        """Recharge les vues persistantes au démarrage."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            msg_info = await self._service.get_rules_message(guild.id)
            if not msg_info:
                continue

            channel = guild.get_channel(msg_info.channel_id)
            if not channel:
                continue

            try:
                message = await channel.fetch_message(msg_info.message_id)
                view = AcceptRulesView(self)
                self.bot.add_view(view, message_id=message.id)
                logger.info(f"Vue règlement réattachée pour guild {guild.id}")
            except discord.NotFound:
                await self._service.delete_rules_message(guild.id)
                logger.warning(f"Message règlement introuvable pour guild {guild.id}")
            except Exception as e:
                logger.error(f"Erreur rechargement vue règlement: {e}")

    @setup_rules.error
    async def setup_rules_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(
                "Vous n'avez pas les permissions nécessaires.", delete_after=10
            )
        else:
            logger.error(f"Erreur dans setup_rules: {error}")
            await ctx.send("Une erreur est survenue.", delete_after=10)


async def setup(bot: commands.Bot):
    channel_config_svc = getattr(bot, "channel_config_svc", None)
    persistent_msg_svc = getattr(bot, "persistent_msg_svc", None)
    guild_members_svc = getattr(bot, "guild_members_svc", None)

    if not all([channel_config_svc, persistent_msg_svc, guild_members_svc]):
        logger.error("Services manquants pour RulesCog. Non chargé.")
        return

    rules_service = RulesService(
        channel_config_svc, persistent_msg_svc, guild_members_svc
    )
    await bot.add_cog(RulesCog(bot, rules_service))
    logger.info("RulesCog chargé.")
