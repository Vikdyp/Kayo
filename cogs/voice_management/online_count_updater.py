import discord
from discord.ext import commands, tasks
import logging
from cogs.utilities.data_manager import DataManager

logger = logging.getLogger("discord.voice_management.online_count_updater")

class OnlineCountUpdater(commands.Cog):
    """Cog pour mettre à jour les noms des salons avec le nombre de membres en ligne par rôle."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = DataManager()
        logger.info("OnlineCountUpdater initialisé.")

    @tasks.loop(minutes=5)
    async def update_task(self):
        """Mise à jour des noms des salons toutes les 5 minutes."""
        logger.info("Exécution de la tâche périodique de mise à jour des salons.")
        config = await self.data.get_config()
        role_channel_mapping = {
            "fer": "rank_Fer",
            "bronze": "rank_Bronze",
            "argent": "rank_Argent",
            "or": "rank_Or",
            "platine": "rank_Platine",
            "diamant": "rank_Diamant",
            "ascendant": "rank_Ascendant",
            "immortel": "rank_Immortel",
        }

        guild = self.bot.guilds[0] if self.bot.guilds else None
        if not guild:
            logger.warning("Aucun serveur trouvé pour mettre à jour les salons.")
            return

        for role_name, channel_key in role_channel_mapping.items():
            # Récupérer l'ID du rôle et du salon depuis la configuration
            role_id = config.get("roles", {}).get(role_name)
            channel_id = config.get("channels", {}).get(channel_key)

            if not role_id or not channel_id:
                logger.warning(f"Rôle ou salon introuvable pour {role_name}. Ignoré.")
                continue

            # Récupérer le rôle et le salon
            role = guild.get_role(role_id)
            channel = guild.get_channel(channel_id)

            if not role:
                logger.warning(f"Rôle {role_name} avec ID {role_id} introuvable.")
                continue
            if not channel:
                logger.warning(f"Canal {channel_key} avec ID {channel_id} introuvable.")
                continue

            # Comptez les membres en ligne pour le rôle
            online_count = sum(1 for m in role.members if m.status != discord.Status.offline)
            logger.debug(f"Nombre de membres en ligne pour {role.name}: {online_count}")

            # Nouveau nom pour le salon
            new_name = f"{role.name.capitalize()} {online_count} online"

            # Mettre à jour le nom du canal si nécessaire
            if channel.name != new_name:
                try:
                    await channel.edit(name=new_name)
                    logger.info(f"Nom du canal {channel.name} mis à jour : {new_name}.")
                except Exception as e:
                    logger.exception(f"Erreur lors de la mise à jour du canal {channel.name} : {e}")

    @update_task.before_loop
    async def before_update_task(self):
        """Attendre que le bot soit prêt avant de démarrer la tâche."""
        logger.info("Attente que le bot soit prêt pour démarrer la tâche périodique.")
        await self.bot.wait_until_ready()
        logger.info("Le bot est prêt. La tâche périodique démarre maintenant.")

    @commands.command(name="test_online_count")
    @commands.has_permissions(administrator=True)
    async def test_online_count(self, ctx: commands.Context):
        """Commande de test pour compter le nombre de membres en ligne par rôle."""
        logger.info("Commande test_online_count appelée.")
        config = await self.data.get_config()
        role_mapping = {
            "fer": "rank_Fer",
            "bronze": "rank_Bronze",
            "argent": "rank_Argent",
            "or": "rank_Or",
            "platine": "rank_Platine",
            "diamant": "rank_Diamant",
            "ascendant": "rank_Ascendant",
            "immortel": "rank_Immortel",
        }

        guild = ctx.guild
        if not guild:
            await ctx.send("Impossible de récupérer le serveur. Assurez-vous que la commande est exécutée dans un serveur.")
            return

        result = []
        for role_name, channel_key in role_mapping.items():
            role_id = config.get("roles", {}).get(role_name)
            if not role_id:
                result.append(f"⚠️ Rôle {role_name} non configuré.")
                logger.warning(f"Rôle {role_name} non configuré.")
                continue

            role = guild.get_role(role_id)
            if not role:
                result.append(f"⚠️ Rôle {role_name} introuvable dans le serveur.")
                logger.warning(f"Rôle {role_name} introuvable dans le serveur.")
                continue

            # Log pour afficher tous les membres du rôle
            logger.debug(f"Membres avec le rôle {role.name}: {[m.display_name for m in role.members]}")
            
            # Comptez les membres en ligne
            online_count = sum(1 for m in role.members if m.status != discord.Status.offline)
            logger.debug(f"Statuts des membres pour {role.name}: {[m.status for m in role.members]}")

            result.append(f"🔹 **{role.name.capitalize()}** : {online_count} en ligne.")

        # Envoyer le résultat dans le chat
        await ctx.send("\n".join(result))
        logger.info("Résultat de test_online_count envoyé.")

async def setup(bot: commands.Bot):
    """Ajoute le cog au bot."""
    await bot.add_cog(OnlineCountUpdater(bot))
    
def setup_online_count_updater(bot: commands.Bot):
    """Initialise et démarre OnlineCountUpdater avec le bot."""
    cog = bot.get_cog("OnlineCountUpdater")
    if cog:
        cog.update_task.start()
        logger.info("Tâche OnlineCountUpdater démarrée.")
    else:
        logger.warning("OnlineCountUpdater non chargé. Impossible de démarrer la tâche.")