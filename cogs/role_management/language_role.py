# cogs/role_management/language_role.py

import discord
from discord.ext import commands
from cogs.role_management.services.language_role_service import RoleService  # Importer la classe
import logging

logger = logging.getLogger(__name__)

class RoleView(discord.ui.View):
    def __init__(self, cog):
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


class RoleManagementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.reload_persistent_views())
        logger.info("RoleManagementCog initialisé.")

    @commands.command(name="setup_language")
    @commands.has_permissions(administrator=True)
    async def setup_roles(self, ctx: commands.Context):
        """
        Envoie un embed avec des boutons de sélection de rôles et enregistre le message.
        """
        embed = discord.Embed(
            title="Choisissez votre langue",
            description="Cliquez sur le bouton correspondant pour recevoir le rôle.",
            color=discord.Color.blue(),
        )

        view = RoleView(self)
        message = await ctx.send(embed=embed, view=view)

        # Stockage du message persistant
        success = await RoleService.store_persistent_message(
            discord_guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            message_id=message.id,
            message_type="language_roles",
            guild_name=ctx.guild.name,
        )
        if success:
            logger.info(f"Message persistant sauvegardé : {message.id}")
        else:
            logger.error("Échec de l'enregistrement du message persistant.")

    async def handle_role_selection(self, interaction: discord.Interaction, role_name: str):
        """
        Gère la sélection ou le retrait d'un rôle en fonction du bouton cliqué.
        """
        guild = interaction.guild
        user = interaction.user

        # Récupérer l'ID du rôle depuis la base
        role_id = await RoleService.get_role_id(guild.id, role_name, guild.name)
        if not role_id:
            await interaction.response.send_message(f"Rôle {role_name} non configuré.", ephemeral=True)
            logger.warning(f"Rôle {role_name} introuvable pour guild_id={guild.id}.")
            return

        role = guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("Le rôle configuré est introuvable.", ephemeral=True)
            logger.error(f"Le rôle avec ID {role_id} est manquant sur le serveur {guild.id}.")
            return

        # Ajouter ou retirer le rôle
        if role in user.roles:
            await user.remove_roles(role)
            await interaction.response.send_message(f"Le rôle {role.mention} a été retiré.", ephemeral=True)
        else:
            await user.add_roles(role)
            await interaction.response.send_message(f"Le rôle {role.mention} a été ajouté.", ephemeral=True)

    async def reload_persistent_views(self):
        """
        Recharge les vues persistantes au redémarrage du bot.
        """
        await self.bot.wait_until_ready()
        logger.info("Rechargement des vues persistantes...")

        for guild in self.bot.guilds:
            # Récupération des messages persistants
            message_data = await RoleService.get_persistent_message(
                discord_guild_id=guild.id,
                message_type="language_roles",
                guild_name=guild.name
            )
            if not message_data:
                continue

            channel = guild.get_channel(message_data["channel_id"])
            if not channel:
                logger.warning(f"Canal introuvable : {message_data['channel_id']} pour guild_id={guild.id}")
                continue

            try:
                message = await channel.fetch_message(message_data["message_id"])
                view = RoleView(self)
                self.bot.add_view(view, message_id=message.id)
                logger.info(f"Vue ajoutée pour le message {message.id} dans le canal {channel.name}")
            except discord.NotFound:
                logger.warning(f"Message introuvable : {message_data['message_id']}")
                await RoleService.delete_persistent_message(
                    discord_guild_id=guild.id,
                    message_type="language_roles",
                    guild_name=guild.name
                )
            except Exception as e:
                logger.error(f"Erreur lors du rechargement des vues : {e}")


async def setup(bot):
    await bot.add_cog(RoleManagementCog(bot))
    logger.info("RoleManagementCog chargé.")
