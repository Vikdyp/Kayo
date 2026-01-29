# cogs/accueil/stalker.py
import discord
from discord.ext import commands, tasks
import logging
import io
from matplotlib import ticker
import matplotlib.pyplot as plt
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Dict

from cogs.accueil.services import accueil_services

logger = logging.getLogger(__name__)

STATS_EMBED_ACTIONS = ("stat_embed", "stats_embed")

# Mapping période -> custom_id des boutons
PERIOD_TO_CUSTOM_ID = {
    "7j": "stats_7j",
    "1m": "stats_1m",
    "default": "stats_1m",
    "1a": "stats_1a",
    "total": "stats_total"
}


# ----- VUE POUR LES BOUTONS -----
class StatsView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, current_period: str = "default"):
        super().__init__(timeout=None)  # Vue persistante
        self.cog = cog
        self.guild = guild
        self.current_period = current_period
        self._update_button_styles()

    def _update_button_styles(self):
        """Met à jour les styles des boutons pour montrer la période active."""
        active_custom_id = PERIOD_TO_CUSTOM_ID.get(self.current_period)
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == active_custom_id:
                    item.style = discord.ButtonStyle.success  # Vert = actif
                elif item.custom_id != "stats_update":
                    item.style = discord.ButtonStyle.secondary  # Gris = inactif

    @discord.ui.button(label="Mettre à jour", style=discord.ButtonStyle.primary, custom_id="stats_update")
    async def update_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.update_stats_embed(interaction.guild, period=self.current_period)
        await interaction.followup.send("Embed mis à jour.", ephemeral=True)

    @discord.ui.button(label="7 jours", style=discord.ButtonStyle.secondary, custom_id="stats_7j")
    async def seven_days(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.update_stats_embed(interaction.guild, period="7j")
        await interaction.followup.send("Affichage des stats sur 7 jours.", ephemeral=True)

    @discord.ui.button(label="1 mois", style=discord.ButtonStyle.secondary, custom_id="stats_1m")
    async def one_month(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.update_stats_embed(interaction.guild, period="1m")
        await interaction.followup.send("Affichage des stats sur 1 mois.", ephemeral=True)

    @discord.ui.button(label="1 an", style=discord.ButtonStyle.secondary, custom_id="stats_1a")
    async def one_year(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.update_stats_embed(interaction.guild, period="1a")
        await interaction.followup.send("Affichage des stats sur 1 an.", ephemeral=True)

    @discord.ui.button(label="Total", style=discord.ButtonStyle.secondary, custom_id="stats_total")
    async def total_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.update_stats_embed(interaction.guild, period="total")
        await interaction.followup.send("Affichage des stats totales.", ephemeral=True)
# ----- FIN VUE -----


def _fill_missing_days(data: list, days: Optional[int]) -> list:
    """
    Remplit les jours manquants entre la première et dernière date avec join_count=0, leave_count=0.
    Si days est spécifié, s'assure que la période couvre exactement ce nombre de jours.
    """
    if not data:
        return data

    # Convertir en dict pour accès rapide
    data_by_date = {record['date']: record for record in data}

    # Déterminer la plage de dates
    paris_tz = ZoneInfo("Europe/Paris")
    today = datetime.now(paris_tz).date()

    if days is not None:
        start_date = today - timedelta(days=days)
        end_date = today
    else:
        # Pour "total", on prend la première date des données jusqu'à aujourd'hui
        start_date = min(record['date'] for record in data)
        end_date = today

    # Remplir les jours manquants
    filled_data = []
    current_date = start_date
    while current_date <= end_date:
        if current_date in data_by_date:
            filled_data.append(data_by_date[current_date])
        else:
            filled_data.append({
                'date': current_date,
                'join_count': 0,
                'leave_count': 0
            })
        current_date += timedelta(days=1)

    return filled_data


class StalkerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Multi-serveur : dictionnaire {guild_id: message}
        self.persistent_messages: Dict[int, discord.Message] = {}

        # Tâche de mise à jour quotidienne
        self.daily_update.start()

        # On essaye de recharger la vue persistante au démarrage
        self.bot.loop.create_task(self.load_persistent_messages())

    def cog_unload(self):
        self.daily_update.cancel()

    async def get_stats_channel(self, guild: discord.Guild) -> Optional[discord.abc.GuildChannel]:
        actions = list(STATS_EMBED_ACTIONS)
        channels = await accueil_services.get_channel_ids(guild.id, actions)
        channel_id = None
        for action in actions:
            channel_id = channels.get(action)
            if channel_id:
                break
        if not channel_id:
            logger.warning("Aucun salon stats_embed configure pour la guilde %s.", guild.id)
            return None
        channel = guild.get_channel(channel_id) or self.bot.get_channel(channel_id)
        if not channel:
            logger.error("Salon stats_embed introuvable pour la guilde %s (id=%s).", guild.id, channel_id)
            return None
        return channel

    async def load_persistent_messages(self):
        """Récupère les messages persistants depuis la base et réattache les vues (multi-serveur)."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            result = await accueil_services.get_persistent_message(guild.id, "stats_embed")
            if result:
                channel_id, message_id = result
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        msg = await channel.fetch_message(message_id)
                        self.persistent_messages[guild.id] = msg
                        # Récupérer la période actuelle depuis l'embed
                        current_period = "default"
                        if msg.embeds and msg.embeds[0].description:
                            desc = msg.embeds[0].description
                            if "7 jours" in desc:
                                current_period = "7j"
                            elif "1 mois" in desc or "30 jours" in desc:
                                current_period = "1m"
                            elif "1 an" in desc:
                                current_period = "1a"
                            elif "Total" in desc:
                                current_period = "total"
                        await msg.edit(view=StatsView(self, guild, current_period))
                        logger.info(f"Vue réattachée sur le message persistant pour guild {guild.id}.")
                    except discord.NotFound:
                        logger.warning(f"Message persistant introuvable pour guild {guild.id}, sera recréé.")
                    except Exception as e:
                        logger.error(f"Erreur lors du chargement du message persistant: {e}")

    async def generate_member_evolution_graph(self, guild: discord.Guild, period: str = "default") -> Optional[discord.File]:
        """
        Génère un graphique de l'évolution des membres sur la période donnée.
        Interpole les jours manquants et utilise une logique de calcul simplifiée.
        """
        if period == "7j":
            days = 7
        elif period == "1m":
            days = 30
        elif period == "1a":
            days = 365
        elif period == "total":
            days = None
        else:
            days = 30  # par défaut, 30 jours

        data = await accueil_services.get_member_evolution(guild.id, days=days)

        # Interpoler les jours manquants
        data = _fill_missing_days(data, days)

        if not data:
            logger.info("Aucune donnée d'évolution trouvée pour la période demandée.")
            return None

        # Trier par date ASC
        data.sort(key=lambda x: x['date'])

        # Construire les changements nets par jour
        net_changes = [record['join_count'] - record['leave_count'] for record in data]
        dates = [record['date'].strftime('%d-%m') for record in data]

        # Calcul cumulatif simplifié :
        # On part du nombre actuel de membres et on remonte dans le temps
        current_total = guild.member_count

        # Calculer le cumul en partant de la fin (aujourd'hui = current_total)
        # cumulative[i] = nombre de membres au jour i
        cumulative = [0] * len(net_changes)
        cumulative[-1] = current_total

        # Remonter dans le temps : membres[jour_precedent] = membres[jour_suivant] - changement_du_jour_suivant
        for i in range(len(net_changes) - 2, -1, -1):
            cumulative[i] = cumulative[i + 1] - net_changes[i + 1]

        # Créer le graphique
        plt.figure(figsize=(10, 5))
        plt.plot(range(len(dates)), cumulative, marker='o', linestyle='-', color='#2ecc71', markersize=4)
        plt.fill_between(range(len(dates)), cumulative, alpha=0.3, color='#2ecc71')
        plt.title("Évolution du nombre de membres", fontsize=14, fontweight='bold')
        plt.xlabel("Date", fontsize=10)
        plt.ylabel("Nombre de membres", fontsize=10)

        ax = plt.gca()
        ax.set_facecolor('#f8f9fa')
        plt.gcf().set_facecolor('#ffffff')

        # Afficher moins de labels si trop de dates
        if len(dates) > 15:
            step = max(1, len(dates) // 10)
            tick_positions = list(range(0, len(dates), step))
            if len(dates) - 1 not in tick_positions:
                tick_positions.append(len(dates) - 1)
            ax.xaxis.set_major_locator(ticker.FixedLocator(tick_positions))
            ax.set_xticklabels([dates[i] for i in tick_positions], rotation=45, ha='right')
        else:
            ax.xaxis.set_major_locator(ticker.FixedLocator(range(len(dates))))
            ax.set_xticklabels(dates, rotation=45, ha='right')

        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=100)
        buf.seek(0)
        plt.close()
        return discord.File(fp=buf, filename="evolution_membres.png")

    async def update_stats_embed(self, guild: discord.Guild, period: str = "default", force_new: bool = False):
        """
        Construit et met à jour l'embed de statistiques dans le salon configuré.

        Args:
            guild: Le serveur Discord
            period: La période à afficher (7j, 1m, 1a, total, default)
            force_new: Si True, crée un nouveau message même s'il en existe un
        """
        await accueil_services.ensure_today_member_stats(guild.id)
        channel = await self.get_stats_channel(guild)
        if channel is None:
            return

        # Récupère les stats selon la période
        if period == "7j":
            days = 7
            period_label = "7 jours"
        elif period == "1m":
            days = 30
            period_label = "1 mois"
        elif period == "1a":
            days = 365
            period_label = "1 an"
        elif period == "total":
            days = None
            period_label = "Total"
        else:
            days = 30
            period_label = "30 jours"

        stats_period = await accueil_services.get_period_stats(guild.id, days)
        current_members = guild.member_count

        embed = discord.Embed(
            title="Statistiques du serveur",
            description=f"Période : {period_label}",
            color=discord.Color.green()
        )

        # Infos principales
        embed.add_field(name="Membres actuels", value=str(current_members), inline=False)
        embed.add_field(name="Adhésions", value=str(stats_period["join_count"]), inline=True)
        embed.add_field(name="Départs", value=str(stats_period["leave_count"]), inline=True)
        embed.add_field(
            name="Taux Join/Leave",
            value=str(stats_period["join_leave_ratio"]),
            inline=False
        )

        # Timestamp pour savoir quand les stats ont été mises à jour
        embed.set_footer(text="Dernière mise à jour")
        embed.timestamp = datetime.now(ZoneInfo("Europe/Paris"))

        # Graphique
        graph_file = await self.generate_member_evolution_graph(guild, period=period)

        if graph_file:
            embed.set_image(url=f"attachment://{graph_file.filename}")

        try:
            # Récupérer le message existant depuis la BDD (plus fiable que recherche par titre)
            bot_message = None
            if not force_new:
                persistent = await accueil_services.get_persistent_message(guild.id, "stats_embed")
                if persistent:
                    _, message_id = persistent
                    try:
                        bot_message = await channel.fetch_message(message_id)
                    except discord.NotFound:
                        bot_message = None  # Message supprimé, on en créera un nouveau

            # S'il existe déjà un message -> on l'édite
            if bot_message and not force_new:
                if graph_file:
                    await bot_message.edit(
                        embed=embed,
                        attachments=[graph_file],
                        view=StatsView(self, guild, period)
                    )
                else:
                    await bot_message.edit(
                        embed=embed,
                        view=StatsView(self, guild, period)
                    )
                self.persistent_messages[guild.id] = bot_message
                logger.info(f"Embed de statistiques mis à jour via édition pour guild {guild.id}.")
            else:
                # Archiver l'ancien thread s'il existe
                old_thread_data = await accueil_services.get_persistent_message(guild.id, "stats_thread")
                if old_thread_data:
                    old_thread_id = old_thread_data[1]
                    old_thread = self.bot.get_channel(old_thread_id)
                    if old_thread:
                        try:
                            await old_thread.edit(archived=True)
                            logger.info(f"Ancien thread archivé pour guild {guild.id}.")
                        except Exception as e:
                            logger.warning(f"Impossible d'archiver l'ancien thread: {e}")

                # Envoyer un nouveau message
                if graph_file:
                    msg = await channel.send(embed=embed, file=graph_file, view=StatsView(self, guild, period))
                else:
                    msg = await channel.send(embed=embed, view=StatsView(self, guild, period))

                self.persistent_messages[guild.id] = msg

                # Sauvegarder le message persistant en BDD
                await accueil_services.save_persistent_message(
                    guild.id, "stats_embed", channel.id, msg.id, requester_id=None
                )

                # Créer un nouveau thread attaché au message
                try:
                    thread = await msg.create_thread(name="Notifications départs")
                    await accueil_services.save_persistent_message(
                        guild.id, "stats_thread", channel.id, thread.id, requester_id=None
                    )
                    logger.info(f"Thread de notifications créé pour guild {guild.id}.")
                except Exception as e:
                    logger.error(f"Erreur lors de la création du thread: {e}")

                logger.info(f"Embed de statistiques envoyé et sauvegardé pour guild {guild.id}.")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'embed pour guild {guild.id}: {e}")

    @tasks.loop(time=time(hour=0, tzinfo=ZoneInfo("Europe/Paris")))
    async def daily_update(self):
        """Met à jour l'embed de statistiques chaque jour à minuit."""
        for guild in self.bot.guilds:
            try:
                await self.update_stats_embed(guild, period="default")
            except Exception as e:
                logger.error(f"Erreur lors de la mise à jour quotidienne pour {guild.id}: {e}")
        logger.info("Mise à jour quotidienne de l'embed effectuée.")

    @daily_update.before_loop
    async def before_daily_update(self):
        await self.bot.wait_until_ready()

    @commands.command(name="embed_statistique")
    async def embed_statistique(self, ctx: commands.Context):
        """
        Commande pour envoyer initialement l'embed de statistiques
        dans le salon configuré. Crée un nouveau message et thread.
        """
        try:
            channel = await self.get_stats_channel(ctx.guild)
            if channel is None:
                await ctx.send("Aucun salon stats_embed configure pour cette guilde.", delete_after=10)
                return

            # Force la création d'un nouveau message
            await self.update_stats_embed(ctx.guild, period="default", force_new=True)
            await ctx.send("Embed de statistiques envoyé et sauvegardé.", delete_after=10)
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de l'embed: {e}")
            await ctx.send("Une erreur est survenue lors de l'initialisation.", delete_after=10)

    # ----- Listeners pour les événements de membres -----
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await accueil_services.log_member_event_aggregated(member.guild.id, "join")
        logger.info(f"{member.name} a rejoint le serveur {member.guild.name}.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await accueil_services.log_member_event_aggregated(member.guild.id, "leave")
        logger.info(f"{member.name} a quitté le serveur {member.guild.name}.")

        # Récupérer le thread dynamiquement depuis la BDD
        thread_data = await accueil_services.get_persistent_message(member.guild.id, "stats_thread")
        if not thread_data:
            logger.debug(f"Pas de thread de notifications configuré pour guild {member.guild.id}.")
            return

        thread_id = thread_data[1]
        thread = self.bot.get_channel(thread_id)
        if thread is None:
            logger.warning(f"Thread de notifications introuvable (id={thread_id}) pour guild {member.guild.id}.")
            return

        try:
            await thread.send(f"**{member.name}** a quitté le serveur.")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi dans le thread: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(StalkerCog(bot))
    logger.info("StalkerCog chargé.")
