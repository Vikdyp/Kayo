# cogs/accueil/stalker.py
"""
Cog de statistiques membres - UI Discord uniquement.
"""

import discord
from discord.ext import commands, tasks
import logging
import asyncio
from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Optional, Dict

from cogs.accueil.presenters import build_member_stats_embed, detect_period_from_embed
from cogs.accueil.renderers import build_member_evolution_chart
from cogs.accueil.services import AccueilService
from cogs.accueil.views import StatsView

logger = logging.getLogger(__name__)


class StalkerCog(commands.Cog):
    def __init__(self, bot: commands.Bot, accueil_service: AccueilService):
        self.bot = bot
        self._service = accueil_service
        # Multi-serveur : dictionnaire {guild_id: message}
        self.persistent_messages: Dict[int, discord.Message] = {}
        self._load_persistent_task: asyncio.Task | None = None

        # Tâche de mise à jour quotidienne
        self.daily_update.start()

        # On essaye de recharger la vue persistante au démarrage
        self._load_persistent_task = asyncio.create_task(self.load_persistent_messages())

    def cog_unload(self):
        self.daily_update.cancel()
        if self._load_persistent_task:
            self._load_persistent_task.cancel()

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
                        current_period = detect_period_from_embed(msg)
                        await msg.edit(view=StatsView(self, guild, current_period))
                        logger.info(f"Vue réattachée sur le message persistant pour guild {guild.id}.")
                    except discord.NotFound:
                        logger.warning(f"Message persistant introuvable pour guild {guild.id}, sera recréé.")
                    except Exception as e:
                        logger.error(f"Erreur lors du chargement du message persistant: {e}")

    async def generate_member_evolution_graph(
        self,
        guild: discord.Guild,
        period: str = "default",
    ) -> Optional[discord.File]:
        """Génère un graphique de l'évolution des membres sur la période donnée."""
        # Récupérer les données via le service
        evolution_data = await self._service.get_evolution_data(guild.id, period)

        if not evolution_data:
            logger.info("Aucune donnée d'évolution trouvée pour la période demandée.")
            return None

        chart_buffer = build_member_evolution_chart(
            evolution_data,
            current_member_count=guild.member_count or 0,
        )
        return discord.File(fp=chart_buffer, filename="evolution_membres.png")

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
            guild.id, period, guild.member_count or 0
        )

        # Graphique
        graph_file = await self.generate_member_evolution_graph(guild, period=period)
        embed = build_member_stats_embed(
            stats_data=stats_data,
            timestamp=datetime.now(ZoneInfo("Europe/Paris")),
            image_url=f"attachment://{graph_file.filename}" if graph_file else None,
        )

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
    @commands.has_permissions(administrator=True)
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

    @embed_statistique.error
    async def embed_statistique_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(
                "Vous devez etre administrateur pour initialiser l'embed de statistiques.",
                delete_after=10,
            )
            return
        raise error

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
    accueil_service = getattr(bot, "accueil_service", None)
    if accueil_service is None:
        logger.error("accueil_service non initialisé. StalkerCog ne sera pas chargé.")
        return

    await bot.add_cog(StalkerCog(bot, accueil_service))
    logger.info("StalkerCog chargé.")
