#cogs\ranking\assign_rank.py
import re
from typing import Optional
import discord
from discord.ext import commands, tasks
from cogs.ranking.services.assign_rank_service import (
    reset_all_update_flag_false,
    mark_user_update_flag_true,
    get_users_with_update_flag_false,
    store_persistent_message,
    get_persistent_message,
    get_channel_id,
    update_user_valorant_info,
    set_valorant_details,
    get_all_users_with_valo_info,
    get_role_mappings,
    refresh_role_mappings,
    delete_valo_data,
    get_role_id_for_config,
    get_or_create_server_record,
    get_user_by_pseudo_tag,
    get_last_notification,         # nouvel import
    update_last_notification         # nouvel import
)
from cogs.ranking.services.valorant_service import (
    close_session, get_puuid, get_player_rank, RateLimitException
)
from cogs.moderation.services.moderation_service import ModerationService
from utils.database import database
from utils.checks import rules_interaction_check
import logging
import asyncio
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    import pytz

logger = logging.getLogger("assign_rank")

EMBED_MESSAGE_TYPE = "embed_rank"

async def get_rules_channel_id(guild_id: int) -> Optional[int]:
    return await get_channel_id(guild_id, "rules")

# --- Mapping rang Valorant → ID (roles_configurations PK)
VALORANT_RANK_TO_DB_ID = {
    "Iron 1": 3,
    "Iron 2": 3,
    "Iron 3": 3,
    "Bronze 1": 4,
    "Bronze 2": 4,
    "Bronze 3": 4,
    "Silver 1": 5,
    "Silver 2": 5,
    "Silver 3": 5,
    "Gold 1": 6,
    "Gold 2": 6,
    "Gold 3": 6,
    "Platinum 1": 7,
    "Platinum 2": 7,
    "Platinum 3": 7,
    "Diamond 1": 8,
    "Diamond 2": 8,
    "Diamond 3": 8,
    "Ascendant 1": 9,
    "Ascendant 2": 9,
    "Ascendant 3": 9,
    "Immortal 1": 10,
    "Immortal 2": 10,
    "Immortal 3": 10,
    "Radiant": 11,
    "Unrated": 41,
}


class PseudoTagModal(discord.ui.Modal, title="Renseignez votre Pseudo et Tag Valorant"):
    pseudo = discord.ui.TextInput(
        label="Pseudo",
        placeholder="Entrez votre pseudo Valorant (exemple: Swyzin ぼ)",
        max_length=32,  # vous pouvez augmenter la taille si besoin
        required=True,
    )
    tag = discord.ui.TextInput(
        label="Tag",
        placeholder="Entrez votre tag Valorant sans le # (exemple: meow)",
        max_length=6,
        required=True,
    )

    def __init__(self, user: discord.User, cog):
        super().__init__()
        self.user = user
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        pseudo = self.pseudo.value.strip()
        tag = self.tag.value.strip()

        # Plus de restriction pour le pseudo : on accepte tout ce qui est non vide
        if not pseudo:
            await interaction.response.send_message(
                "Le pseudo ne doit pas être vide.",
                ephemeral=True
            )
            return

        # Pour le tag, on conserve la restriction pour qu'il ne contienne que des lettres et chiffres
        if not tag.isalnum():
            await interaction.response.send_message(
                "Le tag ne doit contenir que des lettres et des chiffres.",
                ephemeral=True
            )
            return

        existing_discord_id = await get_user_by_pseudo_tag(pseudo, tag)
        if existing_discord_id:
            if existing_discord_id == self.user.id:
                await interaction.response.send_message(
                    "Vous avez déjà enregistré ce pseudo et tag Valorant.",
                    ephemeral=True
                )
                return
            else:
                existing_user = self.cog.bot.get_user(existing_discord_id)
                if not existing_user:
                    existing_user = await self.cog.bot.fetch_user(existing_discord_id)
                await interaction.response.send_message(
                    "Ce pseudo et tag Valorant sont déjà utilisés par un autre utilisateur.",
                    ephemeral=True
                )
                await self.cog.notify_duplicate_pseudo_tag(existing_user, self.user, pseudo, tag)
                return

        if not await rules_interaction_check(interaction):
            return

        try:
            success = await update_user_valorant_info(interaction.user.id, pseudo, tag)
            if success:
                await interaction.response.send_message(
                    f"Vos informations Valorant ont été enregistrées : {pseudo}#{tag}",
                    ephemeral=True
                )
                logger.info(f"Utilisateur {interaction.user} a enregistré son pseudo et tag Valorant.")
            else:
                await interaction.response.send_message(
                    "Une erreur est survenue lors de l'enregistrement de vos informations. Veuillez réessayer plus tard.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement des données pour {interaction.user}: {e}")
            await interaction.response.send_message(
                "Une erreur est survenue lors de l'enregistrement de vos informations. Veuillez réessayer plus tard.",
                ephemeral=True
            )

class EmbedButtonsView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Renseigner Pseudo/Tag Valorant",
        style=discord.ButtonStyle.primary,
        custom_id="button:pseudo_tag"
    )
    async def pseudo_tag_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PseudoTagModal(interaction.user, self.cog)
        if not interaction.response.is_done():
            await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Effacer mes données Valorant",
        style=discord.ButtonStyle.danger,
        custom_id="button:delete_valo_data"
    )
    async def delete_valo_data_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        try:
            success = await delete_valo_data(interaction.user.id)
            if success:
                await interaction.followup.send(
                    "Vos données Valorant ont été supprimées de la base de données.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "Une erreur est survenue lors de la suppression de vos données.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Erreur lors de la suppression des données Valorant pour {interaction.user}: {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors de la suppression de vos données.",
                ephemeral=True
            )

class EmbedCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message_id = None
        logger.info("EmbedCog initialisé.")
        self.bot.loop.create_task(self.reload_persistent_embed())
        # Lancement de la boucle de mise à jour (infinie)
        self.bot.loop.create_task(self.update_roles_loop())
        # Tâche (standard) de refresh du cache des rôles (toutes les heures)
        self.refresh_roles_cache_task.start()

    def cog_unload(self):
        self.refresh_roles_cache_task.cancel()
        self.bot.loop.create_task(close_session())

    async def reload_persistent_embed(self):
        await self.bot.wait_until_ready()
        logger.info("Rechargement de l'embed persistant...")

        for guild in self.bot.guilds:
            message_data = await get_persistent_message(
                guild.id,
                EMBED_MESSAGE_TYPE,
                guild.name
            )
            if not message_data:
                logger.info(f"Aucun message persistant trouvé pour la guilde {guild.id}.")
                continue

            channel = guild.get_channel(message_data["channel_id"])
            if not channel:
                logger.warning(f"Canal introuvable : {message_data['channel_id']} dans guild_id={guild.id}")
                continue

            try:
                message = await channel.fetch_message(message_data["message_id"])
                view = EmbedButtonsView(self)
                self.bot.add_view(view, message_id=message.id)
                logger.info(f"Vue ajoutée pour le message {message.id} dans le canal {channel.name}")
            except discord.NotFound:
                logger.warning(f"Message introuvable : {message_data['message_id']} dans le canal {channel.name}")
            except Exception as e:
                logger.error(f"Erreur lors du rechargement de l'embed persistant : {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"Cog {self.__class__.__name__} prêt.")

    @commands.command(name="send_embed_rang")
    @commands.has_permissions(administrator=True)
    async def send_embed(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        action = "rang"
        channel_id = await get_channel_id(guild_id, action)
        if not channel_id:
            await ctx.send(f"Aucun salon défini pour l'action '{action}'.", delete_after=10)
            logger.error(f"Aucun salon défini pour l'action '{action}' dans guild_id={guild_id}.")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Le salon d'embed spécifié est introuvable.", delete_after=10)
            logger.error(f"Salon d'embed introuvable : {channel_id} dans guild_id={guild_id}.")
            return

        message_data = await get_persistent_message(guild_id, EMBED_MESSAGE_TYPE)
        if message_data:
            try:
                old_message = await channel.fetch_message(message_data["message_id"])
                await ctx.send("L'embed a déjà été envoyé dans ce salon.", delete_after=10)
                logger.info(f"L'embed existe déjà avec le message ID {old_message.id} dans guild_id={guild_id}.")
                return
            except discord.NotFound:
                logger.warning(
                    f"Message persistant introuvable : {message_data['message_id']} "
                    f"dans {channel.name}. Envoi d'un nouvel embed."
                )

        embed = discord.Embed(
            title="Gestion de vos informations Valorant",
            description=(
                "Ce message vous permet de **renseigner** ou d'**effacer** vos données Valorant.\n\n"
                "**Instructions :**\n"
                "1. Cliquez sur le bouton bleu pour lier votre compte Valorant.\n"
                "2. Un formulaire s'ouvrira où vous devrez entrer :\n"
                "   - **Pseudo** : Votre pseudo Valorant (exemple : `globeX`).\n"
                "   - **Tag** : Votre tag Valorant sans le `#` (exemple : `meow`).\n\n"
                "*Note : Vous devez d'abord accepter le règlement.*\n\n"
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="Tenez à jour vos informations pour obtenir le rôle correspondant à votre rang.")

        view = EmbedButtonsView(self)
        try:
            message = await channel.send(embed=embed, view=view)
            success = await store_persistent_message(guild_id, channel.id, message.id, EMBED_MESSAGE_TYPE, ctx.guild.name)
            if success:
                await ctx.send(f"Embed envoyé dans {channel.mention}.", delete_after=10)
                logger.info(f"Embed envoyé dans le salon {channel.id} par {ctx.author} et stocké en base de données.")
            else:
                await ctx.send("Embed envoyé, mais une erreur est survenue lors du stockage en base de données.", delete_after=10)
                logger.error("Embed envoyé, mais échec du stockage en base de données.")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi de l'embed : {e}")
            await ctx.send("Une erreur est survenue lors de l'envoi de l'embed.", delete_after=10)

    async def notify_duplicate_pseudo_tag(self, existing_user: discord.User, current_user: discord.User, pseudo: str, tag: str):
        channel_id = 1315770052431188069  # Remplacez par l'ID du salon désiré
        channel = self.bot.get_channel(channel_id)
        if not channel:
            logger.error(f"Salon avec l'ID {channel_id} introuvable.")
            return

        embed = discord.Embed(
            title="Doublon de Pseudo Valorant Détecté",
            description=(
                f"Un doublon a été détecté pour le pseudo et tag Valorant : **{pseudo}#{tag}**.\n\n"
                f"**Utilisateur 1 :** {existing_user.mention} (ID: {existing_user.id})\n"
                f"**Utilisateur 2 :** {current_user.mention} (ID: {current_user.id})\n\n"
                "Veuillez résoudre ce doublon en modifiant les informations de l'un des utilisateurs."
            ),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="Gestion des Doublons de Pseudo Valorant")
        try:
            await channel.send(embed=embed)
            logger.info(f"Embed de doublon envoyé dans le salon {channel_id} pour {current_user} et {existing_user}.")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi de l'embed de doublon : {e}")

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        await ctx.send("Pong!")

    async def update_roles_loop(self):
        """
        Boucle infinie qui met à jour les rôles Valorant.
        """
        while True:
            try:
                await self.update_roles_task()
            except RateLimitException as e:
                logger.warning(f"RateLimitException rencontrée: {e}. Pause de 60s.")
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(60)

    async def update_roles_task(self):
        """
        Cycle de mise à jour des rôles Valorant.
        Pour chaque utilisateur avec needs_update = FALSE :
        - Vérifie et met à jour les informations (puuid, région, rank, elo).
        - Si la récupération du puuid échoue, notifie le membre (une fois par heure) via DM.
        """
        logger.info("Début de la tâche de mise à jour des rôles Valorant (phase ping-pong).")
        users = await get_users_with_update_flag_false()
        logger.info(f"{len(users)} utilisateurs trouvés avec needs_update=FALSE.")

        if not users:
            logger.info("Aucun utilisateur à mettre à jour. Réinitialisation de needs_update pour tous.")
            await reset_all_update_flag_false()
            logger.info("Fin de la tâche (aucun user).")
            return

        for record in users:
            discord_id = record["discord_id"]
            pseudo = record["valorant_pseudo"]
            tag = record["valorant_tag"]
            puuid = record.get("valorant_puuid")
            region = record.get("valorant_region")
            current_rank = record.get("valorant_rank")
            current_elo = record.get("valorant_elo")

            member = None
            for guild in self.bot.guilds:
                m = guild.get_member(discord_id)
                if m:
                    member = m
                    break
            if not member:
                logger.warning(f"[update_roles_task] Member introuvable pour Discord ID {discord_id}.")
                await mark_user_update_flag_true(discord_id)
                continue

            try:
                ban_role_id = await ModerationService.get_ban_role_id(member.guild.id)
                if ban_role_id:
                    ban_role = member.guild.get_role(ban_role_id)
                    if ban_role and ban_role in member.roles:
                        logger.info(f"[update_roles_task] Skipping {member.display_name} (rôle 'ban').")
                        await mark_user_update_flag_true(discord_id)
                        continue
            except Exception as e:
                logger.error(f"[update_roles_task] Erreur vérification ban pour {member.display_name}: {e}")
                await mark_user_update_flag_true(discord_id)
                continue

            # Si le puuid ou la région ne sont pas enregistrés, on tente de les récupérer via l'API
            if not puuid or not region:
                try:
                    valo_info = await get_puuid(pseudo, tag)
                    if not valo_info:
                        logger.warning(f"[update_roles_task] Impossible de récupérer le PUUID pour {pseudo}#{tag}.")
                        now = datetime.utcnow()
                        last_notif = await get_last_notification(discord_id)
                        if (last_notif is None) or ((now - last_notif) > timedelta(hours=24)):
                            try:
                                await member.send(
                                    f"La récupération de vos informations Valorant a échoué pour le pseudo et tag **{pseudo}#{tag}**.\n"
                                    f"Veuillez vérifier vos identifiants ou modifier vos informations dans le salon <#1323673115922010143>."
                                )
                                await update_last_notification(discord_id, now)
                            except Exception as dm_error:
                                logger.error(f"Erreur lors de l'envoi du DM à {discord_id}: {dm_error}")
                        await mark_user_update_flag_true(discord_id)
                        continue
                    # Affectation des nouvelles valeurs récupérées
                    _, new_region, new_puuid = valo_info
                    region, puuid = new_region, new_puuid
                    # Mise à jour de la BDD avec les nouvelles valeurs
                    await set_valorant_details(discord_id, puuid, region, current_rank or "", current_elo or 0)
                except RateLimitException as e:
                    logger.warning(f"RateLimitException pour {pseudo}#{tag}: {e}")
                    await mark_user_update_flag_true(discord_id)
                    continue

            # Récupération du rang avec les valeurs correctement mises à jour
            try:
                stats = await get_player_rank(region, puuid)
            except RateLimitException as e:
                logger.warning(f"RateLimitException lors de la récupération du rang pour {discord_id}: {e}")
                await mark_user_update_flag_true(discord_id)
                continue
            if stats:
                new_rank, new_elo = stats
            else:
                new_rank, new_elo = None, None
                logger.info(f"[update_roles_task] {pseudo}#{tag} n'a pas de rang compétitif ou API échec.")

            if (new_rank != current_rank) or (new_elo != current_elo):
                if new_rank and new_elo:
                    updated = await set_valorant_details(discord_id, puuid, region, new_rank, new_elo)
                    if updated:
                        logger.info(f"[update_roles_task] Rang/Elo mis à jour pour {discord_id}: {new_rank} / {new_elo}")

            if not new_rank:
                await mark_user_update_flag_true(discord_id)
                continue

            role_config_id = VALORANT_RANK_TO_DB_ID.get(new_rank)
            if not role_config_id:
                logger.warning(f"[update_roles_task] Aucun mapping pour {new_rank}.")
                await mark_user_update_flag_true(discord_id)
                continue

            try:
                discord_role_id = await get_role_id_for_config(member.guild.id, member.guild.name, role_config_id)
            except Exception as e:
                logger.error(f"[update_roles_task] Erreur get_role_id_for_config: {e}")
                discord_role_id = None

            if not discord_role_id:
                logger.warning(f"[update_roles_task] Aucun role_id pour guild={member.guild.id}, pk={role_config_id}.")
                await mark_user_update_flag_true(discord_id)
                continue

            desired_role = member.guild.get_role(discord_role_id)
            if not desired_role:
                logger.warning(f"[update_roles_task] Rôle introuvable sur le serveur : {discord_role_id}")
                await mark_user_update_flag_true(discord_id)
                continue

            role_mappings = await get_role_mappings(member.guild.id, member.guild.name)
            if not role_mappings:
                logger.warning(f"[update_roles_task] Aucune config de rôles pour guild={member.guild.id}.")
                await mark_user_update_flag_true(discord_id)
                continue

            rank_role_ids = set(role_mappings.values())
            roles_to_remove = [r for r in member.roles if (r.id in rank_role_ids and r.id != desired_role.id)]
            if roles_to_remove:
                try:
                    await member.remove_roles(*roles_to_remove, reason="Mise à jour rang Valorant")
                    logger.info(f"[update_roles_task] Rôles supprimés pour {member.display_name}: {[r.name for r in roles_to_remove]}")
                except Exception as e:
                    logger.error(f"[update_roles_task] Erreur remove_roles pour {member.display_name}: {e}")
                    await mark_user_update_flag_true(discord_id)
                    continue

            if desired_role not in member.roles:
                try:
                    await member.add_roles(desired_role, reason="Mise à jour rang Valorant")
                    logger.info(f"[update_roles_task] Rôle '{desired_role.name}' ajouté à {member.display_name}.")
                except Exception as e:
                    logger.error(f"[update_roles_task] Erreur add_roles '{desired_role.name}' -> {member.display_name}: {e}")
                    await mark_user_update_flag_true(discord_id)
                    continue

            await mark_user_update_flag_true(discord_id)

        logger.info("Fin de la tâche de mise à jour des rôles Valorant (phase ping-pong).")


    @commands.command(name="reset_valo_updates")
    @commands.has_permissions(administrator=True)
    async def reset_valo_updates(self, ctx: commands.Context):
        await reset_all_update_flag_false()
        await ctx.send("Tous les utilisateurs ont été repassés en needs_update=TRUE.")

    @tasks.loop(hours=1)
    async def refresh_roles_cache_task(self):
        logger.info("Début de la tâche de rafraîchissement du cache des rôles.")
        for guild in self.bot.guilds:
            await refresh_role_mappings(guild.id, guild.name)
        logger.info("Tâche de rafraîchissement du cache des rôles terminée.")

    @refresh_roles_cache_task.before_loop
    async def before_refresh_roles_cache_task(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedCog(bot))
    logger.info("Cog EmbedCog chargé.")
