# cogs/role_management/language_role.py

import discord
from discord.ext import commands
import logging

from cogs.role_management.services.language_role_service import LanguageRoleService

logger = logging.getLogger(__name__)


class LanguageRoleView(discord.ui.View):
    def __init__(self, cog: "LanguageRoleCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Français", style=discord.ButtonStyle.primary, custom_id="role_button:francais")
    async def francais_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_role_selection(interaction, "francais")

    @discord.ui.button(label="Anglais", style=discord.ButtonStyle.primary, custom_id="role_button:anglais")
    async def anglais_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_role_selection(interaction, "anglais")

    @discord.ui.button(label="Espagnol", style=discord.ButtonStyle.primary, custom_id="role_button:espagnol")
    async def espagnol_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_role_selection(interaction, "espagnol")


class LanguageRoleCog(commands.Cog):
    """Cog pour la sélection de rôles de langue via boutons persistants."""

    def __init__(self, bot: commands.Bot, service: LanguageRoleService):
        self.bot = bot
        self._service = service
        self.bot.loop.create_task(self._reload_persistent_views())
        logger.info("LanguageRoleCog initialisé.")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @commands.command(name="setup_language")
    @commands.has_permissions(administrator=True)
    async def setup_language(self, ctx: commands.Context):
        """Envoie un embed avec des boutons de sélection de langue et enregistre le message."""
        embed = discord.Embed(
            title="Choisissez votre langue",
            description="Cliquez sur le bouton correspondant pour recevoir le rôle.",
            color=discord.Color.blue(),
        )

        view = LanguageRoleView(self)
        message = await ctx.send(embed=embed, view=view)

        await self._service.save_persistent_message(
            ctx.guild.id, ctx.guild.name, ctx.channel.id, message.id
        )
        logger.info(f"Message langue persisté avec ID {message.id}")

    # ------------------------------------------------------------------
    # Role handling
    # ------------------------------------------------------------------

    async def handle_role_selection(self, interaction: discord.Interaction, role_name: str):
        """Gère le toggle d'un rôle de langue (ajout/retrait)."""
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Commande utilisable uniquement dans un serveur.", ephemeral=True)
            return

        user = interaction.user

        role_id = await self._service.get_role_id(guild.id, role_name)
        if not role_id:
            await interaction.response.send_message(f"Rôle {role_name} non configuré.", ephemeral=True)
            return

        role = guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("Le rôle configuré est introuvable.", ephemeral=True)
            return

        if role in user.roles:
            await user.remove_roles(role)
            await interaction.response.send_message(f"Le rôle {role.mention} a été retiré.", ephemeral=True)
        else:
            await user.add_roles(role)
            await interaction.response.send_message(f"Le rôle {role.mention} a été ajouté.", ephemeral=True)

    # ------------------------------------------------------------------
    # Persistent views
    # ------------------------------------------------------------------

    async def _reload_persistent_views(self):
        """Recharge les vues persistantes au redémarrage."""
        await self.bot.wait_until_ready()

        for guild in self.bot.guilds:
            msg_info = await self._service.get_persistent_message(guild.id)
            if not msg_info:
                continue

            channel = guild.get_channel(msg_info.channel_id)
            if not channel:
                continue

            try:
                message = await channel.fetch_message(msg_info.message_id)
                view = LanguageRoleView(self)
                self.bot.add_view(view, message_id=message.id)
                logger.info(f"Vue language_role rechargée pour message {message.id}")
            except discord.NotFound:
                logger.warning(f"Message langue introuvable : {msg_info.message_id}")
                await self._service.delete_persistent_message(guild.id)
            except Exception as e:
                logger.error(f"Erreur rechargement language_role : {e}")

    @setup_language.error
    async def setup_language_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Permissions insuffisantes.", delete_after=10)
        else:
            logger.error(f"Erreur setup_language: {error}")


async def setup(bot: commands.Bot):
    service = LanguageRoleService(bot.role_config_svc, bot.persistent_msg_svc)
    await bot.add_cog(LanguageRoleCog(bot, service))
    logger.info("LanguageRoleCog chargé.")
