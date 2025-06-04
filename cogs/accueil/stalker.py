# cogs/accueil/stalker.py
import discord
from discord.ext import commands, tasks
import logging
import io
from matplotlib import ticker
import matplotlib.pyplot as plt
from datetime import datetime, time
from zoneinfo import ZoneInfo

from cogs.accueil.services import accueil_services

logger = logging.getLogger("accueil.stalker")


# ----- VUE POUR LES BOUTONS -----
class StatsView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, period: str = "default"):
        super().__init__(timeout=None)  # Vue persistante
        self.cog = cog
        self.guild = guild
        self.period = period  # "default" = 30 jours par défaut

    @discord.ui.button(label="🔄 Mettre à jour", style=discord.ButtonStyle.primary, custom_id="stats_update")
    async def update_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.update_stats_embed(self.guild, period=self.period)
        await interaction.followup.send("Embed mis à jour.", ephemeral=True)

    @discord.ui.button(label="7 jours", style=discord.ButtonStyle.secondary, custom_id="stats_7j")
    async def seven_days(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.period = "7j"
        await interaction.response.defer()
        await self.cog.update_stats_embed(self.guild, period="7j")
        await interaction.followup.send("Affichage des stats sur 7 jours.", ephemeral=True)

    @discord.ui.button(label="1 mois", style=discord.ButtonStyle.secondary, custom_id="stats_1m")
    async def one_month(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.period = "1m"
        await interaction.response.defer()
        await self.cog.update_stats_embed(self.guild, period="1m")
        await interaction.followup.send("Affichage des stats sur 1 mois.", ephemeral=True)

    @discord.ui.button(label="1 an", style=discord.ButtonStyle.secondary, custom_id="stats_1a")
    async def one_year(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.period = "1a"
        await interaction.response.defer()
        await self.cog.update_stats_embed(self.guild, period="1a")
        await interaction.followup.send("Affichage des stats sur 1 an.", ephemeral=True)

    @discord.ui.button(label="Total", style=discord.ButtonStyle.secondary, custom_id="stats_total")
    async def total_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.period = "total"
        await interaction.response.defer()
        await self.cog.update_stats_embed(self.guild, period="total")
        await interaction.followup.send("Affichage des stats totales.", ephemeral=True)
# ----- FIN VUE -----


class StalkerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.channel_id = 1236437099310219336
        self.persistent_message = None

        # Tâche de mise à jour quotidienne
        self.daily_update.start()

        # On essaye de recharger la vue persistante au démarrage
        self.bot.loop.create_task(self.load_persistent_message())

    def cog_unload(self):
        self.daily_update.cancel()

    async def load_persistent_message(self):
        """Récupère le message persistant depuis la base et réattache la vue."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            result = await accueil_services.get_persistent_message(guild.id, "stats_embed")
            if result:
                channel_id, message_id = result  # tuple (channel_id, message_id)
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        msg = await channel.fetch_message(message_id)
                        self.persistent_message = msg
                        await msg.edit(view=StatsView(self, guild))
                        logger.info(f"Vue réattachée sur le message persistant pour guild {guild.id}.")
                    except Exception as e:
                        logger.error(f"Erreur lors du chargement du message persistant: {e}")

    async def generate_member_evolution_graph(self, guild: discord.Guild, period: str = "default") -> discord.File:
        """
        Génère un graphique de l'évolution des membres sur la période donnée.
        Corrige le tri des données et applique plt.tight_layout() pour éviter tout
        problème d'affichage dans l'embed.
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
        if not data:
            logger.info("Aucune donnée d'évolution trouvée pour la période demandée.")
            return None

        # --- Correction : trier les données par date ASC avant de construire net_changes ---
        data.sort(key=lambda x: x['date'])

        dates = []
        net_changes = []
        # On construit les listes de base
        for record in data:
            dates.append(record['date'].strftime('%d-%m'))
            net_changes.append(record['join_count'] - record['leave_count'])

        # Calcul cumulatif en partant du count actuel (logique "reverse" inchangée)
        current_total = guild.member_count
        temp_net = list(reversed(net_changes))    # net_changes en sens inverse
        temp_dates = list(reversed(dates))        # idem pour les dates

        cumulative_rev = [current_total]
        for change in temp_net[:-1]:
            cumulative_rev.append(cumulative_rev[-1] - change)

        cumulative = list(reversed(cumulative_rev))
        dates = list(reversed(temp_dates))

        plt.figure(figsize=(8, 4))
        plt.plot(range(len(dates)), cumulative, marker='o', linestyle='-', color='green')
        plt.title("Évolution du nombre de membres")
        plt.xlabel("Date")
        plt.ylabel("Nombre de membres")
        ax = plt.gca()
        ax.xaxis.set_major_locator(ticker.FixedLocator(range(len(dates))))
        ax.set_xticklabels(dates, rotation=45)

        # Pour éviter que les labels soient tronqués
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close()
        return discord.File(fp=buf, filename="evolution_membres.png")

    async def update_stats_embed(self, guild: discord.Guild, period: str = "default"):
        """
        Construit et met à jour l'embed de statistiques dans le salon configuré,
        selon la période demandée.
        """
        await accueil_services.ensure_today_member_stats(guild.id)
        channel = self.bot.get_channel(self.channel_id)
        if channel is None:
            logger.error(f"Canal introuvable avec l'ID {self.channel_id}.")
            return

        # Récupère les stats selon la période cliquée
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
            title="📊 Statistiques du serveur",
            description=f"Période : {period_label}",
            color=discord.Color.green()
        )

        # Infos principales
        embed.add_field(name="Membres actuels", value=str(current_members), inline=False)
        embed.add_field(name="Adhésions ✔", value=str(stats_period["join_count"]), inline=True)
        embed.add_field(name="Départs ✖", value=str(stats_period["leave_count"]), inline=True)
        embed.add_field(
            name="Taux Join/Leave",
            value=str(stats_period["join_leave_ratio"]),
            inline=False
        )
        embed.set_footer(text="Statistiques mises à jour.")

        # Graphique
        graph_file = await self.generate_member_evolution_graph(guild, period=period)

        # On assigne l'image dans l'embed seulement si on a un fichier
        if graph_file:
            embed.set_image(url=f"attachment://{graph_file.filename}")

        try:
            # On recherche si le bot a déjà posté un embed "Statistiques du serveur"
            messages = [msg async for msg in channel.history(limit=10)]
            bot_message = None
            for msg in messages:
                if msg.author == self.bot.user and msg.embeds:
                    if msg.embeds[0].title == "📊 Statistiques du serveur":
                        bot_message = msg
                        break

            # S'il existe déjà un message -> on l'édite
            if bot_message:
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
                self.persistent_message = bot_message
                logger.info("Embed de statistiques mis à jour via édition.")
            else:
                # Sinon, on envoie un nouveau message
                if graph_file:
                    msg = await channel.send(embed=embed, file=graph_file, view=StatsView(self, guild, period))
                else:
                    msg = await channel.send(embed=embed, view=StatsView(self, guild, period))
                self.persistent_message = msg
                # On sauvegarde le message persistant en BDD
                await accueil_services.save_persistent_message(
                    guild.id, "stats_embed", channel.id, msg.id, requester_id=None
                )
                logger.info("Embed de statistiques envoyé et sauvegardé.")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'embed : {e}")

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
        dans le salon configuré.
        """
        try:
            await self.update_stats_embed(ctx.guild, period="default")
            channel = self.bot.get_channel(self.channel_id)
            if channel is None:
                raise Exception(f"Canal introuvable avec l'ID {self.channel_id}")

            messages = [msg async for msg in channel.history(limit=10)]
            bot_message = None
            for msg in messages:
                if msg.author == self.bot.user and msg.embeds:
                    if msg.embeds[0].title == "📊 Statistiques du serveur":
                        bot_message = msg
                        break

            if bot_message is None:
                raise Exception("Aucun message d'embed de statistiques n'a été trouvé.")

            await accueil_services.save_persistent_message(
                ctx.guild.id,
                "stats_embed",
                channel.id,
                bot_message.id,
                requester_id=ctx.author.id
            )
            await ctx.send("Embed de statistiques envoyé et sauvegardé.", delete_after=10)
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de l'embed: {e}")
            await ctx.send("Une erreur est survenue lors de l'initialisation.", delete_after=10)

    # ----- Listeners pour les événements de membres -----
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await accueil_services.log_member_event_aggregated(member.guild.id, "join")
        logger.info(f"{member.name} a rejoint le serveur.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await accueil_services.log_member_event_aggregated(member.guild.id, "leave")
        logger.info(f"{member.name} a quitté le serveur.")

        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            logger.error(f"Canal introuvable avec l'ID {self.channel_id}")
            return
        thread = self.bot.get_channel(1328749667449831434)
        if thread is None:
            logger.error("Thread pour les notifications de départ introuvable.")
            return
        try:
            await thread.send(f"{member.name} a quitté le serveur.")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi dans le thread: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(StalkerCog(bot))
    logger.info("StalkerCog chargé.")
