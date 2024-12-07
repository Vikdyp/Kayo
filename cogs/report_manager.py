import discord
from discord.ext import commands
from discord import app_commands
import json
import logging
import os
from datetime import datetime, timedelta

class ReportManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.report_channel_id = 1236496216796172330  # Channel ID for storing reports and recommendations
        self.notification_channel_id = 1236438027195387914  # Channel ID for notification about bad players
        self.banned_channel_id = 1243941315549466654  # Channel ID for banned users to explain themselves
        self.good_player_role_name = "Bon Joueur"
        self.bad_player_role_name = "Mauvais Joueur"
        self.banned_role_id = 1243940542195306537  # Role ID for banned users
        self.admin_role_id = 1236375048252817418  # Role ID for admins
        self.report_data_file = 'report_data.json'
        self.warning_data_file = 'warning_data.json'
        self.role_backup_file = 'role_backup.json'
        self.report_data = self.load_json_data(self.report_data_file)
        self.warning_data = self.load_json_data(self.warning_data_file)
        self.role_backup = self.load_json_data(self.role_backup_file)

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"{self.bot.user.name} est prêt.")

    def load_json_data(self, file_path):
        """Load JSON data from a file"""
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logging.error(f"Le fichier JSON {file_path} est vide ou mal formaté. Initialisation avec des données vides.")
                return {}
        return {}

    def save_json_data(self, file_path, data):
        """Save JSON data to a file"""
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)

    @app_commands.command(name="report", description="Signaler un utilisateur")
    @app_commands.describe(member="L'utilisateur à signaler")
    async def report(self, interaction: discord.Interaction, member: discord.Member):
        await self.handle_action(interaction, member, "report")

    @app_commands.command(name="recommend", description="Recommander un utilisateur")
    @app_commands.describe(member="L'utilisateur à recommander")
    async def recommend(self, interaction: discord.Interaction, member: discord.Member):
        await self.handle_action(interaction, member, "recommend")

    async def handle_action(self, interaction: discord.Interaction, member: discord.Member, action: str):
        if action not in ["report", "recommend"]:
            return await interaction.response.send_message("Action non reconnue.", ephemeral=True)

        target_id = str(member.id)
        user_id = str(interaction.user.id)
        current_time = datetime.utcnow()

        if target_id not in self.report_data:
            self.report_data[target_id] = {"reports": [], "recommends": []}

        # Check if the user has already reported/recommended this member in the last month
        if action == "report":
            user_reports = [r for r in self.report_data[target_id]["reports"] if r["user_id"] == user_id]
            if user_reports and (current_time - datetime.fromisoformat(user_reports[-1]["timestamp"])).days < 30:
                return await interaction.response.send_message(f"Vous avez déjà signalé {member.display_name} ce mois-ci.", ephemeral=True)
            self.report_data[target_id]["reports"].append({"user_id": user_id, "timestamp": current_time.isoformat()})
        else:
            user_recommends = [r for r in self.report_data[target_id]["recommends"] if r["user_id"] == user_id]
            if user_recommends and (current_time - datetime.fromisoformat(user_recommends[-1]["timestamp"])).days < 30:
                return await interaction.response.send_message(f"Vous avez déjà recommandé {member.display_name} ce mois-ci.", ephemeral=True)
            self.report_data[target_id]["recommends"].append({"user_id": user_id, "timestamp": current_time.isoformat()})

        self.save_json_data(self.report_data_file, self.report_data)
        await interaction.response.send_message(f"{member.display_name} a été {'signalé' if action == 'report' else 'recommandé'} avec succès.", ephemeral=True)

        await self.update_roles(member)

    async def update_roles(self, member: discord.Member):
        target_id = str(member.id)
        reports = len(self.report_data[target_id]["reports"])
        recommends = len(self.report_data[target_id]["recommends"])

        if reports == recommends:
            ratio = 1.0
        else:
            ratio = recommends / reports if reports > 0 else recommends

        guild = member.guild
        good_player_role = discord.utils.get(guild.roles, name=self.good_player_role_name)
        bad_player_role = discord.utils.get(guild.roles, name=self.bad_player_role_name)

        if ratio >= 1:
            if bad_player_role in member.roles:
                await member.remove_roles(bad_player_role)
            if good_player_role not in member.roles:
                await member.add_roles(good_player_role)
        else:
            if good_player_role in member.roles:
                await member.remove_roles(good_player_role)
            if bad_player_role not in member.roles:
                await member.add_roles(bad_player_role)

        if ratio <= 0.5 and (reports >= 10 or recommends >= 10):
            await self.notify_admins(member, ratio, reports, recommends)

    async def notify_admins(self, member, ratio, reports, recommends):
        channel = self.bot.get_channel(self.notification_channel_id)
        embed = discord.Embed(
            title="Alerte de comportement",
            description=(
                f"{member.display_name} a un mauvais ratio de signalements/recommandations ({ratio:.2f}).\n"
                f"Signalements : {reports}\n"
                f"Recommandations : {recommends}\n"
                f"Avertissements : {self.warning_data.get(str(member.id), 0)}"
            ),
            color=discord.Color.red()
        )
        view = AdminActionsView(member, self)
        await channel.send(embed=embed, view=view)

    @app_commands.command(name="reputation", description="Voir la réputation d'un utilisateur")
    @app_commands.describe(member="L'utilisateur dont vous voulez voir la réputation")
    async def reputation(self, interaction: discord.Interaction, member: discord.Member):
        target_id = str(member.id)
        if target_id not in self.report_data:
            return await interaction.response.send_message(f"Aucune donnée trouvée pour {member.display_name}.", ephemeral=True)

        reports = len(self.report_data[target_id]["reports"])
        recommends = len(self.report_data[target_id]["recommends"])

        if reports == recommends:
            ratio = 1.0
        else:
            ratio = recommends / reports if reports > 0 else recommends

        warnings = self.warning_data.get(target_id, 0)
        warning_text = f" (Avertissements : {warnings})" if warnings else ""

        if ratio >= 1:
            role_name = self.good_player_role_name
        else:
            role_name = self.bad_player_role_name

        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if role:
            await member.add_roles(role)

        await interaction.response.send_message(
            f"{member.display_name} a été signalé {reports} fois et recommandé {recommends} fois.\n"
            f"Ratio : {ratio:.2f}{warning_text}\n"
            f"Rôle assigné : {role_name}",
            ephemeral=True
        )

        if ratio < 1:
            notification_channel = self.bot.get_channel(self.notification_channel_id)
            await notification_channel.send(f"{member.display_name} a un mauvais ratio ({ratio:.2f}) de signalements/recommandations.")

    @app_commands.command(name="remove_reports", description="Retirer des signalements")
    @app_commands.describe(member="L'utilisateur dont vous voulez retirer les signalements", count="Le nombre de signalements à retirer")
    async def remove_reports(self, interaction: discord.Interaction, member: discord.Member, count: int):
        if not any(role.id == self.admin_role_id for role in interaction.user.roles):
            return await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)

        target_id = str(member.id)
        if target_id in self.report_data and self.report_data[target_id]["reports"]:
            self.report_data[target_id]["reports"] = self.report_data[target_id]["reports"][:-count]
            self.save_json_data(self.report_data_file, self.report_data)
            await interaction.response.send_message(f"{count} signalements retirés pour {member.display_name}.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Aucun signalement trouvé pour {member.display_name}.", ephemeral=True)

        await self.update_roles(member)

    @app_commands.command(name="remove_recommends", description="Retirer des recommandations")
    @app_commands.describe(member="L'utilisateur dont vous voulez retirer les recommandations", count="Le nombre de recommandations à retirer")
    async def remove_recommends(self, interaction: discord.Interaction, member: discord.Member, count: int):
        if not any(role.id == self.admin_role_id for role in interaction.user.roles):
            return await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)

        target_id = str(member.id)
        if target_id in self.report_data and self.report_data[target_id]["recommends"]:
            self.report_data[target_id]["recommends"] = self.report_data[target_id]["recommends"][:-count]
            self.save_json_data(self.report_data_file, self.report_data)
            await interaction.response.send_message(f"{count} recommandations retirées pour {member.display_name}.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Aucune recommandation trouvée pour {member.display_name}.", ephemeral=True)

        await self.update_roles(member)

    @app_commands.command(name="explain_ban", description="S'expliquer sur son bannissement")
    @app_commands.describe(reason="Raison de l'explication")
    async def explain_ban(self, interaction: discord.Interaction, reason: str):
        if self.banned_role_id not in [role.id for role in interaction.user.roles]:
            return await interaction.response.send_message("Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)

        if interaction.channel_id != self.banned_channel_id:
            return await interaction.response.send_message("Vous ne pouvez utiliser cette commande que dans le salon dédié.", ephemeral=True)

        admin_channel = self.bot.get_channel(self.notification_channel_id)
        embed = discord.Embed(
            title="Demande d'explication",
            description=(
                f"{interaction.user.display_name} a demandé à s'expliquer sur son bannissement.\n"
                f"Raison : {reason}"
            ),
            color=discord.Color.orange()
        )
        view = BanReviewView(interaction.user, self)
        await admin_channel.send(embed=embed, view=view)
        await interaction.response.send_message("Votre demande a été envoyée aux administrateurs.", ephemeral=True)

class AdminActionsView(discord.ui.View):
    def __init__(self, member, cog):
        super().__init__(timeout=None)
        self.member = member
        self.cog = cog

    @discord.ui.button(label="Avertir", style=discord.ButtonStyle.primary)
    async def warn_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == self.cog.admin_role_id for role in interaction.user.roles):
            return await interaction.response.send_message("Vous n'avez pas la permission d'utiliser ce bouton.", ephemeral=True)

        user_id = str(self.member.id)
        self.cog.warning_data[user_id] = self.cog.warning_data.get(user_id, 0) + 1
        self.cog.save_json_data(self.cog.warning_data_file, self.cog.warning_data)

        await self.member.send("Vous avez reçu un avertissement concernant votre comportement. Veuillez faire attention à vos actions.")
        await interaction.response.send_message(f"{self.member.display_name} a été averti(e).", ephemeral=True)

        if self.cog.warning_data[user_id] >= 3:
            await self.ban_user(interaction)

    @discord.ui.button(label="Timeout", style=discord.ButtonStyle.secondary)
    async def timeout_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == self.cog.admin_role_id for role in interaction.user.roles):
            return await interaction.response.send_message("Vous n'avez pas la permission d'utiliser ce bouton.", ephemeral=True)

        timeout_duration = timedelta(minutes=10)
        until = discord.utils.utcnow() + timeout_duration

        await self.member.timeout(until)
        await self.member.send("Vous avez été mis en timeout pour 10 minutes en raison de votre comportement.")
        await interaction.response.send_message(f"{self.member.display_name} a été mis en timeout.", ephemeral=True)

        user_id = str(self.member.id)
        self.cog.warning_data[user_id] = self.cog.warning_data.get(user_id, 0) + 1
        self.cog.save_json_data(self.cog.warning_data_file, self.cog.warning_data)

    @discord.ui.button(label="Bannir", style=discord.ButtonStyle.danger)
    async def ban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == self.cog.admin_role_id for role in interaction.user.roles):
            return await interaction.response.send_message("Vous n'avez pas la permission d'utiliser ce bouton.", ephemeral=True)

        await self.ban_user(interaction)

    async def ban_user(self, interaction):
        user_id = str(self.member.id)
        guild = self.member.guild
        roles = self.member.roles
        self.cog.role_backup[user_id] = [role.id for role in roles if role.id != guild.default_role.id]
        self.cog.save_json_data(self.cog.role_backup_file, self.cog.role_backup)

        for role in roles:
            if role.id != guild.default_role.id:
                await self.member.remove_roles(role)

        banned_role = guild.get_role(self.cog.banned_role_id)
        await self.member.add_roles(banned_role)

        await self.member.send("Vous avez été banni du serveur. Vous pouvez vous expliquer dans le canal réservé.")
        await interaction.response.send_message(f"{self.member.display_name} a été banni(e).", ephemeral=True)

class BanReviewView(discord.ui.View):
    def __init__(self, member, cog):
        super().__init__(timeout=None)
        self.member = member
        self.cog = cog

    @discord.ui.button(label="Retirer le ban", style=discord.ButtonStyle.success)
    async def unban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == self.cog.admin_role_id for role in interaction.user.roles):
            return await interaction.response.send_message("Vous n'avez pas la permission d'utiliser ce bouton.", ephemeral=True)

        user_id = str(self.member.id)
        guild = self.member.guild
        banned_role = guild.get_role(self.cog.banned_role_id)
        await self.member.remove_roles(banned_role)

        if user_id in self.cog.role_backup:
            roles = [guild.get_role(role_id) for role_id in self.cog.role_backup[user_id]]
            for role in roles:
                await self.member.add_roles(role)
            del self.cog.role_backup[user_id]
            self.cog.save_json_data(self.cog.role_backup_file, self.cog.role_backup)

        if user_id in self.cog.warning_data:
            del self.cog.warning_data[user_id]
            self.cog.save_json_data(self.cog.warning_data_file, self.cog.warning_data)

        await self.member.send("Votre ban a été retiré. Veuillez faire attention à votre comportement à l'avenir.")
        await interaction.response.send_message(f"{self.member.display_name} a été débanni(e) et ses rôles ont été restaurés.", ephemeral=True)
        await interaction.message.delete()

    @discord.ui.button(label="Bannir définitivement", style=discord.ButtonStyle.danger)
    async def permanent_ban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == self.cog.admin_role_id for role in interaction.user.roles):
            return await interaction.response.send_message("Vous n'avez pas la permission d'utiliser ce bouton.", ephemeral=True)

        await self.member.ban(reason="Bannissement permanent")
        await interaction.response.send_message(f"{self.member.display_name} a été banni(e) définitivement du serveur.", ephemeral=True)
        await interaction.message.delete()

async def setup(bot):
    await bot.add_cog(ReportManager(bot))
