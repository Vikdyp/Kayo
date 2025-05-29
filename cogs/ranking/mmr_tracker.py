import io
import logging
from datetime import datetime, date, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import discord
from discord import File
from discord.ext import commands, tasks
from discord import app_commands

from cogs.ranking.services.mmr_tracker_service import ValorantService

logger = logging.getLogger('valorant_mmr')

class MMRTracker(commands.Cog):
    """Suivi automatique du MMR toutes les 5 minutes + gestion via une commande unique."""

    ACTION_CHOICES = [
        app_commands.Choice(name="Activer le suivi", value="activer"),
        app_commands.Choice(name="Désactiver le suivi", value="desactiver"),
        app_commands.Choice(name="Afficher les stats", value="afficher"),
    ]

    PERIOD_CHOICES = [
        app_commands.Choice(name="Aujourd'hui", value="today"),
        app_commands.Choice(name="Cette semaine", value="week"),
        app_commands.Choice(name="Ce mois", value="month"),
        app_commands.Choice(name="Total", value="all"),
    ]

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_loop.start()

    def cog_unload(self):
        self.check_loop.cancel()

    @tasks.loop(minutes=5)
    async def check_loop(self):
        rows = await ValorantService.get_tracked_players()
        for user_id, current_elo in [(r["user_id"], r["elo"]) for r in rows]:
            if current_elo is None:
                continue
            last = await ValorantService.get_last_elo(user_id)
            if last is None:
                await ValorantService.record_elo(user_id, current_elo, is_win=True)
            elif current_elo != last:
                await ValorantService.record_elo(user_id, current_elo, is_win=(current_elo > last))

    @app_commands.command(name="mmr_track", description="Gérer le suivi MMR : activer, désactiver ou afficher les stats.")
    @app_commands.describe(action="Action à effectuer", periode="Période des stats")
    @app_commands.choices(action=ACTION_CHOICES, periode=PERIOD_CHOICES)
    @app_commands.default_permissions(administrator=False)
    async def mmr_track(self, interaction: discord.Interaction, action: app_commands.Choice[str], periode: app_commands.Choice[str] = None):
        discord_id = interaction.user.id
        # Activer/Désactiver: réponses éphémères
        if action.value in ("activer", "desactiver"):
            await interaction.response.defer(ephemeral=True)
            if action.value == "activer":
                await ValorantService.enable_tracking(discord_id)
                return await interaction.followup.send("✅ Suivi MMR activé.", ephemeral=True)
            else:
                await ValorantService.disable_tracking(discord_id)
                return await interaction.followup.send("⏸️ Suivi MMR désactivé.", ephemeral=True)

        # Afficher les stats: réponse publique
        await interaction.response.defer(ephemeral=False)
        # Validation de la période
        period = periode.value if periode else "today"
        now = datetime.utcnow()
        start_date = date.today()
        if period == "week":
            start_date = (now - timedelta(days=now.weekday())).date()
        elif period == "month":
            start_date = now.replace(day=1).date()
        elif period == "all":
            start_date = None  # pas de filtre

        # Récupération de l'historique complet
        history = await ValorantService.get_history(discord_id)
        if len(history) < 2:
            return await interaction.followup.send("Aucun historique disponible.")

        # Calcul des diffs selon la période
        diffs = []  # listes de diffs
        for i in range(1, len(history)):
            t = history[i]["recorded_at"]
            if start_date and t.date() < start_date:
                continue
            diff = history[i]["elo"] - history[i-1]["elo"]
            diffs.append((t, diff))

        if not diffs:
            return await interaction.followup.send(f"Aucune game enregistrée pour la période '{period}'.")

        total_games = len(diffs)
        total_change = sum(d for _, d in diffs)
        wins = [d for _, d in diffs if d > 0]
        losses = [d for _, d in diffs if d < 0]
        avg_win = round(sum(wins) / len(wins)) if wins else 0
        avg_loss = round(sum(losses) / len(losses)) if losses else 0
        last_diff = diffs[-1][1]

        # Génération du graphique complet
        dates = [row["recorded_at"] for row in history if not start_date or row["recorded_at"].date() >= start_date]
        elos = [row["elo"] for row in history if not start_date or row["recorded_at"].date() >= start_date]
        buf = io.BytesIO()
        plt.figure()
        plt.plot(dates, elos)
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M' if period != 'all' else '%Y-%m-%d'))
        plt.title(f"Évolution MMR ({period})")
        plt.xlabel("Heure" if period != 'all' else "Date")
        plt.ylabel("ELO")
        plt.tight_layout()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close()

        # Construction de l'embed
        display_period = {
            'today': "Aujourd'hui",
            'week': "Cette semaine",
            'month': "Ce mois",
            'all': "Total",
        }[period]
        embed = discord.Embed(
            title=f"📊 Stats MMR – {display_period}",
            description=(
                f"Total games: **{total_games}**\n"
                f"Total {display_period.lower()}: **{total_change:+d}**\n"
                f"Moyenne win: **{avg_win:+d}**\n"
                f"Moyenne loss: **{avg_loss:+d}**\n"
                f"Dernière game: **{last_diff:+d}**"
            ),
            timestamp=datetime.utcnow()
        )
        file = File(buf, filename="mmr_history.png")
        embed.set_image(url="attachment://mmr_history.png")
        await interaction.followup.send(embed=embed, file=file)

async def setup(bot: commands.Bot):
    await bot.add_cog(MMRTracker(bot))
    logger.info("MMRTracker Cog chargé.")