# cogs/moderation/moderation.py
import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from datetime import datetime, timedelta
from typing import Optional

from cogs.moderation.presenters import (
    build_ban_dm_embed,
    build_unban_dm_embed,
    format_ban_status_message,
)
from cogs.moderation.services.internal_ban_workflow import (
    apply_internal_ban,
    enforce_existing_internal_ban,
    remove_internal_ban,
)
from cogs.moderation.services.moderation_service import ModerationService

logger = logging.getLogger(__name__)

MAX_BAN_PURGE_SCAN_PER_CHANNEL = 1000

class Moderation(commands.Cog):
    """Cog pour gérer les bannissements, débannissements, avertissements et vérifications."""
    def __init__(self, bot: commands.Bot, moderation_service: ModerationService):
        self.bot = bot
        self._mod_svc = moderation_service
        self.lock = asyncio.Lock()
        self._internal_ban_enforcements: set[tuple[int, int]] = set()
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

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self._enforce_internal_ban_for_member(
            member,
            reason="Ban interne actif: retour sur le serveur.",
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        roles_changed = {role.id for role in before.roles} != {role.id for role in after.roles}
        pending_before = bool(getattr(before, "pending", False))
        pending_after = bool(getattr(after, "pending", False))
        onboarding_completed = pending_before and not pending_after
        if not roles_changed and not onboarding_completed:
            return

        await self._enforce_internal_ban_for_member(
            after,
            reason="Ban interne actif: mise a jour des roles.",
        )

    async def _enforce_internal_ban_for_member(self, member: discord.Member, *, reason: str) -> bool:
        key = (member.guild.id, member.id)
        if key in self._internal_ban_enforcements:
            return False

        self._internal_ban_enforcements.add(key)
        try:
            result = await enforce_existing_internal_ban(
                bot=self.bot,
                moderation_service=self._mod_svc,
                guild=member.guild,
                member=member,
                reason=reason,
            )
            if result.ban_found:
                logger.info(
                    "Ban interne reapplique pour %s (%s) dans %s.",
                    member.display_name,
                    member.id,
                    member.guild.name,
                )
            return result.ban_found
        except Exception:
            logger.exception(
                "Erreur lors de la reaplication du ban interne pour %s dans %s.",
                member.id,
                member.guild.id,
            )
            return False
        finally:
            self._internal_ban_enforcements.discard(key)

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

                await interaction.followup.send(
                    format_ban_status_message(ban_info, user.id),
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

            result = await apply_internal_ban(
                bot=self.bot,
                moderation_service=self._mod_svc,
                guild=guild,
                member=member,
                reason=reason,
                banned_by_id=banned_by.id,
                ban_type=ban_type,
                ban_end=ban_end,
                role_reason=f"Ban global: {reason}",
            )
            if not result.ban_recorded:
                return False

            logger.debug(
                f"Ajout du bannissement : user_id={member.id}, ban_type={ban_type}, "
                f"reason={reason}, banned_by={banned_by.id}, ban_end={ban_end}, roles_backup={list(result.roles_backed_up)}"
            )

            deban_channel_mention = await self._get_deban_channel_mention(guild)

            embed = build_ban_dm_embed(
                guild_name=guild.name,
                reason=reason,
                duration_label="Permanente" if ban_end is None else f"Jusqu'à {ban_end}",
                banned_by_display_name=banned_by.display_name,
                deban_channel_mention=deban_channel_mention,
                timestamp=datetime.utcnow(),
            )

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

        result = await remove_internal_ban(
            bot=self.bot,
            moderation_service=self._mod_svc,
            guild=guild,
            user_id=user_id,
            reason=reason,
        )
        if not result.ban_found:
            logger.warning(f"Aucune donnée de bannissement trouvée pour l'utilisateur Discord ID {user_id}.")
            return

        embed = build_unban_dm_embed(
            guild_name=guild.name,
            reason=reason or "Expiration du bannissement temporaire ou décision du staff.",
            timestamp=datetime.utcnow(),
        )

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

    async def _get_deban_channel_mention(self, guild: discord.Guild) -> str:
        deban_channel_id = await self._mod_svc.get_deban_channel_id(guild.id)
        if not deban_channel_id:
            return "le salon de débannissement n'est pas configuré."

        deban_channel = guild.get_channel(deban_channel_id)
        if deban_channel:
            return deban_channel.mention

        logger.warning(
            f"Salon de débannissement avec l'ID {deban_channel_id} introuvable dans le serveur {guild.name}."
        )
        return "le salon de débannissement n'est pas configuré correctement."

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
                        limit=MAX_BAN_PURGE_SCAN_PER_CHANNEL,
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
