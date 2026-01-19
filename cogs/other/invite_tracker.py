import discord
from discord.ext import commands
import asyncpg
from utils.database import database  # Vérifie que le chemin est correct
import logging

logger = logging.getLogger("invite_tracker")

class InviteTrackerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Cache des invitations par serveur : {guild.id: [invite, ...]}
        self.invites = {}
        # Salon de log où envoyer les messages (ID à remplacer par ton salon)
        self.log_channel_id = 1330360063566807132

    async def get_internal_server_id(self, guild: discord.Guild) -> int:
        """Récupère l'ID interne du serveur depuis la table serveur_id."""
        await database.ensure_connected()
        query = "SELECT id FROM serveur_id WHERE guild_id = $1;"
        internal_id = await database.fetchval(query, guild.id)
        if not internal_id:
            logger.error(f"Serveur non trouve dans serveur_id pour guild_id {guild.id}.")
        return internal_id

    async def init_invites(self):
        """Charge les invitations pour chaque serveur du bot."""
        for guild in self.bot.guilds:
            try:
                # Pour récupérer la liste d'invites, le bot doit avoir la permission "Gérer le serveur"
                self.invites[guild.id] = await guild.invites()
            except Exception as e:
                logger.error(f"Erreur lors de la récupération des invitations pour {guild.name} : {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        # Au démarrage du bot, on charge le cache des invitations pour chaque serveur.
        await self.init_invites()
        logger.info("Cache des invitations initialisé pour chaque serveur.")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        # Quand le bot rejoint un nouveau serveur, on charge ses invitations.
        try:
            self.invites[guild.id] = await guild.invites()
            logger.info(f"Invitations chargées pour le serveur {guild.name}")
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des invitations pour {guild.name} : {e}")

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        """
        Événement déclenché quand quelqu'un crée une invite sur un serveur (nécessite Intents.invites).
        On en profite pour l'ajouter à notre cache local.
        """
        guild = invite.guild
        if not guild:
            return
        if guild.id not in self.invites:
            self.invites[guild.id] = []
        # Ajout dans le cache
        # Si elle existe déjà, on la remplace
        for i, inv in enumerate(self.invites[guild.id]):
            if inv.code == invite.code:
                self.invites[guild.id][i] = invite
                return
        # Sinon, on l'ajoute
        self.invites[guild.id].append(invite)
        logger.debug(f"Nouvelle invitation ajoutée au cache: {invite.code} (Guild: {guild.name})")

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        """
        Événement déclenché quand une invitation est supprimée (nécessite Intents.invites).
        On la retire de notre cache pour éviter les confusions.
        """
        guild = invite.guild
        if not guild:
            return
        if guild.id not in self.invites:
            return
        before_count = len(self.invites[guild.id])
        self.invites[guild.id] = [inv for inv in self.invites[guild.id] if inv.code != invite.code]
        after_count = len(self.invites[guild.id])
        logger.debug(f"Invitation supprimée du cache: {invite.code} (Guild: {guild.name}). "
                     f"Avant: {before_count}, Après: {after_count}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Détecte l'invitation utilisée par un nouveau membre, en comparant la liste des invites
        avant/après son arrivée. S'il n'y a pas de différence, on tente un fallback :
        - Chercher si une nouvelle invite est apparue
        - Vérifier si 'uses' est déjà > 0
        """
        guild = member.guild
        invites_before = self.invites.get(guild.id, [])
        try:
            invites_after = await guild.invites()
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des invitations pour {guild.name}: {e}")
            return

        # Mise à jour du cache
        self.invites[guild.id] = invites_after

        used_invite = None
        # 1) Méthode standard : chercher un code dont uses a augmenté
        for invite in invites_after:
            old_invite = discord.utils.find(lambda i: i.code == invite.code, invites_before)
            if old_invite and (invite.uses > old_invite.uses):
                used_invite = invite
                break

        # 2) Fallback : si on n'a pas trouvé, on vérifie s'il existe une nouvelle invite dans invites_after
        #    qui n'apparaît pas dans invites_before, et qui a déjà un usage (ex: uses >= 1).
        if used_invite is None:
            # On liste les nouveaux codes apparus dans invites_after
            new_invites = [inv for inv in invites_after
                           if not any(inv.code == old.code for old in invites_before)]
            # On filtre ceux qui ont au moins 1 usage
            new_invites_used = [inv for inv in new_invites if inv.uses > 0]

            if len(new_invites_used) == 1:
                # S'il n'y en a qu'un, on suppose que c'est lui
                used_invite = new_invites_used[0]
            elif len(new_invites_used) > 1:
                # Si plusieurs, c'est ambigu : on peut prendre le 1er ou ignorer
                used_invite = new_invites_used[0]
                logger.warning("Plus d'une nouvelle invitation avec uses>0 détectée. "
                               f"On suppose que c'est {used_invite.code}.")

        if used_invite:
            inviter = used_invite.inviter
            # Enregistre dans la base
            await self.increment_invite_count(guild, inviter.id)
            await self.set_member_inviter(guild, member.id, inviter.id)

            # Log
            log_channel = self.bot.get_channel(self.log_channel_id)
            if log_channel:
                count = await self.get_invite_count(guild, inviter.id)
                await log_channel.send(
                    f"{member.mention} a rejoint grâce à l'invitation de {inviter.mention} (total des invite : {count} membre{'s' if count != 1 else ''})."
                )
        else:
            logger.info(
                f"[InviteTracker] Impossible de déterminer l'invitation utilisée pour {member} sur {guild.name}. "
                "Peut-être un lien vanity/event, ou un re-join sans code."
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        inviter_id = await self.get_member_inviter(guild, member.id)
        if inviter_id:
            await self.decrement_invite_count(guild, inviter_id)
            log_channel = self.bot.get_channel(self.log_channel_id)
            if log_channel:
                count = await self.get_invite_count(guild, inviter_id)
                inviter = guild.get_member(inviter_id)
                if inviter:
                    await log_channel.send(
                        f"{member.mention} a quitté le serveur,{inviter.mention} passe à {count} invitation{'s' if count != 1 else ''}."
                    )
            # Supprimer le mapping en BDD
            await self.delete_member_inviter(guild, member.id)

    # ---------- Méthodes d'accès à la BDD ----------
    async def increment_invite_count(self, guild: discord.Guild, inviter_id: int):
        """Incrémente le compteur d'invitations pour l'inviteur."""
        await database.ensure_connected()
        internal_server_id = await self.get_internal_server_id(guild)
        if not internal_server_id:
            return
        query = """
        INSERT INTO invite_tracker (inviter_id, count, server_id)
        VALUES ($1, 1, $2)
        ON CONFLICT (inviter_id, server_id) DO UPDATE
          SET count = invite_tracker.count + 1;
        """
        await database.execute(query, inviter_id, internal_server_id)
        logger.debug(f"Invitations incrémentées pour {inviter_id}")

    async def decrement_invite_count(self, guild: discord.Guild, inviter_id: int):
        """Décrémente le compteur d'invitations pour l'inviteur, sans descendre en dessous de 0."""
        await database.ensure_connected()
        internal_server_id = await self.get_internal_server_id(guild)
        if not internal_server_id:
            return
        query = """
        UPDATE invite_tracker
        SET count = GREATEST(count - 1, 0)
        WHERE inviter_id = $1 AND server_id = $2;
        """
        await database.execute(query, inviter_id, internal_server_id)
        logger.debug(f"Invitations décrémentées pour {inviter_id}")

    async def get_invite_count(self, guild: discord.Guild, inviter_id: int) -> int:
        """Retourne le compteur d'invitations de l'inviteur."""
        await database.ensure_connected()
        internal_server_id = await self.get_internal_server_id(guild)
        if not internal_server_id:
            return 0
        query = "SELECT count FROM invite_tracker WHERE inviter_id = $1 AND server_id = $2;"
        result = await database.fetchval(query, inviter_id, internal_server_id)
        return result if result is not None else 0

    async def set_member_inviter(self, guild: discord.Guild, member_id: int, inviter_id: int):
        """Sauvegarde en BDD le mapping entre le membre invité et son invitant."""
        await database.ensure_connected()
        internal_server_id = await self.get_internal_server_id(guild)
        if not internal_server_id:
            return
        query = """
        INSERT INTO member_inviter (member_id, inviter_id, server_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (member_id, server_id) DO UPDATE SET inviter_id = EXCLUDED.inviter_id;
        """
        await database.execute(query, member_id, inviter_id, internal_server_id)
        logger.debug(f"Mapping enregistré: {member_id} -> {inviter_id}")

    async def get_member_inviter(self, guild: discord.Guild, member_id: int) -> int:
        """Renvoie l'ID de l'invitant pour un membre donné, ou None."""
        await database.ensure_connected()
        internal_server_id = await self.get_internal_server_id(guild)
        if not internal_server_id:
            return None
        query = "SELECT inviter_id FROM member_inviter WHERE member_id = $1 AND server_id = $2;"
        return await database.fetchval(query, member_id, internal_server_id)

    async def delete_member_inviter(self, guild: discord.Guild, member_id: int):
        """Supprime le mapping d'un membre invité de la BDD."""
        await database.ensure_connected()
        internal_server_id = await self.get_internal_server_id(guild)
        if not internal_server_id:
            return
        query = "DELETE FROM member_inviter WHERE member_id = $1 AND server_id = $2;"
        await database.execute(query, member_id, internal_server_id)
        logger.debug(f"Mapping supprimé pour le membre {member_id}")

async def setup(bot):
    await bot.add_cog(InviteTrackerCog(bot))
