# cogs/moderation/moderation.py
import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from datetime import datetime, timedelta
from typing import Optional

from cogs.moderation.services.moderation_service import ModerationService
from cogs.moderation.views.confirmation_view import ConfirmationView

logger = logging.getLogger(__name__)

class Moderation(commands.Cog):
    """Cog pour gérer les bannissements, débannissements, avertissements et vérifications."""
    def __init__(self, bot: commands.Bot, moderation_service: ModerationService):
        self.bot = bot
        self._mod_svc = moderation_service
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

                ban_type = "temp" if duration_minutes else "perm"

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

                await self._mod_svc.add_warning(
                    guild_id=interaction.guild.id,
                    guild_name=interaction.guild.name,
                    user_id=user.id,
                    warned_by=interaction.user.id,
                    reason=reason,
                )
                await interaction.followup.send(
                    f"{user.display_name} a été averti(e). Raison : {reason}",
                    ephemeral=True,
                )

            elif action.value == "check_status":
                if not user:
                    await interaction.followup.send(
                        "Veuillez spécifier un utilisateur pour vérifier son statut.\n"
                        "Exemple : `/moderation action:Vérifier le statut user:@Utilisateur`",
                        ephemeral=True
                    )
                    return

                ban_info = await self._mod_svc.get_ban_info(
                    interaction.guild.id,
                    user.id,
                )  # user.id est l'ID Discord
                if not ban_info:
                    await interaction.followup.send(
                        f"{user.mention} n'est pas banni(e).",  # Mention cliquable pour l'utilisateur
                        ephemeral=True
                    )
                    return

                # Détails du bannissement
                ban_type_str = ban_info.ban_type or "Inconnu"
                ban_reason = ban_info.reason or "Aucune raison fournie"
                ban_end = ban_info.ban_end or "Permanent"
                banned_at = ban_info.banned_at or "Inconnu"

                # Récupération de l'utilisateur qui a banni
                banned_by_mention = "Inconnu"
                if ban_info.moderator_discord_id:
                    banned_by_mention = f"<@{ban_info.moderator_discord_id}>"

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
                ban_end = datetime.utcnow() + timedelta(minutes=duration_minutes)

            # Collecter les rôles de l'utilisateur pour le backup
            roles_to_backup = [
                role.id for role in member.roles
                if role != guild.default_role and role.name.lower() != "ban"
            ]

            # Sauvegarder les rôles pour restauration après déban
            await self._mod_svc.update_roles_backup(
                guild_id=guild.id,
                guild_name=guild.name,
                discord_user_id=member.id,
                roles=roles_to_backup,
            )

            # Ajouter les informations de bannissement
            await self._mod_svc.add_ban(
                guild_id=guild.id,
                guild_name=guild.name,
                user_id=member.id,
                ban_type=ban_type,
                reason=reason,
                banned_by=banned_by.id,
                ban_end=ban_end,
            )

            logger.debug(
                f"Ajout du bannissement : user_id={member.id}, ban_type={ban_type}, "
                f"reason={reason}, banned_by={banned_by.id}, ban_end={ban_end}, roles_backup={roles_to_backup}"
            )

            # Appliquer le ban sur TOUS les serveurs où le bot et l'utilisateur sont présents
            await self.apply_ban_all_guilds(member.id, reason, source_member=member)

            # Récupérer l'ID du salon de demande-deban
            deban_channel_id = await self._mod_svc.get_deban_channel_id(guild.id)
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
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Serveur", value=f"**{guild.name}**", inline=False)
            embed.add_field(name="Raison", value=reason, inline=False)
            embed.add_field(name="Durée", value="Permanente" if ban_end is None else f"Jusqu'à {ban_end}", inline=False)
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

        # Récupérer les informations de bannissement (et les rôles sauvegardés)
        ban_info = await self._mod_svc.get_ban_info(guild.id, user_id)
        if not ban_info:
            logger.warning(f"Aucune donnée de bannissement trouvée pour l'utilisateur Discord ID {user_id}.")
            return

        # Récupérer les rôles sauvegardés AVANT de supprimer le ban
        saved_roles = await self._mod_svc.get_roles_backup(guild.id, user_id)

        # Appliquer le unban sur TOUS les serveurs où le bot et l'utilisateur sont présents
        for g in self.bot.guilds:
            member = g.get_member(user_id)
            if not member:
                continue

            # Retirer le rôle ban
            ban_role_id = await self._mod_svc.get_ban_role_id(g.id)
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
        await self._mod_svc.remove_ban(guild.id, user_id)

        # Nettoyer le backup des rôles maintenant qu'ils ont été restaurés
        await self._mod_svc.clear_roles_backup(guild.id, user_id)

        # Récupérer l'ID du salon de demande-deban
        deban_channel_id = await self._mod_svc.get_deban_channel_id(guild.id)
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
            timestamp=datetime.utcnow()
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

    async def apply_ban_all_guilds(self, user_id: int, reason: str, source_member: Optional[discord.Member] = None) -> None:
        """
        Applique le rôle 'ban' à un utilisateur sur TOUS les serveurs où le bot est présent.
        Retire les rôles avant d'ajouter le rôle ban.
        Note: Les rôles sont sauvegardés dans la table bans lors de l'appel à add_ban().

        Args:
            user_id: ID Discord de l'utilisateur
            reason: Raison du ban
            source_member: Membre déjà récupéré (optionnel, évite le cache miss)
        """
        for guild in self.bot.guilds:
            # Utiliser source_member si c'est le même serveur, sinon chercher dans le cache
            if source_member and guild.id == source_member.guild.id:
                member = source_member
            else:
                member = guild.get_member(user_id)

            if not member:
                logger.debug(f"Membre {user_id} non trouvé dans le cache de {guild.name}.")
                continue

            # Récupérer le rôle ban pour ce serveur
            ban_role_id = await self._mod_svc.get_ban_role_id(guild.id)
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
            return 0

        after_date = datetime.utcnow() - delta
        total_deleted = 0

        # Déterminer les serveurs à parcourir
        guilds_to_process = [current_guild] if scope == "current" else self.bot.guilds

        for guild in guilds_to_process:
            # Parcourir tous les salons textuels
            for channel in guild.text_channels:
                try:
                    # Vérifier que le bot a les permissions
                    if not channel.permissions_for(guild.me).manage_messages:
                        continue
                    if not channel.permissions_for(guild.me).read_message_history:
                        continue

                    # Utiliser purge avec un check sur l'auteur
                    def check(msg):
                        return msg.author.id == user_id

                    deleted = await channel.purge(
                        limit=None,
                        check=check,
                        after=after_date,
                        reason=f"Suppression des messages suite à un ban"
                    )
                    total_deleted += len(deleted)

                except discord.Forbidden:
                    logger.debug(f"Pas de permission pour purger dans {channel.name} ({guild.name})")
                except discord.HTTPException as e:
                    logger.error(f"Erreur lors de la purge dans {channel.name} ({guild.name}): {e}")
                except Exception as e:
                    logger.error(f"Erreur inattendue lors de la purge dans {channel.name} ({guild.name}): {e}")

        logger.info(f"Suppression terminée: {total_deleted} messages de l'utilisateur {user_id} supprimés.")
        return total_deleted

    @tasks.loop(minutes=1)
    async def check_bans_expired(self):
        """Vérifie régulièrement les bannissements temporaires expirés et débannit automatiquement les membres."""
        now = datetime.utcnow()
        expired_bans = await self._mod_svc.get_expired_bans(now)

        count = 0
        for ban in expired_bans:
            discord_id = ban.target_discord_id
            if not discord_id:
                logger.error("Impossible de récupérer l'ID Discord pour un ban expiré.")
                continue

            guild = self.bot.get_guild(ban.guild_id)
            if not guild:
                logger.warning(f"Guild introuvable pour le ban expiré: {ban.guild_id}.")
                continue

            await self.unban_member(guild, discord_id, reason="Expiration du bannissement temporaire")
            count += 1

        if count > 0:
            logger.info(f"{count} bannissement(s) expiré(s) traité(s) avec succès.")

    @check_bans_expired.before_loop
    async def before_check_bans_expired(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    moderation_service = getattr(bot, "moderation_service", None)
    if moderation_service is None:
        logger.error("moderation_service non initialisé dans le bot. Le cog Moderation ne sera pas chargé.")
        return
    await bot.add_cog(Moderation(bot, moderation_service))
    logger.info("Moderation Cog chargé avec succès.")
