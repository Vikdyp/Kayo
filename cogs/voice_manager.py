import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone
import logging

class VoiceChannelManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tracked_channels = {}
        self.roles_to_monitor = {"Initiator", "Controller", "Duelist", "Sentinel", "Fill"}
        self.allowed_text_channels = {
            "fer": "Fer",
            "bronze": "Bronze",
            "argent": "Argent",
            "or": "Or",
            "platine": "Platine",
            "diamant": "Diamant",
            "ascendant": "Ascendant",
            "immortel": "Immortel"
        }
        self.check_empty_channels.start()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if after.channel and after.channel.id in self.tracked_channels:
            member_roles = {role.name for role in member.roles}
            conflicting_roles = self.roles_to_monitor.intersection(member_roles)

            for other_member in after.channel.members:
                if other_member != member:
                    other_roles = {role.name for role in other_member.roles}
                    if conflicting_roles.intersection(other_roles):
                        await member.move_to(None)
                        alternative_invite = await self.find_alternative_voice_channel(member, conflicting_roles)
                        if alternative_invite:
                            await member.send(f"Vous avez été déconnecté du salon **{after.channel.name}** en raison d'un conflit de rôle. Voici un lien vers un autre salon : {alternative_invite}")
                        else:
                            await member.send(f"Vous avez été déconnecté du salon **{after.channel.name}** en raison d'un conflit de rôle, mais aucun salon alternatif n'est disponible.")
                        break

    async def find_alternative_voice_channel(self, member, conflicting_roles):
        for channel in member.guild.voice_channels:
            if len(channel.members) < 5:
                members_roles = [role.name for member in channel.members for role in member.roles]
                if not conflicting_roles.intersection(set(members_roles)):
                    invite = await channel.create_invite(max_age=3600, max_uses=5)
                    return invite.url
        return None

    @app_commands.command(name="five_stack", description="Créer un salon vocal temporaire pour 5 personnes maximum")
    async def five_stack(self, interaction: discord.Interaction):
        channel_name = interaction.channel.name.lower()
        if channel_name not in self.allowed_text_channels:
            await interaction.response.send_message("Cette commande doit être envoyée dans un salon texte autorisé (fer, bronze, argent, or, platine, diamant, ascendant, immortel).", ephemeral=True)
            return

        role_name = self.allowed_text_channels[channel_name]

        guild = interaction.guild
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            await interaction.response.send_message(f"Le rôle correspondant au salon **{channel_name}** n'existe pas. Veuillez contacter un administrateur.", ephemeral=True)
            return

        existing_channel = None
        user_roles = {role.name for role in interaction.user.roles}
        for channel in guild.voice_channels:
            if channel.name.endswith("'s Channel") and role in channel.overwrites:
                channel_roles = {role.name for member in channel.members for role in member.roles}
                if user_roles & self.roles_to_monitor and user_roles & channel_roles:
                    existing_channel = channel
                    break

        if existing_channel:
            try:
                await interaction.user.move_to(existing_channel)
                await interaction.response.send_message(f"Vous avez été déplacé vers le salon vocal existant : {existing_channel.name}", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("Le bot n'a pas les permissions nécessaires pour déplacer l'utilisateur.", ephemeral=True)
            except discord.HTTPException as e:
                await interaction.response.send_message(f"Une erreur s'est produite lors du déplacement vers le salon vocal : {e}", ephemeral=True)
        else:
            voice_channel_name = f"{interaction.user.name}'s Channel"
            try:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(connect=False),
                    role: discord.PermissionOverwrite(connect=True, speak=True),
                    interaction.user: discord.PermissionOverwrite(connect=True, speak=True)
                }

                voice_channel = await guild.create_voice_channel(
                    voice_channel_name,
                    user_limit=5,
                    overwrites=overwrites
                )

                invite = await voice_channel.create_invite(max_age=3600, max_uses=5)

                invite_message = await interaction.response.send_message(f"Salon vocal créé : **{voice_channel.name}**\nVoici le lien d'invitation : {invite.url}")

                self.tracked_channels[voice_channel.id] = {
                    "voice_channel": voice_channel,
                    "invite_message": await interaction.original_response(),
                    "command_message": None,
                    "last_active": datetime.now(timezone.utc)
                }
            except discord.Forbidden:
                await interaction.response.send_message("Le bot n'a pas les permissions nécessaires pour créer un salon vocal.", ephemeral=True)
            except discord.HTTPException as e:
                await interaction.response.send_message(f"Une erreur s'est produite lors de la création du salon vocal : {e}", ephemeral=True)

    @tasks.loop(seconds=30)
    async def check_empty_channels(self):
        for channel_id, info in list(self.tracked_channels.items()):
            voice_channel = info["voice_channel"]
            if len(voice_channel.members) == 0:
                if (datetime.now(timezone.utc) - info["last_active"]).total_seconds() > 120:
                    try:
                        await voice_channel.delete()
                        await info["invite_message"].delete()
                        if info["command_message"]:
                            await info["command_message"].delete()
                        del self.tracked_channels[channel_id]
                    except discord.HTTPException as e:
                        logging.error(f"Erreur lors de la suppression du salon vocal ou des messages : {e}")
            else:
                self.tracked_channels[channel_id]["last_active"] = datetime.now(timezone.utc)

    @check_empty_channels.before_loop
    async def before_check_empty_channels(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(VoiceChannelManager(bot))
