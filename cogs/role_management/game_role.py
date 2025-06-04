import discord
from discord.ext import commands, tasks
from cogs.role_management.services.game_role_service import (
    get_role_id,
    get_all_role_ids,
    store_persistent_message,
    get_persistent_message,
    delete_persistent_message,
)
import logging


logger = logging.getLogger("roles.roles")

class RolesView(discord.ui.View):
    def __init__(self, cog):
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
        guild = ctx.guild
        guild_id = guild.id
        guild_name = guild.name

        # Récupérer les IDs des rôles
        roles_to_manage = ['initiator', 'controller', 'duelist', 'sentinel', 'fill']
        roles_config = await get_all_role_ids(guild_id, roles_to_manage, guild_name)
        if not roles_config:
            await ctx.send("Les rôles ne sont pas configurés correctement.", delete_after=10)
            logger.error(f"Rôles non configurés pour guild_id={guild_id}.")
            return

        # Récupérer les comptages de rôles
        role_counts = await self.get_role_counts(guild, roles_config)

        # Déterminer le rôle prioritaire (celui avec le moins de membres)
        role_prioritaire = self.get_least_populated_role(role_counts)

        # Créer l'embed avec les comptages et les informations supplémentaires
        embed = discord.Embed(
            title="🎮 Sélectionnez votre rôle Valorant 🎮",
            description=(
                "Veuillez sélectionner le rôle que vous souhaitez jouer.\n\n"
                "**Ces rôles détermineront le rôle que vous utiliserez en partie.**"
            ),
            color=discord.Color.green()
        )
        
        # Construction de la liste des rôles avec une disposition alignée
        roles_display = ""
        for role_name, count in role_counts.items():
            roles_display += f"**{role_name.capitalize():<10}**: {count} membre(s)\n"

        # Ajouter la liste des rôles alignés à l'embed
        embed.add_field(
            name="Répartition des rôles",
            value=roles_display,
            inline=False
        )
        
        embed.set_footer(text="Vous pouvez changer de rôle à tout moment.")

        view = RolesView(self)
        try:
            message = await ctx.send(embed=embed, view=view)
            logger.info(f"Message envoyé avec ID : {message.id} dans le canal {ctx.channel.name}")
        except discord.Forbidden:
            await ctx.send("Je n'ai pas les permissions nécessaires pour envoyer des messages dans ce salon.", delete_after=10)
            logger.error("Permission manquante pour envoyer un message dans le salon.")
            return
        except Exception as e:
            await ctx.send("Une erreur est survenue lors de l'envoi du message.", delete_after=10)
            logger.error(f"Erreur lors de l'envoi du message des rôles: {e}")
            return

        # Enregistrement en base de données
        success = await store_persistent_message(
            guild_id,
            ctx.channel.id,
            message.id,
            "role_selection",
            guild_name  # important pour get_or_create_server_record
        )
        if success:
            logger.info(f"Message persisté avec ID {message.id}")
        else:
            logger.error("Erreur lors de l'enregistrement du message en base de données.")

    async def get_role_counts(self, guild, roles_config):
        """
        Retourne un dictionnaire avec le nom du rôle et le nombre de membres ayant ce rôle.
        """
        role_counts = {}
        for role_name, role_id in roles_config.items():
            role = guild.get_role(role_id)
            if role:
                role_counts[role_name] = len(role.members)
            else:
                role_counts[role_name] = 0
        return role_counts

    def get_least_populated_role(self, role_counts):
        """
        Détermine le rôle avec le moins de membres.
        En cas d'égalité, retourne le premier rôle trouvé.
        """
        least_populated_role = min(role_counts, key=role_counts.get)
        return least_populated_role

    async def update_roles_embed(self, guild):
        """
        Met à jour l'embed de sélection des rôles avec les comptages actuels et le rôle prioritaire.
        """
        guild_id = guild.id
        guild_name = guild.name

        # Récupérer le message persisté
        message_data = await get_persistent_message(guild_id, "role_selection", guild_name)
        if not message_data:
            logger.warning(f"Aucun message de sélection de rôle trouvé pour guild_id={guild_id}")
            return

        channel = guild.get_channel(message_data["channel_id"])
        if not channel:
            logger.warning(f"Canal introuvable : {message_data['channel_id']} dans guild_id={guild_id}")
            return

        try:
            message = await channel.fetch_message(message_data["message_id"])
        except discord.NotFound:
            logger.warning(f"Message introuvable : {message_data['message_id']} dans canal {channel.name}")
            return
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du message des rôles : {e}")
            return

        # Récupérer les IDs des rôles
        roles_to_manage = ['initiator', 'controller', 'duelist', 'sentinel', 'fill']
        roles_config = await get_all_role_ids(guild_id, roles_to_manage, guild_name)
        if not roles_config:
            logger.error(f"Rôles non configurés pour guild_id={guild_id}.")
            return

        # Récupérer les comptages de rôles
        role_counts = await self.get_role_counts(guild, roles_config)

        # Déterminer le rôle prioritaire (celui avec le moins de membres)
        role_prioritaire = self.get_least_populated_role(role_counts)

        # Créer un nouvel embed avec les comptages mis à jour et les informations supplémentaires
        embed = discord.Embed(
            title="🎮 Sélectionnez votre rôle Valorant 🎮",
            description=(
                "Veuillez sélectionner le rôle que vous souhaitez jouer.\n\n"
                "**Ces rôles détermineront le rôle que vous utiliserez en partie.**"
            ),
            color=discord.Color.green()
        )
        
        # Construction de la liste des rôles avec une disposition alignée
        roles_display = ""
        for role_name, count in role_counts.items():
            roles_display += f"**{role_name.capitalize():<10}**: {count} membre(s)\n"

        # Ajouter la liste des rôles alignés à l'embed
        embed.add_field(
            name="Répartition des rôles\n\n",
            value=roles_display,
            inline=False
        )
        
        embed.set_footer(text="Vous pouvez changer de rôle à tout moment.")

        # Mettre à jour l'embed du message
        try:
            await message.edit(embed=embed)
            logger.info(f"Embed des rôles mis à jour pour le message ID: {message.id}")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'embed des rôles : {e}")

    async def reload_persistent_views(self):
        """
        Recharge les vues persistantes pour les messages enregistrés et met à jour les embeds.
        """
        await self.bot.wait_until_ready()
        logger.info("Rechargement des vues persistantes...")

        for guild in self.bot.guilds:
            guild_id = guild.id
            guild_name = guild.name

            # Récupère le message persisté pour "role_selection"
            message_data = await get_persistent_message(
                guild_id,
                "role_selection",
                guild_name
            )
            if not message_data:
                continue

            channel = guild.get_channel(message_data["channel_id"])
            if not channel:
                logger.warning(f"Canal introuvable : {message_data['channel_id']} dans guild_id={guild_id}")
                continue

            try:
                message = await channel.fetch_message(message_data["message_id"])
                view = RolesView(self)
                self.bot.add_view(view, message_id=message.id)
                logger.info(f"Vue ajoutée pour le message {message.id} dans le canal {channel.name}")

                # Mettre à jour l'embed au démarrage
                await self.update_roles_embed(guild)

            except discord.NotFound:
                logger.warning(f"Message introuvable : {message_data['message_id']} dans canal {channel.name}")
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
        Met à jour l'embed des rôles après chaque changement.
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
        roles_to_remove = [role for role in current_roles if role.name.lower() != role_name.lower()]
        role_to_add = roles.get(role_name.lower())

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

            # Mettre à jour l'embed des rôles
            await self.update_roles_embed(guild)

        except discord.Forbidden:
            await interaction.response.send_message("Je n'ai pas les permissions nécessaires pour gérer vos rôles.", ephemeral=True)
            logger.error(f"Permissions insuffisantes pour gérer les rôles de {user}.")
        except discord.HTTPException as e:
            await interaction.response.send_message("Une erreur est survenue lors de la gestion de vos rôles.", ephemeral=True)
            logger.error(f"Erreur HTTP lors de la gestion des rôles pour {user}: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("RolesCog prêt.")

    @setup_roles.error
    async def setup_roles_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Vous n'avez pas les permissions nécessaires pour utiliser cette commande.", delete_after=10)
            logger.warning(f"{ctx.author} a tenté d'utiliser setup_roles sans permissions.")
        else:
            await ctx.send("Une erreur est survenue lors de l'exécution de la commande.", delete_after=10)
            logger.error(f"Erreur dans setup_roles: {error}")

async def setup(bot: commands.Bot):
    await bot.add_cog(RolesCog(bot))
    logger.info("RolesCog chargé.")