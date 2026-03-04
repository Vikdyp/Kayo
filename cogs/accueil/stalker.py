# cogs/accueil/stalker.py
"""
Cog de statistiques membres - UI Discord uniquement.
"""

import discord
from discord.ext import commands, tasks
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Optional, Dict

from cogs.accueil.services import AccueilService

logger = logging.getLogger(__name__)

# Mapping période → custom_id des boutons
PERIOD_TO_CUSTOM_ID = {
    "7j": "stats_7j",
    "1m": "stats_1m",
    "default": "stats_1m",
    "1a": "stats_1a",
    "total": "stats_total",
}


# ----- VUE POUR LES BOUTONS -----
class StatsView(discord.ui.View):
    def __init__(self, cog: "StalkerCog", guild: discord.Guild, current_period: str = "default"):
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


class StalkerCog(commands.Cog):
    def __init__(self, bot: commands.Bot, accueil_service: AccueilService):
        self.bot = bot
        self._service = accueil_service
        # Multi-serveur : dictionnaire {guild_id: message}
        self.persistent_messages: Dict[int, discord.Message] = {}

        # Tâche de mise à jour quotidienne
        self.daily_update.start()

        # On essaye de recharger la vue persistante au démarrage
        self.bot.loop.create_task(self.load_persistent_messages())

    def cog_unload(self):
        self.daily_update.cancel()

    async def get_stats_channel(self, guild: discord.Guild) -> Optional[discord.abc.GuildChannel]:
        """Récupère le channel de stats via le service."""
        channel_id = await self._service.get_stats_channel_id(guild.id)
        if not channel_id:
            logger.warning(f"Aucun salon stats_embed configuré pour la guilde {guild.id}.")
            return None
        channel = guild.get_channel(channel_id) or self.bot.get_channel(channel_id)
        if not channel:
            logger.error(f"Salon stats_embed introuvable pour la guilde {guild.id} (id={channel_id}).")
        return channel

    async def load_persistent_messages(self):
        """Récupère les messages persistants depuis la base et réattache les vues (multi-serveur)."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            msg_info = await self._service.get_stats_embed_message(guild.id)
            if msg_info:
                channel = self.bot.get_channel(msg_info.channel_id)
                if channel:
                    try:
                        msg = await channel.fetch_message(msg_info.message_id)
                        self.persistent_messages[guild.id] = msg
                        # Récupérer la période actuelle depuis l'embed
                        current_period = self._detect_period_from_embed(msg)
                        await msg.edit(view=StatsView(self, guild, current_period))
                        logger.info(f"Vue réattachée sur le message persistant pour guild {guild.id}.")
                    except discord.NotFound:
                        logger.warning(f"Message persistant introuvable pour guild {guild.id}, sera recréé.")
                    except Exception as e:
                        logger.error(f"Erreur lors du chargement du message persistant: {e}")

    def _detect_period_from_embed(self, msg: discord.Message) -> str:
        """Détecte la période depuis le contenu de l'embed."""
        if msg.embeds and msg.embeds[0].description:
            desc = msg.embeds[0].description
            if "7 jours" in desc:
                return "7j"
            elif "1 mois" in desc or "30 jours" in desc:
                return "1m"
            elif "1 an" in desc:
                return "1a"
            elif "Total" in desc:
                return "total"
        return "default"

    async def generate_member_evolution_graph(
        self,
        guild: discord.Guild,
        period: str = "default",
    ) -> Optional[discord.File]:
        """Génère un graphique via le service et le wrap en discord.File."""
        buf = await self._service.generate_member_evolution_graph(
            guild.id, period, guild.member_count
        )
        if buf is None:
            return None
        return discord.File(fp=buf, filename="evolution_membres.png")

    async def update_stats_embed(
        self,
        guild: discord.Guild,
        period: str = "default",
        force_new: bool = False,
    ):
        """
        Construit et met à jour l'embed de statistiques dans le salon configuré.

        Args:
            guild: Le serveur Discord
            period: La période à afficher (7j, 1m, 1a, total, default)
            force_new: Si True, crée un nouveau message même s'il en existe un
        """
        channel = await self.get_stats_channel(guild)
        if channel is None:
            return

        # Récupérer les données via le service
        stats_data = await self._service.get_stats_embed_data(
            guild.id, period, guild.member_count
        )

        embed = discord.Embed(
            title="Statistiques du serveur",
            description=f"Période : {stats_data.period_label}",
            color=discord.Color.green(),
        )

        # Infos principales
        embed.add_field(name="Membres actuels", value=str(stats_data.current_members), inline=False)
        embed.add_field(name="Adhésions", value=str(stats_data.join_count), inline=True)
        embed.add_field(name="Départs", value=str(stats_data.leave_count), inline=True)
        embed.add_field(name="Taux Join/Leave", value=stats_data.ratio, inline=False)

        # Timestamp pour savoir quand les stats ont été mises à jour
        embed.set_footer(text="Dernière mise à jour")
        embed.timestamp = datetime.now(ZoneInfo("Europe/Paris"))

        # Graphique
        graph_file = await self.generate_member_evolution_graph(guild, period=period)

        if graph_file:
            embed.set_image(url=f"attachment://{graph_file.filename}")

        try:
            # Récupérer le message existant depuis la BDD
            bot_message = None
            if not force_new:
                msg_info = await self._service.get_stats_embed_message(guild.id)
                if msg_info:
                    try:
                        bot_message = await channel.fetch_message(msg_info.message_id)
                    except discord.NotFound:
                        bot_message = None  # Message supprimé, on en créera un nouveau

            # S'il existe déjà un message → on l'édite
            if bot_message and not force_new:
                if graph_file:
                    await bot_message.edit(
                        embed=embed,
                        attachments=[graph_file],
                        view=StatsView(self, guild, period),
                    )
                else:
                    await bot_message.edit(
                        embed=embed,
                        view=StatsView(self, guild, period),
                    )
                self.persistent_messages[guild.id] = bot_message
                logger.info(f"Embed de statistiques mis à jour via édition pour guild {guild.id}.")
            else:
                # Archiver l'ancien thread s'il existe
                old_thread_info = await self._service.get_stats_thread(guild.id)
                if old_thread_info:
                    old_thread = self.bot.get_channel(old_thread_info.channel_id)
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
                await self._service.save_stats_embed_message(
                    guild.id, guild.name, channel.id, msg.id
                )

                # Créer un nouveau thread attaché au message
                try:
                    thread = await msg.create_thread(name="Notifications départs")
                    # Poster un message placeholder pour avoir un message_id valide
                    placeholder_msg = await thread.send("📊 Thread de notifications des départs.")
                    await self._service.save_stats_thread(
                        guild.id, guild.name, thread.id, placeholder_msg.id
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
                await ctx.send("Aucun salon stats_embed configuré pour cette guilde.", delete_after=10)
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
        await self._service.on_member_join(member.guild.id, member.guild.name)
        logger.info(f"{member.name} a rejoint le serveur {member.guild.name}.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self._service.on_member_leave(member.guild.id, member.guild.name)
        logger.info(f"{member.name} a quitté le serveur {member.guild.name}.")

        # Récupérer le thread dynamiquement depuis la BDD
        thread_info = await self._service.get_stats_thread(member.guild.id)
        if not thread_info:
            logger.debug(f"Pas de thread de notifications configuré pour guild {member.guild.id}.")
            return

        thread = self.bot.get_channel(thread_info.channel_id)
        if thread is None:
            logger.warning(
                f"Thread de notifications introuvable (id={thread_info.channel_id}) pour guild {member.guild.id}."
            )
            return

        try:
            await thread.send(f"**{member.name}** a quitté le serveur.")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi dans le thread: {e}")


async def setup(bot: commands.Bot):
    # Le service est injecté via bot.accueil_service (configuré dans main.py)
    accueil_service = bot.accueil_service
    await bot.add_cog(StalkerCog(bot, accueil_service))
    logger.info("StalkerCog chargé.")
