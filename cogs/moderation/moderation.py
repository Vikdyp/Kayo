# cogs/moderation/moderation.py
import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from cogs.moderation.services.moderation_service import ModerationService
from utils.confirmation_view import ConfirmationView

logger = logging.getLogger("moderation")

class Moderation(commands.Cog):
    """Cog pour gérer les bannissements, débannissements, avertissements et vérifications."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.check_bans_expired.start()
        logger.info("Initialisation du Cog de Modération.")

    def cog_unload(self):
        self.check_bans_expired.cancel()
        logger.info("Cog de Modération déchargé.")

    async def ensure_moderator_permissions(self, interaction: discord.Interaction):
        """Vérifie que l'utilisateur ayant lancé la commande dispose des permissions de modération nécessaires."""
        if not interaction.guild:
            await interaction.followup.send("Cette commande doit être exécutée dans un serveur.", ephemeral=True)
            return False

        # Exemple de vérification de permission : vérifier si le membre a la permission de bannir
        # Cela dépend de votre logique interne. Ici on vérifie la permission de bannir des membres.
        if not interaction.user.guild_permissions.ban_members:
            await interaction.followup.send(
                "Vous n'avez pas les permissions nécessaires pour utiliser cette commande.",
                ephemeral=True
            )
            return False
        return True

    @app_commands.command(name="moderation", description="Exécute des actions de modération.")
    @app_commands.describe(
        action="Action à effectuer",
        user="Utilisateur cible",
        reason="Raison de l'action (si applicable)",
        duration_minutes="Durée en minutes (pour un bannissement temporaire)",
        delete_messages="Supprimer les messages de l'utilisateur (pour le ban)",
        delete_scope="Portée de la suppression des messages"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Bannir", value="ban"),
            app_commands.Choice(name="Débannir", value="unban"),
            app_commands.Choice(name="Avertir", value="warn"),
            app_commands.Choice(name="Vérifier le statut", value="check_status")
        ],
        delete_messages=[
            app_commands.Choice(name="Ne pas supprimer", value="none"),
            app_commands.Choice(name="Dernière heure", value="1h"),
            app_commands.Choice(name="6 dernières heures", value="6h"),
            app_commands.Choice(name="12 dernières heures", value="12h"),
            app_commands.Choice(name="24 dernières heures", value="24h"),
            app_commands.Choice(name="7 derniers jours", value="7d"),
        ],
        delete_scope=[
            app_commands.Choice(name="Serveur actuel", value="current"),
            app_commands.Choice(name="Tous les serveurs", value="all"),
        ]
    )

    @app_commands.default_permissions(administrator=True)
    async def moderation_execute(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        user: Optional[discord.Member] = None,
        reason: Optional[str] = None,
        duration_minutes: Optional[int] = None,
        delete_messages: Optional[app_commands.Choice[str]] = None,
        delete_scope: Optional[app_commands.Choice[str]] = None
    ):
        """Exécute une action de modération en fonction de l'option spécifiée."""
        
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not await self.ensure_moderator_permissions(interaction):
            return

        try:
            if action.value == "ban":
                if not user or not reason:
                    await interaction.followup.send(
                        "Veuillez spécifier un utilisateur et une raison pour le bannissement.\n"
                        "Exemple : `/moderation action:Bannir user:@Utilisateur reason:VotreRaison`",
                        ephemeral=True
                    )
                    return

                ban_type = "temp" if duration_minutes else "perma"

                # Déterminer les paramètres de suppression
                delete_period = delete_messages.value if delete_messages else "none"
                scope = delete_scope.value if delete_scope else "current"

                success = await self.ban_member(
                    guild=interaction.guild,
                    member=user,
                    ban_type=ban_type,
                    reason=reason,
                    banned_by=interaction.user,
                    duration_minutes=duration_minutes
                )

                # Supprimer les messages si demandé
                deleted_count = 0
                if success and delete_period != "none":
                    deleted_count = await self.delete_user_messages(
                        user_id=user.id,
                        period=delete_period,
                        scope=scope,
                        current_guild=interaction.guild
                    )

                if success:
                    msg = f"{user.display_name} a été banni(e) {'temporairement' if ban_type == 'temp' else 'définitivement'}."
                    if deleted_count > 0:
                        msg += f"\n{deleted_count} message(s) supprimé(s)."
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.followup.send(
                        "Une erreur est survenue lors du bannissement. Veuillez vérifier les rôles et permissions du bot.",
                        ephemeral=True
                    )

            elif action.value == "unban":
                if not user:
                    await interaction.followup.send(
                        "Veuillez spécifier un utilisateur pour le débannissement.\n"
                        "Exemple : `/moderation action:Débannir user:@Utilisateur`",
                        ephemeral=True
                    )
                    return

                await self.unban_member(
                    guild=interaction.guild,
                    user_id=user.id,
                    reason=reason
                )
                await interaction.followup.send(
                    f"{user.display_name} a été débanni(e).",
                    ephemeral=True
                )

            elif action.value == "warn":
                if not user or not reason:
                    await interaction.followup.send(
                        "Veuillez spécifier un utilisateur et une raison pour l'avertissement.\n"
                        "Exemple : `/moderation action:Avertir user:@Utilisateur reason:VotreRaison`",
                        ephemeral=True
                    )
                    return

                await ModerationService.add_warning(user.id)
                await interaction.followup.send(
                    f"{user.display_name} a été averti(e). Raison : {reason}",
                    ephemeral=True
                )

            elif action.value == "check_status":
                if not user:
                    await interaction.followup.send(
                        "Veuillez spécifier un utilisateur pour vérifier son statut.\n"
                        "Exemple : `/moderation action:Vérifier le statut user:@Utilisateur`",
                        ephemeral=True
                    )
                    return

                ban_info = await ModerationService.get_ban_info(user.id)  # user.id est l'ID Discord
                if not ban_info:
                    await interaction.followup.send(
                        f"{user.mention} n'est pas banni(e).",  # Mention cliquable pour l'utilisateur
                        ephemeral=True
                    )
                    return

                # Détails du bannissement
                ban_type_str = ban_info.get("ban_type", "Inconnu")
                ban_reason = ban_info.get("ban_reason", "Aucune raison fournie")
                ban_end = ban_info.get("ban_end", "Permanent")
                banned_at = ban_info.get("banned_at", "Inconnu")

                # Récupération de l'utilisateur qui a banni
                banned_by_id = ban_info.get("banned_by")
                banned_by_mention = "Inconnu"
                if banned_by_id:
                    # Convertir l'ID interne en ID Discord
                    discord_banned_by_id = await ModerationService.get_discord_id(banned_by_id)
                    if discord_banned_by_id:
                        try:
                            banned_by_mention = f"<@{discord_banned_by_id}>"  # Format de mention cliquable
                        except discord.NotFound:
                            banned_by_mention = "Utilisateur introuvable"
                    else:
                        banned_by_mention = "Utilisateur inconnu"

                # Mention cliquable de l'utilisateur banni
                banned_user_mention = f"<@{user.id}>"

                await interaction.followup.send(
                    f"**Statut de {banned_user_mention}** :\n"  # Mention cliquable pour le banni
                    f"Type : {ban_type_str}\n"
                    f"Raison : {ban_reason}\n"
                    f"Banni(e) le : {banned_at}\n"
                    f"Fin de ban : {ban_end}\n"
                    f"Banni(e) par : {banned_by_mention}",  # Mention cliquable pour celui qui a banni
                    ephemeral=True
                )



        except Exception as e:
            logger.exception(f"Erreur dans moderation_execute : {e}")
            await interaction.followup.send(
                "Une erreur est survenue lors du traitement de votre requête. code 001",
                ephemeral=True
            )

    async def ban_member(
            self,
            guild: discord.Guild,
            member: discord.Member,
            ban_type: str,
            reason: str,
            banned_by: discord.User,
            duration_minutes: Optional[int] = None
        ) -> bool:
            """Bannit un membre avec sauvegarde des rôles et ajout du rôle 'ban' sur tous les serveurs."""
            logger.debug(f"Début du bannissement de {member.display_name} (ID: {member.id}) dans {guild.name}.")

            # Définir la durée du bannissement si temporaire
            ban_end = None
            if ban_type == "temp" and duration_minutes:
                ban_end = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)

            # Collecter les rôles de l'utilisateur pour le backup
            roles_to_backup = [
                role.id for role in member.roles
                if role != guild.default_role and role.name.lower() != "ban"
            ]

            # Récupérer l'ID interne du serveur pour le contexte
            internal_server_id = await ModerationService.get_internal_server_id(guild.id)

            # Ajouter les informations de bannissement dans la table 'bans' (global)
            await ModerationService.add_ban(
                user_id=member.id,
                ban_type=ban_type,
                reason=reason,
                banned_by=banned_by.id,
                ban_end=ban_end,
                roles_backup=roles_to_backup if roles_to_backup else None,
                server_id=internal_server_id
            )

            logger.debug(
                f"Ajout du bannissement : user_id={member.id}, ban_type={ban_type}, "
                f"reason={reason}, banned_by={banned_by.id}, ban_end={ban_end}, roles_backup={roles_to_backup}"
            )

            # Appliquer le ban sur TOUS les serveurs où le bot et l'utilisateur sont présents
            await self.apply_ban_all_guilds(member.id, reason)

            # Récupérer l'ID interne du serveur
            internal_server_id = await ModerationService.get_internal_server_id(guild.id)
            if not internal_server_id:
                logger.error(f"Impossible de récupérer l'ID interne du serveur pour {guild.id}.")
                # Vous pouvez choisir de continuer ou de retourner False ici
                # Je vais continuer pour envoyer le DM sans mention de salon de débannissement

            # Récupérer l'ID du salon de demande-deban
            deban_channel_id = await ModerationService.get_deban_channel_id(internal_server_id) if internal_server_id else None
            if deban_channel_id:
                deban_channel = guild.get_channel(deban_channel_id)
                if deban_channel:
                    deban_channel_mention = deban_channel.mention
                else:
                    deban_channel_mention = "le salon de débannissement n'est pas configuré correctement."
                    logger.warning(f"Salon de débannissement avec l'ID {deban_channel_id} introuvable dans le serveur {guild.name}.")
            else:
                deban_channel_mention = "le salon de débannissement n'est pas configuré."

            # Créer l'embed de bannissement
            embed = discord.Embed(
                title="📛 Vous avez été banni(e) du serveur",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Serveur", value=f"**{guild.name}**", inline=False)
            embed.add_field(name="Raison", value=reason, inline=False)
            embed.add_field(name="Durée", value="Permanente" if ban_type == "perma" else f"Jusqu'à {ban_end}", inline=False)
            embed.add_field(name="Banni(e) par", value=banned_by.display_name, inline=False)
            embed.add_field(
                name="Demande de Débannissement",
                value=(
                    f"Si vous souhaitez être débanni(e), veuillez soumettre une demande dans {deban_channel_mention}."
                ),
                inline=False
            )
            embed.set_footer(text="Si vous avez des questions, veuillez contacter l'administration.")

            # Envoyer un DM à l'utilisateur avec l'embed
            try:
                await member.send(embed=embed)
                logger.info(f"Embed de bannissement envoyé à {member.display_name}.")
            except discord.Forbidden:
                logger.warning(f"Impossible d'envoyer un DM à {member.display_name}.")
            except discord.HTTPException as e:
                logger.error(f"Erreur HTTP lors de l'envoi de l'embed de bannissement à {member.display_name}: {e}")

            return True

    async def unban_member(self, guild: discord.Guild, user_id: int, reason: Optional[str] = None) -> None:
        """Débanni un membre et restaure ses rôles sur tous les serveurs."""
        logger.debug(f"Tentative de débannissement de l'utilisateur ID: {user_id}. Raison: {reason}")

        # Convertir l'ID Discord en ID interne
        internal_id = await ModerationService.get_or_create_user_id(user_id)
        if not internal_id:
            logger.error(f"Impossible de convertir l'ID Discord {user_id} en ID interne pour le débannissement.")
            return

        # Récupérer les informations de bannissement (et les rôles sauvegardés)
        ban_info = await ModerationService.get_ban_info(user_id)
        if not ban_info:
            logger.warning(f"Aucune donnée de bannissement trouvée pour l'utilisateur Discord ID {user_id}.")
            return

        # Récupérer les rôles sauvegardés AVANT de supprimer le ban
        saved_roles = await ModerationService.get_roles_backup(user_id)

        # Appliquer le unban sur TOUS les serveurs où le bot et l'utilisateur sont présents
        for g in self.bot.guilds:
            member = g.get_member(user_id)
            if not member:
                continue

            # Retirer le rôle ban
            ban_role_id = await ModerationService.get_ban_role_id(g.id)
            if ban_role_id:
                ban_role = g.get_role(ban_role_id)
                if ban_role and ban_role in member.roles:
                    try:
                        await member.remove_roles(ban_role, reason=f"Fin de ban: {reason or 'Débannissement'}")
                        logger.info(f"Rôle 'ban' retiré de {member.display_name} dans {g.name}.")
                    except discord.Forbidden:
                        logger.error(f"Impossible de retirer le rôle 'ban' de {member.display_name} dans {g.name}.")
                    except discord.HTTPException as e:
                        logger.error(f"Erreur HTTP lors du retrait du rôle 'ban' de {member.display_name} dans {g.name}: {e}")

            # Restaurer les rôles (uniquement dans le serveur d'origine où les rôles ont été sauvegardés)
            if g.id == guild.id and saved_roles:
                roles_to_add = [
                    discord.utils.get(g.roles, id=role_id)
                    for role_id in saved_roles
                ]
                roles_to_add = [role for role in roles_to_add if role is not None]
                if roles_to_add:
                    try:
                        await member.add_roles(*roles_to_add, reason="Restauration des rôles après débannissement.")
                        logger.info(f"Rôles restaurés pour {member.display_name} dans {g.name}: {[role.name for role in roles_to_add]}")
                    except discord.Forbidden:
                        logger.error(f"Permission refusée pour restaurer les rôles de {member.display_name} dans {g.name}.")
                    except discord.HTTPException as e:
                        logger.exception(f"Erreur lors de la restauration des rôles de {member.display_name} dans {g.name}: {e}")

        # Supprimer les informations de bannissement
        await ModerationService.remove_ban(internal_id)

        # Récupérer l'ID interne du serveur
        internal_server_id = await ModerationService.get_internal_server_id(guild.id)
        if not internal_server_id:
            logger.error(f"Impossible de récupérer l'ID interne du serveur pour {guild.id}.")
            # Vous pouvez choisir de continuer ou de retourner ici
            # Je vais continuer pour envoyer le DM sans mention de salon de débannissement

        # Récupérer l'ID du salon de demande-deban
        deban_channel_id = await ModerationService.get_deban_channel_id(internal_server_id) if internal_server_id else None
        if deban_channel_id:
            deban_channel = guild.get_channel(deban_channel_id)
            if deban_channel:
                deban_channel_mention = deban_channel.mention
            else:
                deban_channel_mention = "le salon de débannissement n'est pas configuré correctement."
                logger.warning(f"Salon de débannissement avec l'ID {deban_channel_id} introuvable dans le serveur {guild.name}.")
        else:
            deban_channel_mention = "le salon de débannissement n'est pas configuré."

        # Créer l'embed de débannissement
        embed = discord.Embed(
            title="✅ Vous avez été débanni(e) du serveur",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Serveur", value=f"**{guild.name}**", inline=False)
        embed.add_field(name="Raison", value=reason or "Expiration du bannissement temporaire ou décision du staff.", inline=False)
        embed.add_field(name="Débanni(e) par", value="Administration", inline=False)
        embed.add_field(
            name="C'est fini",
            value=(
                f"Bonne nouvelle, vous êtes libre comme l’air. On est content de vous revoir parmi nous, mais faites gaffe cette fois, hein ? 😉 Profitez bien et bon retour !"
            ),
            inline=False
        )
        embed.set_footer(text="Si vous avez des questions, veuillez contacter l'administration.")

        # Informer l'utilisateur via DM avec l'embed
        try:
            user = await self.bot.fetch_user(user_id)
            if user:
                await user.send(embed=embed)
                logger.info(f"Embed de débannissement envoyé à l'utilisateur Discord ID {user_id}.")
        except discord.Forbidden:
            logger.warning(f"Impossible d'envoyer un DM à l'utilisateur Discord ID {user_id}.")
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors de l'envoi de l'embed de débannissement à l'utilisateur Discord ID {user_id}: {e}")

    async def apply_ban_all_guilds(self, user_id: int, reason: str) -> None:
        """
        Applique le rôle 'ban' à un utilisateur sur TOUS les serveurs où le bot est présent.
        Retire les rôles avant d'ajouter le rôle ban.
        Note: Les rôles sont sauvegardés dans la table bans lors de l'appel à add_ban().
        """
        for guild in self.bot.guilds:
            member = guild.get_member(user_id)
            if not member:
                continue

            # Récupérer le rôle ban pour ce serveur
            ban_role_id = await ModerationService.get_ban_role_id(guild.id)
            if not ban_role_id:
                logger.debug(f"Rôle 'ban' non configuré pour le serveur {guild.name}.")
                continue

            ban_role = guild.get_role(ban_role_id)
            if not ban_role:
                logger.warning(f"Rôle 'ban' avec ID {ban_role_id} introuvable dans {guild.name}.")
                continue

            # Vérifier si l'utilisateur a déjà le rôle ban
            if ban_role in member.roles:
                logger.debug(f"Utilisateur {member.display_name} a déjà le rôle ban dans {guild.name}.")
                continue

            try:
                # Retirer tous les rôles (sauf le rôle par défaut)
                roles_to_remove = [role for role in member.roles if role != guild.default_role]
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason=f"Ban global: {reason}")
                    logger.info(f"Rôles supprimés pour {member.display_name} dans {guild.name}.")

                # Ajouter le rôle ban
                await member.add_roles(ban_role, reason=f"Ban global: {reason}")
                logger.info(f"Rôle 'ban' appliqué à {member.display_name} dans {guild.name}.")

            except discord.Forbidden:
                logger.error(f"Permissions insuffisantes pour bannir {member.display_name} dans {guild.name}.")
            except discord.HTTPException as e:
                logger.error(f"Erreur HTTP lors du ban de {member.display_name} dans {guild.name}: {e}")

    async def delete_user_messages(
        self,
        user_id: int,
        period: str,
        scope: str,
        current_guild: discord.Guild
    ) -> int:
        """
        Supprime les messages d'un utilisateur dans une période donnée.

        Args:
            user_id: ID Discord de l'utilisateur
            period: Période de suppression ("1h", "6h", "12h", "24h", "7d")
            scope: Portée ("current" pour le serveur actuel, "all" pour tous les serveurs)
            current_guild: Le serveur où la commande a été exécutée

        Returns:
            Le nombre total de messages supprimés
        """
        # Calculer la date limite
        period_mapping = {
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "12h": timedelta(hours=12),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
        }

        delta = period_mapping.get(period)
        if not delta:
            logger.warning(f"Période invalide: {period}")
            return 0

        after_date = datetime.now(timezone.utc) - delta
        total_deleted = 0

        logger.info(f"Début suppression messages user {user_id}, période: {period}, scope: {scope}")

        # Déterminer les serveurs à parcourir
        guilds_to_process = [current_guild] if scope == "current" else self.bot.guilds

        for guild in guilds_to_process:
            # Parcourir tous les salons textuels
            for channel in guild.text_channels:
                try:
                    # Vérifier que le bot a les permissions
                    perms = channel.permissions_for(guild.me)
                    if not perms.manage_messages or not perms.read_message_history:
                        continue

                    # Collecter les messages à supprimer
                    messages_to_delete = []
                    async for msg in channel.history(limit=500, after=after_date):
                        if msg.author.id == user_id:
                            messages_to_delete.append(msg)

                    if not messages_to_delete:
                        continue

                    logger.debug(f"Trouvé {len(messages_to_delete)} messages dans {channel.name}")

                    # Supprimer les messages un par un (plus fiable)
                    for msg in messages_to_delete:
                        try:
                            await msg.delete()
                            total_deleted += 1
                        except discord.NotFound:
                            pass  # Déjà supprimé
                        except discord.Forbidden:
                            logger.debug(f"Pas de permission pour supprimer msg {msg.id}")
                        except Exception as e:
                            logger.debug(f"Erreur suppression msg {msg.id}: {e}")

                except discord.Forbidden:
                    pass
                except Exception as e:
                    logger.error(f"Erreur dans {channel.name} ({guild.name}): {e}")

        logger.info(f"Suppression terminée: {total_deleted} messages de l'utilisateur {user_id} supprimés.")
        return total_deleted

    @tasks.loop(minutes=1)
    async def check_bans_expired(self):
        """Vérifie régulièrement les bannissements temporaires expirés et débannit automatiquement les membres."""
        now = datetime.now(timezone.utc)
        expired_bans = await ModerationService.get_expired_bans(now)

        count = 0
        for ban in expired_bans:
            internal_user_id = ban["user_id"]  # Ceci est l'ID interne
            # Récupérer l'ID Discord à partir de l'ID interne
            discord_id = await ModerationService.get_discord_id(internal_user_id)
            if not discord_id:
                logger.error(f"Impossible de récupérer l'ID Discord pour l'ID interne {internal_user_id}.")
                continue

            # Utiliser le premier serveur où l'utilisateur est présent comme référence
            # (unban_member s'applique maintenant sur tous les serveurs automatiquement)
            for guild in self.bot.guilds:
                member = guild.get_member(discord_id)
                if member:
                    await self.unban_member(guild, discord_id, reason="Expiration du bannissement temporaire")
                    count += 1
                    break  # Le unban est global, pas besoin de continuer

        if count > 0:
            logger.info(f"{count} bannissement(s) expiré(s) traité(s) avec succès.")

    @check_bans_expired.before_loop
    async def before_check_bans_expired(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Re-bannit automatiquement un membre qui rejoint s'il est toujours banni."""
        if member.bot:
            return

        # Vérifier si l'utilisateur est dans la table des bans
        ban_info = await ModerationService.get_ban_info(member.id)
        if not ban_info:
            return  # Pas banni

        # Vérifier si le ban est expiré (pour les bans temporaires)
        ban_end = ban_info.get("ban_end")
        if ban_end and datetime.now(timezone.utc) > ban_end:
            # Ban expiré, supprimer le ban et ne pas re-bannir
            await ModerationService.remove_ban(member.id)
            logger.info(f"Ban expiré pour {member.display_name}, suppression du ban.")
            return

        # Attendre que les autres systèmes (auto-role, etc.) aient assigné les rôles
        await asyncio.sleep(3)

        # Rafraîchir le membre pour avoir les rôles à jour
        try:
            member = await member.guild.fetch_member(member.id)
        except discord.NotFound:
            return  # Le membre a quitté

        # Le membre est toujours banni, appliquer le rôle ban
        guild = member.guild
        ban_role_id = await ModerationService.get_ban_role_id(guild.id)
        if not ban_role_id:
            logger.warning(f"Pas de rôle ban configuré pour {guild.name}, impossible de re-bannir {member.display_name}")
            return

        ban_role = guild.get_role(ban_role_id)
        if not ban_role:
            logger.warning(f"Rôle ban {ban_role_id} introuvable dans {guild.name}")
            return

        # Vérifier si le membre a déjà le rôle ban
        if ban_role in member.roles:
            return

        try:
            # Supprimer tous les rôles un par un (pour éviter les erreurs de hiérarchie)
            roles_to_remove = [
                role for role in member.roles
                if role != guild.default_role and role != ban_role and role < guild.me.top_role
            ]
            for role in roles_to_remove:
                try:
                    await member.remove_roles(role, reason="Re-ban automatique: membre toujours banni")
                except (discord.Forbidden, discord.HTTPException):
                    logger.debug(f"Impossible de retirer le rôle {role.name} de {member.display_name}")

            # Ajouter le rôle ban
            await member.add_roles(ban_role, reason="Re-ban automatique: membre toujours banni")

            ban_reason = ban_info.get("ban_reason", "Non spécifiée")
            ban_type = ban_info.get("ban_type", "perma")
            logger.info(f"Re-ban automatique de {member.display_name} dans {guild.name} (type: {ban_type}, raison: {ban_reason})")

            # Envoyer un DM à l'utilisateur pour l'informer
            try:
                embed = discord.Embed(
                    title="📛 Vous êtes toujours banni(e)",
                    description="Vous avez rejoint le serveur mais vous êtes toujours sous le coup d'un bannissement.",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Serveur", value=guild.name, inline=True)
                embed.add_field(name="Type", value="Permanent" if ban_type == "perma" else "Temporaire", inline=True)
                embed.add_field(name="Raison", value=ban_reason, inline=False)
                if ban_end:
                    embed.add_field(name="Fin du ban", value=f"<t:{int(ban_end.timestamp())}:F>", inline=False)
                await member.send(embed=embed)
            except discord.Forbidden:
                pass  # DMs fermés

        except discord.Forbidden:
            logger.error(f"Permissions insuffisantes pour re-bannir {member.display_name} dans {guild.name}")
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors du re-ban de {member.display_name} dans {guild.name}: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
    logger.info("Moderation Cog chargé avec succès.")
