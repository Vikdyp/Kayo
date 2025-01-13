# cogs/accueil/stalker.py
import discord
from discord.ext import commands
import logging
import io
import matplotlib.pyplot as plt
from datetime import timedelta, date

# Importation des fonctions depuis accueil_services
from cogs.accueil.services import accueil_services

logger = logging.getLogger("accueil.stalker")

class StalkerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # ID du canal où envoyer (et mettre à jour) le message de statistiques
        self.channel_id = 1236437099310219336  # À adapter
        # Nom du thread pour les notifications de départ
        self.leave_thread_name = "Notifications départs"

    async def get_leave_thread(self, channel: discord.TextChannel) -> discord.Thread:
        """
        Récupère un thread existant pour les notifications de départ dans le channel,
        ou en crée un s'il n'existe pas.
        """
        # On parcourt les threads actifs du channel
        threads = channel.threads
        for thread in threads:
            if thread.name == self.leave_thread_name:
                return thread

        # Si aucun thread n'existe, on en crée un.
        # Note : certains salons nécessitent les permissions adéquates pour créer un thread.
        try:
            thread = await channel.create_thread(
                name=self.leave_thread_name,
                type=discord.ChannelType.public_thread,
                auto_archive_duration=60  # Auto-archivage au bout de 60 minutes d'inactivité
            )
            return thread
        except Exception as e:
            logger.error(f"Erreur lors de la création du thread pour les départs: {e}")
            # Si impossible de créer un thread, retourner le channel principal
            return channel

    async def generate_member_evolution_graph(self, guild: discord.Guild) -> discord.File:
        """
        Génère un graphique montrant l'évolution du nombre de membres sur 30 jours.
        Le graphique est renvoyé sous forme de discord.File à joindre à l'embed.
        """
        # Récupérer les données d'évolution
        data = await accueil_services.get_member_evolution(guild.id)
        if not data:
            logger.info("Pas de données d'évolution disponibles pour générer le graphique.")
            return None

        # Construction des listes pour les dates et la variation journalière
        dates = []
        net_changes = []
        for record in data:
            dates.append(record['date'])
            net_changes.append(record['join_count'] - record['leave_count'])
        
        # Calcul du cumul pour obtenir l'évolution du nombre total de membres
        cumulative = []
        current_total = guild.member_count
        # On prend la liste inversée pour retracer l'évolution précédente
        temp_net = list(reversed(net_changes))
        cumulative_rev = [current_total]
        for change in temp_net[:-1]:
            cumulative_rev.append(cumulative_rev[-1] - change)
        cumulative = list(reversed(cumulative_rev))
        
        # Génération du graphique
        plt.figure(figsize=(8, 4))
        plt.plot(dates, cumulative, marker='o', linestyle='-', color='green')
        plt.title("Évolution du nombre de membres sur 30 jours")
        plt.xlabel("Date")
        plt.ylabel("Nombre de membres")
        plt.xticks(rotation=45)
        plt.tight_layout()

        # Sauvegarde dans un buffer
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close()
        
        file = discord.File(fp=buf, filename="evolution_membres.png")
        return file

    async def update_stats_embed(self, guild: discord.Guild):
        """
        Construit et met à jour l'embed de statistiques dans le canal principal.
        On y ajoute notamment le graphique d'évolution du nombre de membres.
        """
        channel = self.bot.get_channel(self.channel_id)
        if channel is None:
            logger.error(f"Le canal avec l'ID {self.channel_id} n'a pas été trouvé.")
            return

        # Récupère les statistiques agrégées depuis la base
        stats = await accueil_services.get_aggregated_stats(guild.id)
        current_members = guild.member_count

        embed = discord.Embed(
            title="📊 Statistiques du serveur",
            color=discord.Color.green()
        )
        embed.add_field(name="Membres actuels", value=str(current_members), inline=False)
        embed.add_field(name="Total des adhésions", value=str(stats["total_join"]), inline=True)
        embed.add_field(name="Total des départs", value=str(stats["total_left"]), inline=True)
        embed.add_field(name="Adhésions (24h)", value=str(stats["join_24h"]), inline=True)
        embed.add_field(name="Départs (24h)", value=str(stats["leave_24h"]), inline=True)
        embed.add_field(name="Adhésions (7j)", value=str(stats["join_7d"]), inline=True)
        embed.add_field(name="Départs (7j)", value=str(stats["leave_7d"]), inline=True)
        embed.add_field(name="Adhésions (30j)", value=str(stats["join_30d"]), inline=True)
        embed.add_field(name="Départs (30j)", value=str(stats["leave_30d"]), inline=True)
        embed.add_field(name="Taux Join/Leave", value=str(stats["join_leave_ratio"]), inline=False)
        embed.set_footer(text="Dernières statistiques mises à jour.")

        # Génération du graphique
        graph_file = await self.generate_member_evolution_graph(guild)
        if graph_file:
            embed.set_image(url=f"attachment://{graph_file.filename}")
        
        # Recherche du message existant envoyé par le bot avec l'embed de stats
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
                    await bot_message.edit(embed=embed, attachments=[graph_file])
                else:
                    await bot_message.edit(embed=embed)
                logger.info("Embed de statistiques mis à jour via édition.")
            else:
                if graph_file:
                    await channel.send(embed=embed, file=graph_file)
                else:
                    await channel.send(embed=embed)
                logger.info("Embed de statistiques envoyé.")
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'embed de statistiques : {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Enregistre un événement 'join' et met à jour l'embed de statistiques."""
        try:
            await accueil_services.log_member_event_aggregated(member.guild.id, "join")
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement d'un join: {e}")
        await self.update_stats_embed(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Enregistre un événement 'leave', met à jour l'embed de statistiques et envoie le message dans un thread dédié."""
        try:
            await accueil_services.log_member_event_aggregated(member.guild.id, "leave")
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement d'un leave: {e}")

        channel = self.bot.get_channel(self.channel_id)
        if channel is None:
            logger.error(f"Le canal avec l'ID {self.channel_id} n'a pas été trouvé.")
            return

        # Récupération (ou création) du thread dédié aux notifications de départ
        thread = await self.get_leave_thread(channel)

        try:
            # Envoi du message de départ dans le thread
            await thread.send(f"{member.name} a quitté le serveur.")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du message dans le thread : {e}")

        # Mise à jour de l'embed des statistiques
        await self.update_stats_embed(member.guild)

async def setup(bot: commands.Bot):
    await bot.add_cog(StalkerCog(bot))
    logger.info("StalkerCog chargé.")
