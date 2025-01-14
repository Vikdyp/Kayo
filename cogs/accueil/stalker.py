# cogs/accueil/stalker.py
import discord
from discord.ext import commands, tasks
import logging
import io
from matplotlib import ticker
import matplotlib.pyplot as plt
from datetime import timedelta, date, datetime, time
from zoneinfo import ZoneInfo
import asyncio

# Importation des fonctions depuis accueil_services
from cogs.accueil.services import accueil_services

logger = logging.getLogger("accueil.stalker")

# ----- VUE POUR LES BOUTONS -----
class StatsView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, period: str = "default"):
        super().__init__(timeout=None)  # Vue persistante
        self.cog = cog
        self.guild = guild
        self.period = period  # "default" signifie période par défaut (30 jours)

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
        # ID du salon où l'embed sera envoyé (à adapter)
        self.channel_id = 1236437099310219336
        # Nom du thread pour les notifications de départ (utilisé pour notifier les départs)
        self.leave_thread_name = "Notifications départs"
        # Stockage en mémoire du message persistant
        self.persistent_message = None
        # Tâche de mise à jour quotidienne
        self.daily_update.start()
        # Récupération/réattachement du message persistant au démarrage
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
        Génère un graphique de l'évolution des membres sur une période donnée.
        period: "7j", "1m", "1a", "total", ou "default" (30 jours)
        """
        if period == "7j":
            days = 7
        elif period == "1m":
            days = 30
        elif period == "1a":
            days = 365
        elif period == "total":
            days = 365  # Adapter pour le total si nécessaire
        else:
            days = 30

        data = await accueil_services.get_member_evolution(guild.id, days=days)
        if not data:
            logger.info("Aucune donnée d'évolution trouvée.")
            return None

        dates = []
        net_changes = []
        for record in data:
            dates.append(record['date'].strftime('%d-%m'))
            net_changes.append(record['join_count'] - record['leave_count'])

        cumulative = []
        current_total = guild.member_count
        temp_net = list(reversed(net_changes))
        cumulative_rev = [current_total]
        for change in temp_net[:-1]:
            cumulative_rev.append(cumulative_rev[-1] - change)
        cumulative = list(reversed(cumulative_rev))

        plt.figure(figsize=(8, 4))
        plt.plot(range(len(dates)), cumulative, marker='o', linestyle='-', color='green')
        plt.title(f"Évolution du nombre de membres sur {days} jours")
        plt.xlabel("Date")
        plt.ylabel("Nombre de membres")
        ax = plt.gca()
        ax.xaxis.set_major_locator(ticker.FixedLocator(range(len(dates))))
        ax.set_xticklabels(dates, rotation=45)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close()
        return discord.File(fp=buf, filename="evolution_membres.png")

    async def update_stats_embed(self, guild: discord.Guild, period: str = "default"):
        """
        Construit et met à jour l'embed de statistiques dans le salon configuré.
        Le paramètre 'period' détermine la période pour le graphique.
        """
        await accueil_services.ensure_today_member_stats(guild.id)
        channel = self.bot.get_channel(self.channel_id)
        if channel is None:
            logger.error(f"Canal introuvable avec l'ID {self.channel_id}.")
            return

        stats = await accueil_services.get_aggregated_stats(guild.id)
        current_members = guild.member_count

        embed = discord.Embed(
            title="📊 Statistiques du serveur",
            color=discord.Color.green()
        )

        # Informations générales
        embed.add_field(name="Membres actuels", value=str(current_members), inline=False)
        embed.add_field(name="Total adhésions", value=str(stats["total_join"]), inline=True)
        embed.add_field(name="Total départs", value=str(stats["total_left"]), inline=True)
        embed.add_field(name="Taux Join/Leave", value=str(stats["join_leave_ratio"]), inline=False)
        
        # Statistiques par périodes
        embed.add_field(name="Adhésions ✔ (24h)", value=str(stats["join_24h"]), inline=True)
        embed.add_field(name="Adhésions ✔ (7j)", value=str(stats["join_7d"]), inline=True)
        embed.add_field(name="Adhésions ✔ (30j)", value=str(stats["join_30d"]), inline=True)
        embed.add_field(name="Départs ✖ (24h)", value=str(stats["leave_24h"]), inline=True)
        embed.add_field(name="Départs ✖ (7j)", value=str(stats["leave_7d"]), inline=True)
        embed.add_field(name="Départs ✖ (30j)", value=str(stats["leave_30d"]), inline=True)
        embed.set_footer(text="Dernières statistiques mises à jour.")

        graph_file = await self.generate_member_evolution_graph(guild, period=period)
        if graph_file:
            embed.set_image(url=f"attachment://{graph_file.filename}")

        try:
            messages = [msg async for msg in channel.history(limit=10)]
            bot_message = None
            for msg in messages:
                if msg.author == self.bot.user and msg.embeds:
                    if msg.embeds[0].title == "📊 Statistiques du serveur":
                        bot_message = msg
                        break

            if bot_message:
                if graph_file:
                    await bot_message.edit(embed=embed, attachments=[graph_file], view=StatsView(self, guild, period))
                else:
                    await bot_message.edit(embed=embed, view=StatsView(self, guild, period))
                self.persistent_message = bot_message
                logger.info("Embed de statistiques mis à jour via édition.")
            else:
                if graph_file:
                    msg = await channel.send(embed=embed, file=graph_file, view=StatsView(self, guild, period))
                else:
                    msg = await channel.send(embed=embed, view=StatsView(self, guild, period))
                self.persistent_message = msg
                await accueil_services.save_persistent_message(guild.id, "stats_embed", channel.id, msg.id, requester_id=None)
                logger.info("Embed de statistiques envoyé et sauvegardé.")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'embed : {e}")

    @tasks.loop()
    async def daily_update(self):
        """
        Mise à jour quotidienne de l'embed à 00h00 (heure de Paris).
        """
        while True:
            try:
                paris_tz = ZoneInfo("Europe/Paris")
                now = datetime.now(paris_tz)
                logger.debug(f"Heure actuelle à Paris: {now}")

                next_midnight = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=paris_tz)
                delta_seconds = (next_midnight - now).total_seconds()
                logger.debug(f"Délai jusqu'au prochain minuit: {delta_seconds} secondes")
                await asyncio.sleep(delta_seconds)
                for guild in self.bot.guilds:
                    await self.update_stats_embed(guild)
                logger.info("Mise à jour quotidienne de l'embed effectuée.")
            except Exception as e:
                logger.error(f"Erreur dans la tâche quotidienne: {e}")
                await asyncio.sleep(60)

    @daily_update.before_loop
    async def before_daily_update(self):
        await self.bot.wait_until_ready()

    @commands.command(name="embed_statistique")
    async def embed_statistique(self, ctx: commands.Context):
        """
        Commande pour envoyer initialement l'embed de statistiques dans le salon configuré.
        L'embed est ensuite sauvegardé dans la base pour réattachement persistant.
        """
        try:
            await self.update_stats_embed(ctx.guild)
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
        # Enregistrer l'adhésion dans la BDD
        await accueil_services.log_member_event_aggregated(member.guild.id, "join")
        logger.info(f"{member.name} a rejoint le serveur.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Enregistrer le départ dans la BDD
        await accueil_services.log_member_event_aggregated(member.guild.id, "leave")
        logger.info(f"{member.name} a quitté le serveur.")

        # Notification de départ dans le thread (ID codé en dur)
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
