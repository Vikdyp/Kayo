import logging
import re
from datetime import datetime, date, timedelta, timezone
import discord
from discord import File
from discord.ext import commands, tasks
from discord import app_commands
from typing import List, Optional

from cogs.ranking.renderers import build_mmr_history_chart, get_mmr_period_title
from cogs.ranking.services.mmr_tracker_service import MmrTrackerService

logger = logging.getLogger(__name__)


async def _valorant_link_required(interaction: discord.Interaction) -> bool:
    linked = await interaction.client.ranking_service.account_linked(interaction.user.id)
    if not linked:
        await interaction.response.send_message(
            "Tu dois d'abord lier ton compte Valorant avec `/link`.", ephemeral=True,
        )
    return linked


class MMRTracker(commands.Cog):
    """Suivi automatique du MMR toutes les 5 minutes + gestion via une commande unique."""

    ACTION_CHOICES = [
        app_commands.Choice(name="Activer le suivi", value="activer"),
        app_commands.Choice(name="Désactiver le suivi", value="desactiver"),
        app_commands.Choice(name="Afficher les stats", value="afficher"),
    ]

    def __init__(self, bot: commands.Bot, tracker_svc: MmrTrackerService):
        self.bot = bot
        self._tracker_svc = tracker_svc
        self.check_loop.start()

    def cog_unload(self):
        self.check_loop.cancel()

    @tasks.loop(minutes=5)
    async def check_loop(self):
        try:
            rows = await self._tracker_svc.get_tracked_players()
        except Exception as e:
            logger.exception(f"[check_loop] Impossible de recuperer les joueurs suivis: {e}")
            return

        for row in rows:
            try:
                await self._tracker_svc.record_current_mmr_snapshot(row)
            except Exception as e:
                logger.exception(
                    f"[check_loop] Erreur suivi MMR pour user_id={row.get('user_id')}: {e}"
                )

    @check_loop.before_loop
    async def before_check_loop(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="mmr_track", description="Gérer le suivi MMR : activer, désactiver ou afficher les stats.")
    @app_commands.check(_valorant_link_required)
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
                await self._tracker_svc.enable_tracking(discord_id)
                await self._tracker_svc.fetch_full_history(discord_id)
                return await interaction.followup.send("✅ Suivi MMR activé.", ephemeral=True)
            else:
                await self._tracker_svc.disable_tracking(discord_id)
                return await interaction.followup.send("⏸️ Suivi MMR désactivé.", ephemeral=True)

        # AFFICHER LES STATS
        await interaction.response.defer(thinking=True, ephemeral=False)

        # 1) Determination du filtre
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

        # 2) Recuperation de l'historique filtre (retourne des EloHistoryRow)
        history = await self._tracker_svc.get_history(discord_id, season_num, act_num)
        if len(history) < 2:
            return await interaction.followup.send("Aucun historique disponible.")

        # 3) Calcul des diffs
        diffs: List[tuple[datetime, int]] = []
        for i in range(1, len(history)):
            t = history[i].recorded_at
            if start_date and t.date() < start_date:
                continue
            diff = history[i].elo - history[i-1].elo
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

        # 4) Generation du graphique
        dates_plot = [row.recorded_at for row in history if not start_date or row.recorded_at.date() >= start_date]
        elos_plot  = [row.elo         for row in history if not start_date or row.recorded_at.date() >= start_date]

        if len(dates_plot) < 2:
            return await interaction.followup.send(f"Aucune partie enregistrée pour la période '{period}'.")

        title = get_mmr_period_title(period, season_num, act_num)
        buf = build_mmr_history_chart(dates_plot, elos_plot, period=period, title=title)

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
            timestamp=datetime.now(timezone.utc)
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
        parts = await self._tracker_svc.get_partitions(interaction.user.id)
        for season, act in parts:
            label = f"Episode {season} • Act {act}"
            value = f"e{season}a{act}"
            choices.append(app_commands.Choice(name=label, value=value))
        return [c for c in choices if current.lower() in c.value.lower()][:25]

async def setup(bot: commands.Bot):
    await bot.add_cog(MMRTracker(bot, bot.mmr_tracker_service))
    logger.info("MMRTracker Cog chargé.")
