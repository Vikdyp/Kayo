import io
import logging
import re
from datetime import datetime, date, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import discord
from discord import File
from discord.ext import commands, tasks
from discord import app_commands
from typing import List, Optional

from cogs.ranking.services.mmr_tracker_service import ValorantService

logger = logging.getLogger('valorant_mmr')

class MMRTracker(commands.Cog):
    """Suivi automatique du MMR toutes les 5 minutes + gestion via une commande unique."""

    ACTION_CHOICES = [
        app_commands.Choice(name="Activer le suivi", value="activer"),
        app_commands.Choice(name="Désactiver le suivi", value="desactiver"),
        app_commands.Choice(name="Afficher les stats", value="afficher"),
    ]

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_loop.start()

    def cog_unload(self):
        self.check_loop.cancel()

    from datetime import date, datetime

    @tasks.loop(minutes=5)
    async def check_loop(self):
        rows = await ValorantService.get_tracked_players()
        today = date.today()

        for r in rows:
            user_id     = r["user_id"]
            current_elo = r["elo"]
            if current_elo is None:
                continue

            # 1) On récupère le dernier elo historisé
            last = await ValorantService.get_last_history_row(user_id)
            prev_elo = last["elo"] if last else None

            # 2) Si l'elo n'a pas bougé, on skip
            if prev_elo is not None and current_elo == prev_elo:
                continue

            # 3) Premier changement de la journée → on fetch l'API et on met en cache
            if not hasattr(self, "_partition_date") or self._partition_date != today:
                self.current_season, self.current_act = await ValorantService.fetch_current_partition()
                self._partition_date = today

            # 4) Calcul du delta et du flag win/loss
            rr     = 0 if prev_elo is None else (current_elo - prev_elo)
            is_win = rr >= 0

            # 5) Construction de l'entry avec la partition en cache
            entry = {
                "date":    datetime.utcnow().isoformat() + "Z",
                "elo":     current_elo,
                "rr":      rr,
                "season":  {"short": f"e{self.current_season}a{self.current_act}"}
            }

            # 6) Insertion idempotente dans la bonne partition
            await ValorantService.insert_history_entry(user_id, entry)

    @app_commands.command(name="mmr_track", description="Gérer le suivi MMR : activer, désactiver ou afficher les stats.")
    @app_commands.describe(action="Action à effectuer", periode="Partition ou période à afficher")
    @app_commands.choices(action=ACTION_CHOICES)
    async def mmr_track(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        periode: Optional[str] = None
    ):
        discord_id = interaction.user.id

        # ACTIVER / DESACTIVER
        if action.value in ("activer", "desactiver"):
            await interaction.response.defer(thinking=True, ephemeral=True)
            if action.value == "activer":
                await ValorantService.enable_tracking(discord_id)
                await ValorantService.fetch_full_history(discord_id)
                return await interaction.followup.send("✅ Suivi MMR activé.", ephemeral=True)
            else:
                await ValorantService.disable_tracking(discord_id)
                return await interaction.followup.send("⏸️ Suivi MMR désactivé.", ephemeral=True)

        # AFFICHER LES STATS
        await interaction.response.defer(thinking=True, ephemeral=False)

        # 1) Détermination du filtre
        period = periode or "today"
        season_num: Optional[int] = None
        act_num:    Optional[int] = None
        start_date: Optional[date] = date.today()

        if period == "today":
            start_date = date.today()
        elif period == "all":
            start_date = None
        else:
            m = re.match(r"e(\d+)a(\d+)", period)
            if m:
                season_num, act_num = map(int, m.groups())
                start_date = None
            else:
                start_date = date.today()

        # 2) Récupération de l'historique filtré
        history = await ValorantService.get_history(discord_id, season_num, act_num)
        if len(history) < 2:
            return await interaction.followup.send("Aucun historique disponible.")

        # 3) Calcul des diffs
        diffs: List[tuple[datetime,int]] = []
        for i in range(1, len(history)):
            t = history[i]["recorded_at"]
            if start_date and t.date() < start_date:
                continue
            diff = history[i]["elo"] - history[i-1]["elo"]
            diffs.append((t, diff))

        if not diffs:
            return await interaction.followup.send(f"Aucune partie enregistrée pour la période '{period}'.")

        total_games  = len(diffs)
        total_change = sum(d for _, d in diffs)
        wins   = [d for _, d in diffs if d > 0]
        losses = [d for _, d in diffs if d < 0]
        avg_win  = round(sum(wins)/len(wins)) if wins else 0
        avg_loss = round(sum(losses)/len(losses)) if losses else 0
        last_diff = diffs[-1][1]

        # 4) Génération du graphique
        dates = [row["recorded_at"] for row in history if not start_date or row["recorded_at"].date() >= start_date]
        elos  = [row["elo"]         for row in history if not start_date or row["recorded_at"].date() >= start_date]

        buf = io.BytesIO()
        plt.figure()
        plt.plot(dates, elos)
        fmt = '%H:%M' if period != 'all' else '%Y-%m-%d'
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter(fmt))
        title = {
            'today': "Aujourd'hui",
            'all':   "Total"
        }.get(period, f"Episode {season_num} • Act {act_num}")
        plt.title(f"Évolution MMR ({title})")
        xlabel = "Heure" if period != 'all' else "Date"
        plt.xlabel(xlabel)
        plt.ylabel("ELO")
        plt.tight_layout()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close()

        # 5) Construction et envoi de l'embed
        embed = discord.Embed(
            title=f"📊 Stats MMR – {title}",
            description=(
                f"Total games: **{total_games}**\n"
                f"Total {title.lower()}: **{total_change:+d}**\n"
                f"Moyenne win: **{avg_win:+d}**\n"
                f"Moyenne loss: **{avg_loss:+d}**\n"
                f"Dernière game: **{last_diff:+d}**"
            ),
            timestamp=datetime.utcnow()
        )
        file = File(buf, filename="mmr_history.png")
        embed.set_image(url="attachment://mmr_history.png")
        await interaction.followup.send(embed=embed, file=file)

    @mmr_track.autocomplete("periode")
    async def periode_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        choices: List[app_commands.Choice[str]] = [
            app_commands.Choice(name="Aujourd'hui", value="today"),
            app_commands.Choice(name="Total",       value="all"),
        ]
        parts = await ValorantService.get_partitions(interaction.user.id)
        for season, act in parts:
            label = f"Episode {season} • Act {act}"
            value = f"e{season}a{act}"
            choices.append(app_commands.Choice(name=label, value=value))
        return [c for c in choices if current.lower() in c.value.lower()][:25]

async def setup(bot: commands.Bot):
    await bot.add_cog(MMRTracker(bot))
    logger.info("MMRTracker Cog chargé.")
