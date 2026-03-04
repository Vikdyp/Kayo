# cogs/ranking/mmr_tracker.py

import io
import logging
import re
from datetime import datetime, date, timedelta

import discord
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from discord import File, app_commands
from discord.ext import commands, tasks
from matplotlib.collections import LineCollection
from matplotlib.patches import PathPatch
from matplotlib.path import Path
from typing import List, Optional

from cogs.ranking.services.mmr_tracker_service import MmrTrackerService

logger = logging.getLogger(__name__)


class MMRTracker(commands.Cog):
    """Suivi automatique du MMR toutes les 5 minutes + gestion via une commande unique."""

    ACTION_CHOICES = [
        app_commands.Choice(name="Activer le suivi", value="activer"),
        app_commands.Choice(name="Désactiver le suivi", value="desactiver"),
        app_commands.Choice(name="Afficher les stats", value="afficher"),
    ]

    def __init__(self, bot: commands.Bot, service: MmrTrackerService):
        self.bot = bot
        self._service = service

        self._partition_date: Optional[date] = None
        self._partition_season: Optional[int] = None
        self._partition_act: Optional[int] = None

        self.check_loop.start()

    def cog_unload(self):
        self.check_loop.cancel()

    @tasks.loop(minutes=5)
    async def check_loop(self):
        rows = await self._service.get_tracked_players()
        today = date.today()

        if self._partition_date is None or self._partition_date != today:
            self._partition_date = None
            self._partition_season = None
            self._partition_act = None

        for r in rows:
            user_id = r["user_id"]
            current_elo = r["elo"]
            if current_elo is None or current_elo <= 0:
                continue

            last = await self._service.get_last_history_row(user_id)
            prev_elo = last["elo"] if last else None

            if prev_elo is not None and current_elo == prev_elo:
                continue

            if self._partition_date is None:
                season, act = await self._service.fetch_current_partition(user_id)
                self._partition_date = today
                self._partition_season = season
                self._partition_act = act

            await self._service.record_elo_change(
                user_id, current_elo, prev_elo,
                self._partition_season, self._partition_act,
            )

    @app_commands.command(
        name="mmr_track",
        description="Gérer le suivi MMR : activer, désactiver ou afficher les stats.",
    )
    @app_commands.describe(periode="Période à afficher (today, week, all, ou episode/act)")
    @app_commands.choices(action=ACTION_CHOICES)
    async def mmr_track(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        periode: Optional[str] = None,
    ):
        discord_id = interaction.user.id

        # Vérifier que le compte Valorant est lié
        if not await self._service.account_linked(discord_id):
            return await interaction.response.send_message(
                "Tu dois d'abord lier ton compte Valorant avec `/link`.", ephemeral=True
            )

        # ACTIVER / DESACTIVER
        if action.value in ("activer", "desactiver"):
            await interaction.response.defer(thinking=True, ephemeral=True)
            if action.value == "activer":
                await self._service.enable_tracking(discord_id)
                await self._service.fetch_full_history(discord_id)
                return await interaction.followup.send("✅ Suivi MMR activé.", ephemeral=True)
            else:
                await self._service.disable_tracking(discord_id)
                return await interaction.followup.send("⏸️ Suivi MMR désactivé.", ephemeral=True)

        # AFFICHER LES STATS
        await interaction.response.defer(thinking=True, ephemeral=False)

        period = periode or "today"
        season_num: Optional[int] = None
        act_num: Optional[int] = None
        start_date: Optional[date] = date.today()

        if period == "today":
            start_date = date.today()
        elif period == "week":
            start_date = date.today() - timedelta(days=7)
        elif period == "all":
            start_date = None
        else:
            m = re.match(r"e(\d+)a(\d+)", period)
            if m:
                season_num, act_num = map(int, m.groups())
                start_date = None
            else:
                start_date = date.today()

        history = await self._service.get_history(discord_id, season_num, act_num)
        if len(history) < 2:
            return await interaction.followup.send("Aucun historique disponible.")

        # Calcul des diffs
        diffs: List[tuple[datetime, int]] = []
        for i in range(1, len(history)):
            t = history[i]["recorded_at"]
            if start_date and t.date() < start_date:
                continue
            diff = history[i]["elo"] - history[i - 1]["elo"]
            diffs.append((t, diff))

        if not diffs:
            return await interaction.followup.send(
                f"Aucune partie enregistrée pour la période '{period}'."
            )

        total_games = len(diffs)
        total_change = sum(d for _, d in diffs)
        wins = [d for _, d in diffs if d > 0]
        losses = [d for _, d in diffs if d < 0]
        avg_win = round(sum(wins) / len(wins)) if wins else 0
        avg_loss = round(sum(losses) / len(losses)) if losses else 0
        last_diff = diffs[-1][1]

        # Génération du graphique (filtrer elo <= 0)
        filtered = [
            row for row in history
            if (not start_date or row["recorded_at"].date() >= start_date)
            and row["elo"] > 0
        ]
        if len(filtered) < 2:
            return await interaction.followup.send(
                "Pas assez de données valides pour générer un graphique."
            )
        dates_plot = [row["recorded_at"] for row in filtered]
        elos_plot = [row["elo"] for row in filtered]

        buf = self._generate_graph(dates_plot, elos_plot, period, season_num, act_num)

        # Embed
        title = {
            "today": "Aujourd'hui",
            "week": "7 derniers jours",
            "all": "Total",
        }.get(period, f"Episode {season_num} • Act {act_num}")

        embed = discord.Embed(
            title=f"📊 Stats MMR – {title}",
            description=(
                f"Total games: **{total_games}**\n"
                f"Total {title.lower()}: **{total_change:+d}**\n"
                f"Moyenne win: **{avg_win:+d}**\n"
                f"Moyenne loss: **{avg_loss:+d}**\n"
                f"Dernière game: **{last_diff:+d}**"
            ),
            timestamp=datetime.utcnow(),
        )
        file = File(buf, filename="mmr_history.png")
        embed.set_image(url="attachment://mmr_history.png")
        await interaction.followup.send(embed=embed, file=file)

    @mmr_track.autocomplete("periode")
    async def periode_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        choices: List[app_commands.Choice[str]] = [
            app_commands.Choice(name="Aujourd'hui", value="today"),
            app_commands.Choice(name="7 derniers jours", value="week"),
            app_commands.Choice(name="Total", value="all"),
        ]
        parts = await self._service.get_partitions(interaction.user.id)
        for season, act in parts:
            label = f"Episode {season} • Act {act}"
            value = f"e{season}a{act}"
            choices.append(app_commands.Choice(name=label, value=value))
        return [c for c in choices if current.lower() in c.value.lower()][:25]

    @staticmethod
    def _generate_graph(
        dates_plot: list[datetime],
        elos_plot: list[int],
        period: str,
        season_num: Optional[int],
        act_num: Optional[int],
    ) -> io.BytesIO:
        mpl_dates = mdates.date2num(dates_plot)
        cmap_fill = "Greens" if elos_plot[-1] > elos_plot[0] else "Reds"

        points = np.array([mpl_dates, elos_plot]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        seg_colors = [
            "green" if elos_plot[i + 1] > elos_plot[i] else "red"
            for i in range(len(elos_plot) - 1)
        ]

        buf = io.BytesIO()
        plt.style.use("dark_background")
        fig, ax = plt.subplots(figsize=(10, 4), dpi=150)

        ymin = min(elos_plot) - 10
        gradient = np.linspace(1, 0, 256).reshape(256, 1)
        im = ax.imshow(
            gradient,
            extent=[mpl_dates.min(), mpl_dates.max(), ymin, max(elos_plot)],
            origin="lower",
            cmap=plt.get_cmap(cmap_fill),
            alpha=0.5,
            aspect="auto",
            zorder=1,
        )
        poly = np.vstack([
            [mpl_dates[0], ymin],
            np.column_stack([mpl_dates, elos_plot]),
            [mpl_dates[-1], ymin],
            [mpl_dates[0], ymin],
        ])
        im.set_clip_path(PathPatch(Path(poly), transform=ax.transData))

        lc = LineCollection(segments, colors=seg_colors, linewidths=2.5, zorder=3)
        ax.add_collection(lc)

        for seg, col in zip(segments, seg_colors):
            ax.plot(
                seg[:, 0], seg[:, 1],
                linewidth=8, solid_capstyle="round", color=col, alpha=0.2, zorder=2,
            )

        if period == "today":
            fmt = "%H:%M"
            xlabel = "Heure"
        else:
            fmt = "%Y-%m-%d"
            xlabel = "Date"
        ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.set_xlabel(xlabel, fontsize=12)

        ax.grid(False)
        ax.xaxis.grid(False)

        title = {
            "today": "Aujourd'hui",
            "week": "7 derniers jours",
            "all": "Total",
        }.get(period, f"Episode {season_num} • Act {act_num}")
        ax.set_title(f"Évolution MMR ({title})", fontsize=14, fontweight="bold")
        ax.set_ylabel("ELO", fontsize=12)

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_ylim(ymin, max(elos_plot) + 10)

        plt.tight_layout()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close(fig)
        return buf


async def setup(bot: commands.Bot):
    from database.services.valorant_info_service import ValorantInfoService
    from database.services.mmr_history_service import MmrHistoryService

    valorant_info_svc = getattr(bot, "valorant_info_svc", None) or ValorantInfoService(bot.db)
    mmr_history_svc = MmrHistoryService(bot.db)
    service = MmrTrackerService(valorant_info_svc, mmr_history_svc)

    await bot.add_cog(MMRTracker(bot, service))
    logger.info("MMRTracker Cog chargé.")
