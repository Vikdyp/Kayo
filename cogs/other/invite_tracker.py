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

    async def init_invites(self):
        """Charge les invitations pour chaque serveur du bot."""
        for guild in self.bot.guilds:
            try:
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
    async def on_member_join(self, member: discord.Member):
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
        for invite in invites_after:
            old_invite = discord.utils.find(lambda i: i.code == invite.code, invites_before)
            if old_invite and invite.uses > old_invite.uses:
                used_invite = invite
                break

        if used_invite:
            inviter = used_invite.inviter

            # On incrémente le compteur pour l'inviteur et on sauvegarde le mapping en BDD.
            await self.increment_invite_count(inviter.id)
            await self.set_member_inviter(member.id, inviter.id)
            
            # Récupération du salon de log via l'ID défini
            log_channel = self.bot.get_channel(self.log_channel_id)
            if log_channel:
                count = await self.get_invite_count(inviter.id)
                await log_channel.send(f"Félicitations {inviter.mention}, tu as désormais invité {count} membre{'s' if count != 1 else ''}!")
        else:
            logger.info("Impossible de déterminer l'invitation utilisée.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        inviter_id = await self.get_member_inviter(member.id)
        if inviter_id:
            await self.decrement_invite_count(inviter_id)
            
            log_channel = self.bot.get_channel(self.log_channel_id)
            if log_channel:
                count = await self.get_invite_count(inviter_id)
                inviter = guild.get_member(inviter_id)
                if inviter:
                    await log_channel.send(f"{member.mention} a quitté le serveur. {inviter.mention} passe à {count} invitation{'s' if count != 1 else ''}.")
            
            # Supprimer le mapping en BDD
            await self.delete_member_inviter(member.id)
    
    # Méthodes d'accès à la BDD

    async def increment_invite_count(self, inviter_id: int):
        """Incrémente le compteur d'invitations pour l'inviteur."""
        await database.ensure_connected()
        query = """
        INSERT INTO invite_tracker (inviter_id, count)
        VALUES ($1, 1)
        ON CONFLICT (inviter_id) DO UPDATE
          SET count = invite_tracker.count + 1;
        """
        await database.execute(query, inviter_id)
        logger.debug(f"Invitations incrémentées pour {inviter_id}")

    async def decrement_invite_count(self, inviter_id: int):
        """Décrémente le compteur d'invitations pour l'inviteur, sans descendre en dessous de 0."""
        await database.ensure_connected()
        query = """
        UPDATE invite_tracker
        SET count = GREATEST(count - 1, 0)
        WHERE inviter_id = $1;
        """
        await database.execute(query, inviter_id)
        logger.debug(f"Invitations décrémentées pour {inviter_id}")

    async def get_invite_count(self, inviter_id: int) -> int:
        """Retourne le compteur d'invitations de l'inviteur."""
        await database.ensure_connected()
        query = "SELECT count FROM invite_tracker WHERE inviter_id = $1;"
        result = await database.fetchval(query, inviter_id)
        return result if result is not None else 0

    async def set_member_inviter(self, member_id: int, inviter_id: int):
        """Sauvegarde en BDD le mapping entre le membre invité et son invitant."""
        await database.ensure_connected()
        query = """
        INSERT INTO member_inviter (member_id, inviter_id)
        VALUES ($1, $2)
        ON CONFLICT (member_id) DO UPDATE SET inviter_id = EXCLUDED.inviter_id;
        """
        await database.execute(query, member_id, inviter_id)
        logger.debug(f"Mapping enregistré: {member_id} -> {inviter_id}")

    async def get_member_inviter(self, member_id: int) -> int:
        """Renvoie l'ID de l'invitant pour un membre donné, ou None."""
        await database.ensure_connected()
        query = "SELECT inviter_id FROM member_inviter WHERE member_id = $1;"
        return await database.fetchval(query, member_id)

    async def delete_member_inviter(self, member_id: int):
        """Supprime le mapping d'un membre invité de la BDD."""
        await database.ensure_connected()
        query = "DELETE FROM member_inviter WHERE member_id = $1;"
        await database.execute(query, member_id)
        logger.debug(f"Mapping supprimé pour le membre {member_id}")

async def setup(bot):
    await bot.add_cog(InviteTrackerCog(bot))
