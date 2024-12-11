import discord
from discord.ext import commands, tasks
import logging
from cogs.utilities.data_manager import DataManager

logger = logging.getLogger("discord.rank_channel_updater")

class RankChannelUpdater(commands.Cog):
    """Cog pour mettre à jour automatiquement les salons en fonction des rôles des rangs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        self.update_rank_channels_task.start()  # Démarre la tâche périodique
        logger.info("RankChannelUpdater initialisé et tâche périodique démarrée.")

    def cog_unload(self):
        """Arrête la tâche lorsque le cog est déchargé."""
        self.update_rank_channels_task.cancel()
        logger.info("RankChannelUpdater déchargé et tâche périodique arrêtée.")

    @tasks.loop(minutes=5)  # Exécute la tâche toutes les 5 minutes
    async def update_rank_channels_task(self):
        """Tâche périodique pour mettre à jour les noms des salons des rangs."""
        logger.info("Exécution de la tâche de mise à jour des salons des rangs.")
        config = await self.data.get_config()
        roles_config = config.get("roles", {})
        channels_config = config.get("channels", {})
        
        # Rangs spécifiques
        ranks = ["fer", "bronze", "argent", "or", "platine", "diamant", "ascendant", "immortel", "radiant"]

        guild = self.bot.guilds[0] if self.bot.guilds else None
        if not guild:
            logger.warning("Aucun serveur trouvé pour la mise à jour des salons.")
            return

        for rank in ranks:
            role_id = roles_config.get(rank)
            channel_id = channels_config.get(rank)

            # Vérifier si le rôle et le salon sont configurés
            if not role_id or not channel_id:
                logger.warning(f"Rang {rank.capitalize()} : rôle ou salon non configuré.")
                continue

            role = guild.get_role(role_id)
            channel = guild.get_channel(channel_id)

            # Vérifier si le rôle et le salon existent dans le serveur
            if not role:
                logger.warning(f"Rôle {rank.capitalize()} introuvable dans le serveur.")
                continue

            if not channel:
                logger.warning(f"Salon {rank.capitalize()} introuvable dans le serveur.")
                continue

            # Compter les membres avec le rôle qui ne sont pas hors ligne
            online_members = [member for member in role.members if member.status != discord.Status.offline]
            online_count = len(online_members)

            # Renommer le salon pour inclure le nombre de membres en ligne
            new_channel_name = f"{rank.capitalize()} - {online_count} en ligne"
            if channel.name != new_channel_name:
                try:
                    await channel.edit(name=new_channel_name)
                    logger.info(f"Nom du salon {channel.name} mis à jour : {new_channel_name}.")
                except Exception as e:
                    logger.error(f"Erreur lors de la mise à jour du salon {channel.name} : {e}")
            else:
                logger.debug(f"Nom du salon {channel.name} déjà à jour.")


    @update_rank_channels_task.before_loop
    async def before_update_rank_channels_task(self):
        """Attendre que le bot soit prêt avant de démarrer la tâche."""
        logger.info("Attente que le bot soit prêt pour démarrer la tâche périodique.")
        await self.bot.wait_until_ready()
        logger.info("Le bot est prêt. La tâche périodique démarre maintenant.")

    @commands.command(name="start_rank_update_task")
    @commands.has_permissions(administrator=True)
    async def start_rank_update_task(self, ctx: commands.Context):
        """Démarre la tâche périodique de mise à jour des salons."""
        if not self.update_rank_channels_task.is_running():
            self.update_rank_channels_task.start()
            await ctx.send("✅ Tâche périodique démarrée.")
            logger.info("Tâche périodique démarrée manuellement.")
        else:
            await ctx.send("⚠️ La tâche est déjà en cours d'exécution.")

    @commands.command(name="stop_rank_update_task")
    @commands.has_permissions(administrator=True)
    async def stop_rank_update_task(self, ctx: commands.Context):
        """Arrête la tâche périodique de mise à jour des salons."""
        if self.update_rank_channels_task.is_running():
            self.update_rank_channels_task.cancel()
            await ctx.send("✅ Tâche périodique arrêtée.")
            logger.info("Tâche périodique arrêtée manuellement.")
        else:
            await ctx.send("⚠️ La tâche n'est pas en cours d'exécution.")

    @commands.command(name="test_online_members")
    @commands.has_permissions(administrator=True)
    async def test_online_members(self, ctx: commands.Context):
        """Affiche les membres en ligne et leurs rôles."""
        logger.info("Commande test_online_members appelée.")
        guild = ctx.guild

        if not guild:
            await ctx.send("⚠️ Impossible de récupérer le serveur. Assurez-vous que la commande est exécutée dans un serveur.")
            logger.error("Commande exécutée hors d'un serveur.")
            return

        # Inclure tous les statuts sauf 'offline'
        online_members = [
            member for member in guild.members if member.status in (discord.Status.online, discord.Status.idle, discord.Status.dnd)
        ]

        if not online_members:
            await ctx.send("Aucun membre en ligne trouvé.")
            logger.info("Aucun membre en ligne.")
            return

        result = ["**Membres en ligne et leurs rôles :**"]
        for member in online_members:
            roles = ", ".join([role.name for role in member.roles if role.name != "@everyone"])
            status = str(member.status).capitalize()  # Ajout du statut pour diagnostic
            result.append(f"🔹 **{member.display_name}** ({status}) : {roles or 'Aucun rôle'}")

        # Envoie les résultats dans le chat
        messages = []
        chunk = ""
        for line in result:
            if len(chunk) + len(line) + 1 < 2000:  # Gérer la limite Discord
                chunk += f"{line}\n"
            else:
                messages.append(chunk)
                chunk = f"{line}\n"
        messages.append(chunk)

        for message in messages:
            await ctx.send(message)

        logger.info("Résultat de test_online_members envoyé.")

    @commands.command(name="debug_members")
    @commands.has_permissions(administrator=True)
    async def debug_members(self, ctx: commands.Context):
        """Affiche tous les membres du serveur avec leur statut."""
        guild = ctx.guild
        members = [f"{member.display_name}: {member.status}" for member in guild.members]
        await ctx.send("\n".join(members[:2000]))



async def setup(bot: commands.Bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(RankChannelUpdater(bot))
