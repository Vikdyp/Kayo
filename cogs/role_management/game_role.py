# cogs/role_management/game_role.py

import discord
from discord.ext import commands
import logging

from cogs.role_management.services.game_role_service import GameRoleService, GAME_ROLE_KEYS

logger = logging.getLogger(__name__)


class GameRolesView(discord.ui.View):
    def __init__(self, cog: "GameRoleCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Initiator", style=discord.ButtonStyle.primary, custom_id="role_button:initiator")
    async def initiator_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_role_selection(interaction, "initiator")

    @discord.ui.button(label="Controller", style=discord.ButtonStyle.primary, custom_id="role_button:controller")
    async def controller_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_role_selection(interaction, "controller")

    @discord.ui.button(label="Duelist", style=discord.ButtonStyle.primary, custom_id="role_button:duelist")
    async def duelist_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_role_selection(interaction, "duelist")

    @discord.ui.button(label="Sentinel", style=discord.ButtonStyle.primary, custom_id="role_button:sentinel")
    async def sentinel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_role_selection(interaction, "sentinel")

    @discord.ui.button(label="Fill", style=discord.ButtonStyle.primary, custom_id="role_button:fill")
    async def fill_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_role_selection(interaction, "fill")


class GameRoleCog(commands.Cog):
    """Cog pour la sélection de rôles Valorant via boutons persistants."""

    def __init__(self, bot: commands.Bot, service: GameRoleService):
        self.bot = bot
        self._service = service
        self.bot.loop.create_task(self._reload_persistent_views())
        logger.info("GameRoleCog initialisé.")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @commands.command(name="setup_roles")
    @commands.has_permissions(administrator=True)
    async def setup_roles(self, ctx: commands.Context):
        """Envoie l'embed avec les boutons de sélection de rôles et enregistre le message."""
        guild = ctx.guild

        roles_config = await self._service.get_all_role_ids(guild.id)
        if not roles_config:
            await ctx.send("Les rôles ne sont pas configurés correctement.", delete_after=10)
            return

        role_counts = self._get_role_counts(guild, roles_config)

        embed = self._build_embed(role_counts)
        view = GameRolesView(self)

        try:
            message = await ctx.send(embed=embed, view=view)
        except discord.Forbidden:
            await ctx.send("Je n'ai pas les permissions nécessaires pour envoyer des messages.", delete_after=10)
            return

        await self._service.save_persistent_message(
            guild.id, guild.name, ctx.channel.id, message.id
        )
        logger.info(f"Message de rôles persisté avec ID {message.id}")

    # ------------------------------------------------------------------
    # Role handling
    # ------------------------------------------------------------------

    async def handle_role_selection(self, interaction: discord.Interaction, role_name: str):
        """Gère la sélection exclusive de rôle (un seul rôle de jeu à la fois)."""
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Commande utilisable uniquement dans un serveur.", ephemeral=True)
            return

        user = interaction.user

        roles_config = await self._service.get_all_role_ids(guild.id)
        if not roles_config:
            await interaction.response.send_message("Les rôles ne sont pas configurés.", ephemeral=True)
            return

        roles = {name: guild.get_role(rid) for name, rid in roles_config.items()}
        missing = [n for n, r in roles.items() if r is None]
        if missing:
            await interaction.response.send_message(
                f"Rôles manquants sur le serveur : {', '.join(missing)}.", ephemeral=True
            )
            return

        current_roles = [r for r in user.roles if r.id in roles_config.values()]
        roles_to_remove = [r for r in current_roles if r.name.lower() != role_name.lower()]
        role_to_add = roles.get(role_name.lower())

        messages = []
        try:
            if roles_to_remove:
                await user.remove_roles(*roles_to_remove, reason="Changement de rôle via sélection.")
                removed = ", ".join(r.mention for r in roles_to_remove)
                messages.append(f"Rôle(s) retiré(s) : {removed}.")

            if role_to_add not in current_roles:
                await user.add_roles(role_to_add, reason="Sélection de rôle.")
                messages.append(f"Rôle ajouté : {role_to_add.mention}.")
            else:
                messages.append(f"Vous possédez déjà le rôle : {role_to_add.mention}.")

            await interaction.response.send_message("\n".join(messages), ephemeral=True)
            await self._update_roles_embed(guild)

        except discord.Forbidden:
            await interaction.response.send_message("Permissions insuffisantes pour gérer vos rôles.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message("Erreur lors de la gestion de vos rôles.", ephemeral=True)
            logger.error(f"Erreur HTTP rôles pour {user}: {e}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_role_counts(guild: discord.Guild, roles_config: dict[str, int]) -> dict[str, int]:
        counts = {}
        for name, rid in roles_config.items():
            role = guild.get_role(rid)
            counts[name] = len(role.members) if role else 0
        return counts

    @staticmethod
    def _build_embed(role_counts: dict[str, int]) -> discord.Embed:
        embed = discord.Embed(
            title="🎮 Sélectionnez votre rôle Valorant 🎮",
            description=(
                "Veuillez sélectionner le rôle que vous souhaitez jouer.\n\n"
                "**Ces rôles détermineront le rôle que vous utiliserez en partie.**"
            ),
            color=discord.Color.green(),
        )
        display = ""
        for name, count in role_counts.items():
            display += f"**{name.capitalize():<10}**: {count} membre(s)\n"
        embed.add_field(name="Répartition des rôles", value=display, inline=False)
        embed.set_footer(text="Vous pouvez changer de rôle à tout moment.")
        return embed

    async def _update_roles_embed(self, guild: discord.Guild):
        """Met à jour l'embed du message persistant avec les comptages actuels."""
        msg_info = await self._service.get_persistent_message(guild.id)
        if not msg_info:
            return

        channel = guild.get_channel(msg_info.channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(msg_info.message_id)
        except (discord.NotFound, discord.HTTPException):
            return

        roles_config = await self._service.get_all_role_ids(guild.id)
        if not roles_config:
            return

        role_counts = self._get_role_counts(guild, roles_config)
        embed = self._build_embed(role_counts)

        try:
            await message.edit(embed=embed)
        except Exception as e:
            logger.error(f"Erreur mise à jour embed rôles : {e}")

    async def _reload_persistent_views(self):
        """Recharge les vues persistantes au démarrage."""
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
                view = GameRolesView(self)
                self.bot.add_view(view, message_id=message.id)
                await self._update_roles_embed(guild)
                logger.info(f"Vue game_role rechargée pour message {message.id}")
            except discord.NotFound:
                logger.warning(f"Message game_role introuvable : {msg_info.message_id}")
            except Exception as e:
                logger.error(f"Erreur rechargement game_role : {e}")

    @setup_roles.error
    async def setup_roles_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Permissions insuffisantes.", delete_after=10)
        else:
            logger.error(f"Erreur setup_roles: {error}")


async def setup(bot: commands.Bot):
    service = GameRoleService(bot.role_config_svc, bot.persistent_msg_svc)
    await bot.add_cog(GameRoleCog(bot, service))
    logger.info("GameRoleCog chargé.")
