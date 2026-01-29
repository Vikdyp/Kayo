import io
import logging
import re
from datetime import datetime, date, timedelta
from matplotlib.collections import LineCollection
from matplotlib.patches import PathPatch
from matplotlib.path import Path
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import discord
from discord import File
from discord.ext import commands, tasks
from discord import app_commands
from typing import List, Optional

import numpy as np

from cogs.ranking.services.mmr_tracker_service import ValorantService
from utils.checks import valorant_link_required

logger = logging.getLogger(__name__)

class MMRTracker(commands.Cog):
    """Suivi automatique du MMR toutes les 5 minutes + gestion via une commande unique."""

    ACTION_CHOICES = [
        app_commands.Choice(name="Activer le suivi", value="activer"),
        app_commands.Choice(name="Désactiver le suivi", value="desactiver"),
        app_commands.Choice(name="Afficher les stats", value="afficher"),
    ]

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Initialisation des attributs liés à la partition Valorant
        self._partition_date   = None  # date pour laquelle la partition a déjà été récupérée
        self._partition_season = None  # saison récupérée pour la date en cours
        self._partition_act    = None  # act récupéré pour la date en cours

        self.check_loop.start()

    def cog_unload(self):
        self.check_loop.cancel()

    @tasks.loop(minutes=5)
    async def check_loop(self):
        rows = await ValorantService.get_tracked_players()
        today = date.today()

        # Si on commence une nouvelle journée, on réinitialise le flag ET les valeurs de saison/act
        if self._partition_date is None or self._partition_date != today:
            self._partition_date   = None
            self._partition_season = None
            self._partition_act    = None

        for r in rows:
            user_id     = r["user_id"]
            current_elo = r["elo"]
            if current_elo is None:
                continue

            # 1) Récupérer le dernier ELO historisé
            last = await ValorantService.get_last_history_row(user_id)
            prev_elo = last["elo"] if last else None

            # 2) Si l'ELO n'a pas bougé, on passe au joueur suivant
            if prev_elo is not None and current_elo == prev_elo:
                continue

            # 3) Premier changement d'ELO de la journée → on calcule (et stocke) la partition
            if self._partition_date is None:
                logger.info(f"[check_loop] Avant fetch_current_partition → user_id={user_id}  today={today}")
                season, act = await ValorantService.fetch_current_partition(user_id)
                logger.info(f"[check_loop] Après fetch_current_partition → user_id={user_id}, season={season}, act={act}, today={today}")

                self._partition_date   = today
                self._partition_season = season
                self._partition_act    = act

            # 4) Calcul du delta (RR) et détermination win/loss
            rr     = 0 if prev_elo is None else (current_elo - prev_elo)
            is_win = rr >= 0

            # 5) Construction de l'entrée avec la partition en cache
            entry = {
                "date":    datetime.utcnow().isoformat() + "Z",
                "elo":     current_elo,
                "rr":      rr,
                "season":  {"short": f"e{self._partition_season}a{self._partition_act}"}
            }

            # 6) Insertion idempotente dans la bonne partition
            await ValorantService.insert_history_entry(user_id, entry)

    @app_commands.command(name="mmr_track", description="Gérer le suivi MMR : activer, désactiver ou afficher les stats.")
    @valorant_link_required()
    @app_commands.describe(periode="Période à afficher (today, week, all, ou episode/act)")
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
        dates_plot = [row["recorded_at"] for row in history if not start_date or row["recorded_at"].date() >= start_date]
        elos_plot  = [row["elo"]         for row in history if not start_date or row["recorded_at"].date() >= start_date]

        # Conversion pour Matplotlib
        mpl_dates = mdates.date2num(dates_plot)

        # Choix du fill dégradé global (vert si dernier > premier, rouge sinon)
        cmap_fill = 'Greens' if elos_plot[-1] > elos_plot[0] else 'Reds'

        # Préparation des segments colorés (vert/rouge selon progression locale)
        points   = np.array([mpl_dates, elos_plot]).T.reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        seg_colors = [
            'green' if elos_plot[i+1] > elos_plot[i] else 'red'
            for i in range(len(elos_plot)-1)
        ]

        # Création du plot
        buf = io.BytesIO()
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(10, 4), dpi=150)

        #  — Dégradé clipé sous la courbe —
        ymin = min(elos_plot) - 10
        gradient = np.linspace(1, 0, 256).reshape(256, 1)  # opaque→transparent
        im = ax.imshow(
            gradient,
            extent=[mpl_dates.min(), mpl_dates.max(), ymin, max(elos_plot)],
            origin='lower',
            cmap=plt.get_cmap(cmap_fill),
            alpha=0.5,
            aspect='auto',
            zorder=1
        )
        poly = np.vstack([
            [mpl_dates[0], ymin],
            np.column_stack([mpl_dates, elos_plot]),
            [mpl_dates[-1], ymin],
            [mpl_dates[0], ymin]
        ])
        im.set_clip_path(PathPatch(Path(poly), transform=ax.transData))

        #  — Segments colorés —
        lc = LineCollection(segments, colors=seg_colors, linewidths=2.5, zorder=3)
        ax.add_collection(lc)

        #  — Glow « maison » sous chaque segment —
        for seg, col in zip(segments, seg_colors):
            ax.plot(seg[:,0], seg[:,1],
                    linewidth=8,
                    solid_capstyle='round',
                    color=col,
                    alpha=0.2,
                    zorder=2)

        #  — Axes et formatage des dates —
        if period == 'today':
            fmt = '%H:%M'
            xlabel = "Heure"
        else:
            fmt = '%Y-%m-%d'
            xlabel = "Date"
        ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.set_xlabel(xlabel, fontsize=12)

        #  — Pas de grille verticale —
        ax.grid(False)
        ax.xaxis.grid(False)

        #  — Titres et labels —
        title = {
            'today': "Aujourd'hui",
            'week': "7 derniers jours",
            'all':   "Total"
        }.get(period, f"Episode {season_num} • Act {act_num}")
        ax.set_title(f"Évolution MMR ({title})", fontsize=14, fontweight='bold')
        ax.set_xlabel("Heure" if period != 'all' else "Date", fontsize=12)
        ax.set_ylabel("ELO", fontsize=12)

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.set_ylim(ymin, max(elos_plot) + 10)

        plt.tight_layout()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close(fig)

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
            app_commands.Choice(name="7 derniers jours", value="week"),
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
