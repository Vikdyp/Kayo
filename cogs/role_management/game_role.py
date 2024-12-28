import discord
from discord.ext import commands
from cogs.role_management.services.game_role_service import (
    get_role_id,
    get_all_role_ids,
    store_persistent_message,
    get_persistent_message,
    delete_persistent_message,
)
import logging

from utils.request_manager import enqueue_button_request, enqueue_request

logger = logging.getLogger("roles.roles")

class RolesView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Initiator", style=discord.ButtonStyle.primary, custom_id="role_button:initiator")
    @enqueue_button_request("FAST")
    async def initiator_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_role_selection(interaction, "initiator")

    @discord.ui.button(label="Controller", style=discord.ButtonStyle.primary, custom_id="role_button:controller")
    @enqueue_button_request("FAST")
    async def controller_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_role_selection(interaction, "controller")

    @discord.ui.button(label="Duelist", style=discord.ButtonStyle.primary, custom_id="role_button:duelist")
    @enqueue_button_request("FAST")
    async def duelist_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_role_selection(interaction, "duelist")

    @discord.ui.button(label="Sentinel", style=discord.ButtonStyle.primary, custom_id="role_button:sentinel")
    @enqueue_button_request("FAST")
    async def sentinel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_role_selection(interaction, "sentinel")

    @discord.ui.button(label="Fill", style=discord.ButtonStyle.primary, custom_id="role_button:fill")
    @enqueue_button_request("FAST")
    async def fill_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_role_selection(interaction, "fill")


class RolesCog(commands.Cog):
    """Cog pour gérer la sélection des rôles via des boutons."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("RolesCog initialisé.")
        self.bot.loop.create_task(self.reload_persistent_views())

    @commands.command(name="setup_roles")
    @commands.has_permissions(administrator=True)
    async def setup_roles(self, ctx: commands.Context):
        """
        Envoie l'embed avec les boutons de sélection de rôles et enregistre le message.
        """
        embed = discord.Embed(
            title="🎮 Sélectionnez votre rôle en jeu 🎮",
            description="Veuillez sélectionner le rôle que vous souhaitez jouer.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Vous pouvez changer à tout moment.")

        view = RolesView(self)
        message = await ctx.send(embed=embed, view=view)
        logger.info(f"Message envoyé avec ID : {message.id} dans le canal {ctx.channel.name}")

        # Enregistrement en base de données
        success = await store_persistent_message(
            ctx.guild.id,
            ctx.channel.id,
            message.id,
            "role_selection",
            ctx.guild.name  # important pour get_or_create_server_record
        )
        if success:
            logger.info(f"Message persisté avec ID {message.id}")
        else:
            logger.error("Erreur lors de l'enregistrement du message en base de données.")

    async def reload_persistent_views(self):
        """
        Recharge les vues persistantes pour les messages enregistrés.
        """
        await self.bot.wait_until_ready()
        logger.info("Rechargement des vues persistantes...")

        for guild in self.bot.guilds:
            # Récupère le message persistant pour "role_selection"
            message_data = await get_persistent_message(
                guild.id,
                "role_selection",
                guild.name
            )
            if not message_data:
                continue

            channel = guild.get_channel(message_data["channel_id"])
            if not channel:
                logger.warning(f"Canal introuvable : {message_data['channel_id']} dans guild_id={guild.id}")
                continue

            try:
                message = await channel.fetch_message(message_data["message_id"])
                view = RolesView(self)
                self.bot.add_view(view, message_id=message.id)
                logger.info(f"Vue ajoutée pour le message {message.id} dans le canal {channel.name}")
            except discord.NotFound:
                logger.warning(f"Message introuvable : {message_data['message_id']}")
            except Exception as e:
                logger.error(f"Erreur lors du rechargement : {e}")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """
        Écoute les interactions pour debugger (optionnel).
        """
        logger.debug(f"Interaction reçue : {interaction.data}")

    async def handle_role_selection(self, interaction: discord.Interaction, role_name: str):
        """
        Gère la sélection des rôles en s'assurant qu'un utilisateur ne peut avoir qu'un seul 
        des cinq rôles à la fois. Affiche le rôle ajouté et le rôle retiré en cas de changement.
        """
        logger.info(f"Interaction pour le rôle {role_name} par {interaction.user}")

        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Cette commande ne peut être utilisée que dans un serveur.", ephemeral=True)
            logger.warning("Interaction reçue en dehors d'un serveur.")
            return

        user = interaction.user

        # Liste des rôles à gérer
        roles_to_manage = ['initiator', 'controller', 'duelist', 'sentinel', 'fill']

        # Récupérer les IDs des rôles configurés via get_all_role_ids
        # => on passe guild.id et la liste des rôles, plus le guild.name pour la conversion en DB.
        roles_config = await get_all_role_ids(guild.id, roles_to_manage, guild.name)
        if not roles_config:
            await interaction.response.send_message("Les rôles ne sont pas configurés correctement.", ephemeral=True)
            logger.error(f"Rôles non configurés pour guild_id={guild.id}.")
            return

        # Récupérer les objets de rôles
        roles = {name: guild.get_role(role_id) for name, role_id in roles_config.items()}
        missing_roles = [name for name, role in roles.items() if role is None]
        if missing_roles:
            await interaction.response.send_message(
                f"Les rôles suivants sont manquants sur le serveur : {', '.join(missing_roles)}.",
                ephemeral=True
            )
            logger.error(f"Rôles manquants pour guild_id={guild.id}: {', '.join(missing_roles)}.")
            return

        # Récupérer les rôles actuels de l'utilisateur parmi les rôles gérés
        current_roles = [role for role in user.roles if role.id in roles_config.values()]
        roles_to_remove = [role for role in current_roles if role.name != role_name]
        role_to_add = roles.get(role_name)

        messages = []

        try:
            # Retirer les rôles existants si nécessaire
            if roles_to_remove:
                await user.remove_roles(*roles_to_remove, reason="Changement de rôle via le système de sélection.")
                removed_role_mentions = ", ".join([role.mention for role in roles_to_remove])
                messages.append(f"Rôle(s) retiré(s) : {removed_role_mentions}.")

            # Ajouter le nouveau rôle si l'utilisateur ne le possède pas déjà
            if role_to_add not in current_roles:
                await user.add_roles(role_to_add, reason="Sélection de rôle via le système de sélection.")
                messages.append(f"Rôle ajouté : {role_to_add.mention}.")
            else:
                messages.append(f"Vous possédez déjà le rôle : {role_to_add.mention}.")

            # Envoyer un message récapitulatif
            await interaction.response.send_message("\n".join(messages), ephemeral=True)
            logger.info(f"Rôles mis à jour pour {user}: ajouté {role_to_add.name}, retiré {[role.name for role in roles_to_remove]}")

        except discord.Forbidden:
            await interaction.response.send_message("Je n'ai pas les permissions nécessaires pour gérer vos rôles.", ephemeral=True)
            logger.error(f"Permissions insuffisantes pour gérer les rôles de {user}.")
        except discord.HTTPException as e:
            await interaction.response.send_message("Une erreur est survenue lors de la gestion de vos rôles.", ephemeral=True)
            logger.error(f"Erreur HTTP lors de la gestion des rôles pour {user}: {e}")

    @setup_roles.error
    async def setup_roles_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Vous n'avez pas les permissions nécessaires pour utiliser cette commande.", ephemeral=True)
            logger.warning(f"{ctx.author} a tenté d'utiliser setup_roles sans permissions.")
        else:
            await ctx.send("Une erreur est survenue lors de l'exécution de la commande.", ephemeral=True)
            logger.error(f"Erreur dans setup_roles: {error}")

async def setup(bot: commands.Bot):
    await bot.add_cog(RolesCog(bot))
    logger.info("RolesCog chargé.")
