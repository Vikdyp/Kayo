# cogs/moderation/moderation.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from datetime import datetime, timedelta
from typing import Optional
from cogs.utilities.data_manager import DataManager
from cogs.utilities.request_manager import enqueue_request
from cogs.utilities.permission_manager import is_admin
from cogs.utilities.confirmation_view import ConfirmationView

logger = logging.getLogger("discord.moderation")

class UnbanButton(discord.ui.Button):
    def __init__(self, cog, user_id: int):
        super().__init__(label="Unban", style=discord.ButtonStyle.green)
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        view = ConfirmationView(interaction, None)
        await interaction.response.send_message("Confirmez-vous le débannissement ?", view=view, ephemeral=True)
        await view.wait()
        if view.value:
            await self.cog.unban_user(interaction, self.user_id, reason="Unban via demande-deban")
            await interaction.followup.send("Utilisateur débanni avec succès.", ephemeral=True)
            self.view.stop()
        else:
            await interaction.followup.send("Action annulée.", ephemeral=True)

class UnbanView(discord.ui.View):
    def __init__(self, cog, user_id: int):
        super().__init__(timeout=3600)
        self.cog = cog
        self.add_item(UnbanButton(cog, user_id))

class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.check_bans_expired.start()

    def cog_unload(self):
        self.check_bans_expired.cancel()

    async def get_moderation_data(self):
        return await self.data.get_moderation_data()

    async def save_moderation_data(self, mod_data):
        await self.data.save_moderation_data(mod_data)

    async def backup_roles_and_apply_ban(self, member: discord.Member, ban_type: str, reason: str, banned_by: discord.User, duration_minutes: Optional[int] = None):
        guild = member.guild
        mod_data = await self.get_moderation_data()

        # Appel au RoleBackup Cog
        role_backup_cog = self.bot.get_cog("RoleBackup")
        if role_backup_cog:
            await role_backup_cog.backup_roles(member)

        # Retirer tous les rôles (sauf le role par défaut)
        await member.remove_roles(*member.roles[1:], reason="Ban")

        ban_role = discord.utils.get(guild.roles, name="ban")
        if ban_role:
            await member.add_roles(ban_role, reason="Ban")

        now = datetime.utcnow()
        ban_end = None
        if ban_type == "temp" and duration_minutes is not None:
            ban_end = (now + timedelta(minutes=duration_minutes)).isoformat()

        user_data = {
            "ban_type": ban_type,
            "ban_end": ban_end,
            "ban_reason": reason,
            "banned_by": banned_by.id,
            "banned_at": now.isoformat(),
            "warnings_count": 0,
            "unban_request_msg_id": None,
            "unban_request_channel_id": None
        }

        mod_data["bans"][str(member.id)] = user_data
        await self.save_moderation_data(mod_data)

        try:
            await member.send(f"Vous avez été banni du serveur {guild.name}.\nRaison: {reason}\nBanni par: {banned_by.display_name}")
        except:
            pass

    async def unban_user(self, interaction: discord.Interaction, user_id: int, reason: Optional[str] = None):
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            return

        mod_data = await self.get_moderation_data()
        ban_info = mod_data["bans"].pop(str(user_id), None)
        if not ban_info:
            await interaction.followup.send("Cet utilisateur n'est pas banni.", ephemeral=True)
            return

        member = guild.get_member(user_id)
        if member:
            ban_role = discord.utils.get(guild.roles, name="ban")
            if ban_role and ban_role in member.roles:
                await member.remove_roles(ban_role, reason="Unban")

            # Restauration des rôles via RoleBackup
            role_backup_cog = self.bot.get_cog("RoleBackup")
            if role_backup_cog:
                await role_backup_cog.restore_roles(member)

            try:
                await member.send(f"Vous avez été débanni du serveur {guild.name}. Raison: {reason or 'Aucune raison fournie'}")
            except:
                pass

        # Supprimer le message de demande de déban si existe
        if ban_info.get("unban_request_msg_id") and ban_info.get("unban_request_channel_id"):
            ch = guild.get_channel(ban_info["unban_request_channel_id"])
            if ch:
                try:
                    msg = await ch.fetch_message(ban_info["unban_request_msg_id"])
                    await msg.delete()
                except:
                    pass

        await self.save_moderation_data(mod_data)
        logger.info(f"Utilisateur {user_id} débanni par {interaction.user} pour {reason}.")

    @tasks.loop(minutes=1)
    async def check_bans_expired(self):
        now = datetime.utcnow()
        mod_data = await self.get_moderation_data()
        to_unban = []
        for uid, ban_info in mod_data["bans"].items():
            if ban_info["ban_type"] == "temp" and ban_info["ban_end"]:
                end_time = datetime.fromisoformat(ban_info["ban_end"])
                if now > end_time:
                    to_unban.append(uid)

        if to_unban:
            await self.save_moderation_data(mod_data)

        for uid in to_unban:
            user_id = int(uid)
            guilds = self.bot.guilds
            if guilds:
                guild = guilds[0]
                member = guild.get_member(user_id)
                if member:
                    class FakeInteraction:
                        guild = guild
                        user = self.bot.user
                        async def followup(self):
                            class FU:
                                async def send(self, *args, **kwargs):
                                    pass
                            return FU()
                    fake_interaction = FakeInteraction()
                    await self.unban_user(fake_interaction, user_id, reason="Ban expiré automatiquement")
                    logger.info(f"Utilisateur {user_id} débanni automatiquement (ban expiré).")

    @check_bans_expired.before_loop
    async def before_check_bans_expired(self):
        await self.bot.wait_until_ready()

    async def ask_confirmation(self, interaction: discord.Interaction, message: str):
        view = ConfirmationView(interaction, None)
        await interaction.followup.send(message, view=view, ephemeral=True)
        await view.wait()
        return view.value

    @app_commands.command(name="ban_perma", description="Bannir définitivement un utilisateur")
    @app_commands.describe(user="Utilisateur à bannir", reason="Raison du ban", id_message="ID du message (optionnel)")
    @is_admin()
    @enqueue_request()
    async def ban_perma(self, interaction: discord.Interaction, user: discord.Member, reason: str, id_message: Optional[str] = None):
        if not await self.ask_confirmation(interaction, f"Confirmez-vous le ban permanent de {user.mention} ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)
        await self.backup_roles_and_apply_ban(user, "perma", reason, interaction.user)
        await interaction.followup.send(f"{user.display_name} a été banni définitivement. Raison: {reason}", ephemeral=True)
        logger.info(f"{interaction.user} a banni {user.display_name} perma. Raison: {reason}")

    @app_commands.command(name="ban_temp", description="Bannir un utilisateur temporairement")
    @app_commands.describe(user="Utilisateur à bannir", reason="Raison du ban", duration_minutes="Durée du ban en minutes", id_message="ID du message (optionnel)")
    @is_admin()
    @enqueue_request()
    async def ban_temp(self, interaction: discord.Interaction, user: discord.Member, reason: str, duration_minutes: int, id_message: Optional[str] = None):
        if not await self.ask_confirmation(interaction, f"Confirmez-vous le ban temporaire de {user.mention} pour {duration_minutes} minutes ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)
        await self.backup_roles_and_apply_ban(user, "temp", reason, interaction.user, duration_minutes=duration_minutes)
        end_time = (datetime.utcnow() + timedelta(minutes=duration_minutes)).strftime("%Y-%m-%d %H:%M:%S UTC")
        await interaction.followup.send(f"{user.display_name} a été banni temporairement jusqu'au {end_time}. Raison: {reason}", ephemeral=True)
        logger.info(f"{interaction.user} a banni {user.display_name} temp. Raison: {reason}, Durée: {duration_minutes}min")

    @app_commands.command(name="demande_deban", description="Demander un déban")
    @enqueue_request()
    async def demande_deban(self, interaction: discord.Interaction, raison: str):
        guild = interaction.guild
        if not guild:
            return await interaction.followup.send("Cette commande doit être utilisée sur un serveur.", ephemeral=True)

        mod_data = await self.get_moderation_data()
        ban_info = mod_data["bans"].get(str(interaction.user.id))
        if not ban_info:
            return await interaction.followup.send("Vous n'êtes pas banni.", ephemeral=True)

        demande_deban_channel = discord.utils.get(guild.text_channels, name="demande-deban")
        if not demande_deban_channel:
            return await interaction.followup.send("Le canal #demande-deban est introuvable.", ephemeral=True)

        banned_by = guild.get_member(ban_info["banned_by"])
        banned_at = ban_info["banned_at"]
        ban_end = ban_info["ban_end"]
        ban_type = ban_info["ban_type"]
        ban_reason = ban_info["ban_reason"]

        embed = discord.Embed(title="Demande de Déban", color=discord.Color.orange())
        embed.add_field(name="Utilisateur Banni", value=interaction.user.mention, inline=False)
        embed.add_field(name="Banni par", value=banned_by.mention if banned_by else ban_info["banned_by"], inline=False)
        embed.add_field(name="Raison du ban", value=ban_reason, inline=False)
        embed.add_field(name="Date du ban", value=banned_at, inline=False)
        if ban_type == "temp" and ban_end:
            embed.add_field(name="Fin du ban", value=ban_end, inline=False)
        embed.add_field(name="Raison du déban", value=raison, inline=False)

        view = UnbanView(self, interaction.user.id)
        request_msg = await demande_deban_channel.send(embed=embed, view=view)
        ban_info["unban_request_msg_id"] = request_msg.id
        ban_info["unban_request_channel_id"] = demande_deban_channel.id
        mod_data["bans"][str(interaction.user.id)] = ban_info
        await self.save_moderation_data(mod_data)

        await interaction.followup.send("Votre demande de déban a été envoyée.", ephemeral=True)

    @app_commands.command(name="unban", description="Débannir un utilisateur")
    @app_commands.describe(user="Utilisateur à débannir", reason="Raison du déban (optionnel)")
    @is_admin()
    @enqueue_request()
    async def unban(self, interaction: discord.Interaction, user: discord.User, reason: Optional[str] = None):
        if not await self.ask_confirmation(interaction, f"Confirmez-vous le unban de {user.mention} ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)
        await self.unban_user(interaction, user.id, reason=reason)
        await interaction.followup.send(f"{user.mention} a été débanni. Raison: {reason or 'Aucune raison'}", ephemeral=True)

    @app_commands.command(name="avertissement", description="Mettre un avertissement à un utilisateur")
    @app_commands.describe(user="Utilisateur à avertir", reason="Raison de l'avertissement")
    @is_admin()
    @enqueue_request()
    async def avertissement(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        if not await self.ask_confirmation(interaction, f"Confirmez-vous l'avertissement pour {user.mention} ?"):
            return await interaction.followup.send("Action annulée.", ephemeral=True)

        mod_data = await self.get_moderation_data()
        warnings = mod_data.setdefault("warnings", {})
        user_warnings = warnings.get(str(user.id), 0)
        user_warnings += 1
        warnings[str(user.id)] = user_warnings
        await self.save_moderation_data(mod_data)

        try:
            await user.send(f"Vous avez reçu un avertissement sur {interaction.guild.name}. Raison: {reason}\nTotal avertissements: {user_warnings}")
        except:
            pass

        if user_warnings == 3:
            await self.backup_roles_and_apply_ban(user, "temp", f"Avertissements: {user_warnings}", interaction.user, duration_minutes=10080)
            await interaction.followup.send(f"{user.display_name} a atteint 3 avertissements et est banni 1 semaine.", ephemeral=True)
        elif user_warnings == 5:
            await self.backup_roles_and_apply_ban(user, "perma", f"Avertissements: {user_warnings}", interaction.user)
            await interaction.followup.send(f"{user.display_name} a atteint 5 avertissements et est banni définitivement.", ephemeral=True)
        else:
            await interaction.followup.send(f"{user.display_name} a maintenant {user_warnings} avertissements. Raison: {reason}", ephemeral=True)

    @ban_perma.error
    @ban_temp.error
    @demande_deban.error
    @unban.error
    @avertissement.error
    async def moderation_command_error(self, interaction: discord.Interaction, error: Exception):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.followup.send(
                "Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True
            )
            logger.warning(f"{interaction.user} a tenté d'utiliser une commande de modération sans permissions.")
        else:
            await interaction.followup.send(
                "Une erreur est survenue lors de l'exécution de la commande.",
                ephemeral=True
            )
            logger.exception(f"Erreur lors d'une commande modération par {interaction.user}: {error}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
    logger.info("Moderation Cog chargé avec succès.")
