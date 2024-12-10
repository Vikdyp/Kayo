# cogs/reputation/reputation.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import datetime
from cogs.utilities.data_manager import DataManager
from cogs.utilities.request_manager import enqueue_request
from typing import Any

logger = logging.getLogger('discord.reputation')

class Reputation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()

    async def get_reputation_data(self):
        return await self.data.get_reputation_data()

    async def save_reputation_data(self, rep_data):
        await self.data.save_reputation_data(rep_data)

    def today_str(self):
        return datetime.utcnow().strftime("%Y-%m-%d")

    async def update_player_role(self, member: discord.Member, reports_count: int, recommendations_count: int):
        ratio = (recommendations_count + 1) / (reports_count + 1)
        guild = member.guild
        bon_joueur_role = discord.utils.get(guild.roles, name="bon joueur")
        mauvais_joueur_role = discord.utils.get(guild.roles, name="mauvais joueur")

        # Retirer les deux rôles si présents
        roles_to_remove = []
        if bon_joueur_role and bon_joueur_role in member.roles:
            roles_to_remove.append(bon_joueur_role)
        if mauvais_joueur_role and mauvais_joueur_role in member.roles:
            roles_to_remove.append(mauvais_joueur_role)
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason="Mise à jour du statut joueur")

        # Ajouter le rôle approprié
        if ratio > 1:
            # bon joueur
            if bon_joueur_role:
                await member.add_roles(bon_joueur_role, reason="Joueur ratio > 1")
        else:
            # mauvais joueur
            if mauvais_joueur_role:
                await member.add_roles(mauvais_joueur_role, reason="Joueur ratio <= 1")

    def count_reports_for_user(self, rep_data, user_id: str):
        reports_count = 0
        for rid, rinfo in rep_data.get("reports", {}).items():
            if user_id in rinfo["targets"]:
                # rinfo["targets"][user_id] = { "dates": [list_of_dates] }
                # On compte le nombre total de reports sur cette cible
                reports_count += len(rinfo["targets"][user_id]["dates"])
        return reports_count

    def count_recommendations_for_user(self, rep_data, user_id: str):
        reco_count = 0
        for rid, rinfo in rep_data.get("recommendations", {}).items():
            if user_id in rinfo["targets"]:
                # rinfo["targets"][user_id] = { "dates": [list_of_dates] }
                reco_count += len(rinfo["targets"][user_id]["dates"])
        return reco_count

    @app_commands.command(name="recommend", description="Recommande un utilisateur (max 1/jour par cible, max 5 fois par cible au total)")
    @app_commands.describe(user="Utilisateur à recommander")
    @enqueue_request()
    async def recommend(self, interaction: Any, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        if user.id == interaction.user.id:
            return await interaction.followup.send("Vous ne pouvez pas vous recommander vous-même.", ephemeral=True)

        rep_data = await self.get_reputation_data()
        recommendations = rep_data.setdefault("recommendations", {})
        recommender_id = str(interaction.user.id)
        recommended_id = str(user.id)
        recommender_info = recommendations.setdefault(recommender_id, {"targets":{}})

        target_info = recommender_info["targets"].setdefault(recommended_id, {"dates":[]})

        today = self.today_str()
        # Vérifier si déjà recommandé cet utilisateur aujourd'hui
        if today in target_info["dates"]:
            return await interaction.followup.send("Vous avez déjà recommandé cet utilisateur aujourd'hui.", ephemeral=True)

        # Vérifier si déjà recommandé 5 fois au total cet utilisateur
        if len(target_info["dates"]) >= 5:
            return await interaction.followup.send("Vous avez déjà recommandé cet utilisateur 5 fois au total.", ephemeral=True)

        # Ajouter la recommandation
        target_info["dates"].append(today)
        await self.save_reputation_data(rep_data)

        await interaction.followup.send(f"{user.mention} a été recommandé !", ephemeral=True)

        # Mettre à jour les rôles du "user"
        user_reports_count = self.count_reports_for_user(rep_data, recommended_id)
        user_reco_count = self.count_recommendations_for_user(rep_data, recommended_id)
        await self.update_player_role(user, user_reports_count, user_reco_count)

    @app_commands.command(name="report", description="Report un utilisateur (max 1/jour par cible, max 5 fois par cible au total)")
    @app_commands.describe(user="Utilisateur à reporter", reason="Raison du report")
    @enqueue_request()
    async def report(self, interaction: Any, user: discord.Member, reason: str):
        await interaction.response.defer(ephemeral=True)
        if user.id == interaction.user.id:
            return await interaction.followup.send("Vous ne pouvez pas vous report vous-même.", ephemeral=True)

        rep_data = await self.get_reputation_data()
        reports = rep_data.setdefault("reports", {})
        reporter_id = str(interaction.user.id)
        reported_id = str(user.id)
        reporter_info = reports.setdefault(reporter_id, {"targets":{}})

        target_info = reporter_info["targets"].setdefault(reported_id, {"dates":[]})

        today = self.today_str()
        # Vérifier si déjà reporté cet utilisateur aujourd'hui
        if today in target_info["dates"]:
            return await interaction.followup.send("Vous avez déjà reporté cet utilisateur aujourd'hui.", ephemeral=True)

        # Vérifier si déjà reporté 5 fois au total cet utilisateur
        if len(target_info["dates"]) >= 5:
            return await interaction.followup.send("Vous avez déjà reporté cet utilisateur 5 fois au total.", ephemeral=True)

        # Ajouter le report
        target_info["dates"].append(today)
        await self.save_reputation_data(rep_data)

        await interaction.followup.send(f"{user.mention} a été report pour {reason}", ephemeral=True)

        # Mettre à jour les rôles du "user"
        user_reports_count = self.count_reports_for_user(rep_data, reported_id)
        user_reco_count = self.count_recommendations_for_user(rep_data, reported_id)
        await self.update_player_role(user, user_reports_count, user_reco_count)

    @app_commands.command(name="reputation", description="Affiche la réputation d'un utilisateur")
    @app_commands.describe(user="Utilisateur dont on veut la réputation")
    @enqueue_request()
    async def reputation_cmd(self, interaction: Any, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        rep_data = await self.get_reputation_data()

        uid = str(user.id)
        reports_count = self.count_reports_for_user(rep_data, uid)
        reco_count = self.count_recommendations_for_user(rep_data, uid)

        ratio = (reco_count + 1) / (reports_count + 1)
        embed = discord.Embed(title=f"Réputation de {user.display_name}", color=discord.Color.blue())
        embed.add_field(name="Reports", value=str(reports_count), inline=True)
        embed.add_field(name="Recommandations", value=str(reco_count), inline=True)
        embed.add_field(name="Ratio (Reco+1)/(Reports+1)", value=f"{ratio:.2f}", inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Reputation(bot))
    logger.info("Reputation Cog chargé avec succès.")
