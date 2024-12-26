# cogs/ranking/assign_rank_role.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
from cogs.ranking.services.rank_role_service import RankRoleService, VALID_RANKS
from utils.request_manager import enqueue_request
import os
import logging
from typing import Optional, List

logger = logging.getLogger("rank_roles")

class AssignRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        riot_api_key = os.getenv("RIOT_API_KEY")  # Utilisation de la clé Riot
        if not riot_api_key:
            logger.error("La clé API Riot n'est pas définie dans les variables d'environnement.")
            raise ValueError("Clé API Riot manquante.")
        self.service = RankRoleService(riot_api_key=riot_api_key)
        logger.debug("AssignRoles Cog initialisé.")

        # Démarrer la tâche de fond pour mettre à jour les rôles
        self.update_roles_task.start()

    def cog_unload(self):
        self.update_roles_task.cancel()

    @tasks.loop(hours=1)  # Ajustez la fréquence selon vos besoins
    async def update_roles_task(self):
        logger.debug("Tâche de mise à jour des rôles démarrée.")
        # Récupérer tous les utilisateurs liés au jeu Valorant
        query = """
            SELECT discord_id, valorant_pseudo, valorant_tag, valorant_region
            FROM user_id
            WHERE valorant_pseudo IS NOT NULL AND valorant_tag IS NOT NULL AND valorant_region IS NOT NULL;
        """
        users = await self.service.database.fetch(query)

        for user in users:
            discord_id = user['discord_id']
            pseudo = f"{user['valorant_pseudo']}#{user['valorant_tag']}"
            region = user['valorant_region']

            guilds = self.bot.guilds  # Obtenir toutes les guildes auxquelles le bot est connecté
            for guild in guilds:
                member = guild.get_member(discord_id)
                if not member:
                    logger.debug(f"Utilisateur Discord ID {discord_id} non trouvé dans la guilde {guild.id}.")
                    continue

                # Obtenir le PUUID
                puuid = await self.service.fetch_puuid(user['valorant_pseudo'], user['valorant_tag'], region)
                if not puuid:
                    logger.warning(f"Impossible de récupérer le PUUID pour {pseudo}.")
                    continue

                # Obtenir le rang
                rank = await self.service.fetch_valorant_rank(puuid, region)
                if not rank:
                    logger.warning(f"Impossible de récupérer le rang pour {pseudo}.")
                    continue

                if rank not in VALID_RANKS:
                    logger.warning(f"Rang non valide '{rank}' pour {pseudo}.")
                    continue

                # Attribuer le rôle
                await self.service.assign_rank_role(member, "valorant", rank)

    @update_roles_task.before_loop
    async def before_update_roles_task(self):
        await self.bot.wait_until_ready()
        logger.debug("Tâche de mise à jour des rôles prête à démarrer.")

    @app_commands.command(name="link_rank", description="Lier un jeu et un pseudo à votre compte Discord.")
    @app_commands.describe(
        game="Le jeu pour lequel vous voulez lier votre compte.",
        username="Votre nom d'utilisateur dans le jeu sélectionné (ex: Nom).",
        tag="Votre tag dans le jeu sélectionné (ex: Tag).",
        region="Votre région dans le jeu (ex: NA, EU, KR)."
    )
    @app_commands.choices(
        game=[
            app_commands.Choice(name="Valorant", value="valorant"),
            app_commands.Choice(name="Rocket League", value="rocket_league"),
            app_commands.Choice(name="Apex Legends", value="apex")
        ]
    )
    @app_commands.choices(
        region=[
            app_commands.Choice(name="North America (NA)", value="na"),
            app_commands.Choice(name="Europe (EU)", value="eu"),
            app_commands.Choice(name="Korea (KR)", value="kr"),
            app_commands.Choice(name="Latin America (LATAM)", value="latam"),
            app_commands.Choice(name="Brazil (BR)", value="br"),
            app_commands.Choice(name="Asia Pacific (AP)", value="ap")
        ]
    )
    @enqueue_request()
    async def link_rank(self, interaction: discord.Interaction, game: app_commands.Choice[str], username: str, tag: str, region: app_commands.Choice[str]) -> None:
        """
        Commande pour lier un pseudo d'un jeu à un compte Discord.
        """
        logger.debug(f"Début de link_rank: user={interaction.user}, game={game.value}, username={username}, tag={tag}, region={region.value}")
        try:
            user = interaction.user
            game_name = game.value.lower()
            region_name = region.value.lower()
            pseudo = f"{username}#{tag}"

            # Validation spécifique au jeu
            if game_name == "valorant":
                if not self.service.is_valid_valorant_username(username):
                    logger.debug("Validation du pseudo Valorant échouée")
                    await interaction.followup.send(
                        f"Le nom d'utilisateur Valorant `{username}` est invalide. Assurez-vous qu'il respecte le format : "
                        f"`Nom` avec un maximum de 16 caractères.",
                        ephemeral=True
                    )
                    return

            # Vérifier si le jeu est supporté pour le lier
            if game_name not in ["valorant", "rocket_league", "apex"]:
                await interaction.followup.send(
                    "Jeu non supporté pour cette commande.",
                    ephemeral=True
                )
                return

            # Optionnel: Vérifier si la région est valide pour le jeu
            if game_name == "valorant" and region_name not in ["na", "eu", "kr", "latam", "br", "ap"]:
                await interaction.followup.send(
                    "Région non supportée pour Valorant. Veuillez choisir parmi NA, EU, KR, LATAM, BR, AP.",
                    ephemeral=True
                )
                return

            # Stocker le pseudo et la région dans la base de données
            await self.service.link_user_game(user.id, game_name, pseudo, region_name)

            await interaction.followup.send(
                f"Votre pseudo `{pseudo}` a été lié à votre compte Discord pour le jeu **{game.name}** en région **{region.name}**.",
                ephemeral=True
            )
            logger.info(f"Pseudo {pseudo} et région {region_name} lié à {user.display_name} pour le jeu {game_name}.")
        except Exception as e:
            logger.exception(f"Erreur dans link_rank: {e}")
            await interaction.followup.send(
                "Une erreur inattendue s'est produite. Veuillez réessayer.",
                ephemeral=True
            )

    @app_commands.command(name="assign_rank", description="Attribuer un rôle basé sur le rang d'un jeu.")
    @app_commands.describe(
        game="Le jeu pour lequel vous voulez récupérer votre rôle en fonction du rang."
    )
    @app_commands.choices(
        game=[
            app_commands.Choice(name="Valorant", value="valorant"),
            app_commands.Choice(name="Rocket League", value="rocket_league"),
            app_commands.Choice(name="Apex Legends", value="apex")
        ]
    )
    @enqueue_request()
    async def assign_rank(self, interaction: discord.Interaction, game: app_commands.Choice[str]) -> None:
        """
        Commande pour attribuer un rôle basé sur un rang en fonction du pseudo lié.
        """
        logger.debug(f"Début de assign_rank: user={interaction.user}, game={game.value}")
        try:
            user = interaction.user
            game_name = game.value.lower()

            # Vérifier si le jeu est supporté pour l'attribution de rôles
            if game_name != "valorant":
                await interaction.followup.send(
                    f"L'attribution automatique des rôles pour **{game.name}** n'est pas encore implémentée.",
                    ephemeral=True
                )
                return

            # Récupérer le pseudo et la région liés
            linked_data = await self.service.get_user_game_data(user.id, game_name)

            if not linked_data or not linked_data["pseudo"] or not linked_data["tag"] or not linked_data["region"]:
                await interaction.followup.send(
                    f"Aucun pseudo n'est lié à votre compte Discord pour le jeu **{game.name}**. "
                    f"Veuillez utiliser `/link_rank` pour lier votre pseudo et région.",
                    ephemeral=True
                )
                return

            pseudo = f"{linked_data['pseudo']}#{linked_data['tag']}"
            region_name = linked_data["region"]

            # Extraire le nom d'utilisateur et le tag depuis le pseudo stocké
            try:
                game_username, tag_line = pseudo.split("#")
            except ValueError:
                logger.error(f"Format du pseudo lié invalide pour l'utilisateur {user.id}: {pseudo}")
                await interaction.followup.send(
                    "Le format de votre pseudo lié est invalide. Veuillez réutiliser `/link_rank` pour le lier correctement.",
                    ephemeral=True
                )
                return

            # Obtenir le PUUID via l'API Riot
            puuid = await self.service.fetch_puuid(game_username, tag_line, region_name)
            if not puuid:
                await interaction.followup.send(
                    f"Impossible de récupérer le PUUID pour le pseudo `{pseudo}`.",
                    ephemeral=True
                )
                return

            # Obtenir le rang via le PUUID et la région
            rank = await self.service.fetch_valorant_rank(puuid, region_name)
            if not rank:
                await interaction.followup.send(
                    f"Impossible de récupérer le rang pour le pseudo `{pseudo}` dans le jeu **{game.name}**.",
                    ephemeral=True
                )
                return

            if rank not in VALID_RANKS:
                await interaction.followup.send(
                    f"Le rang `{rank}` n'est pas reconnu. Contactez un administrateur.",
                    ephemeral=True
                )
                logger.warning(f"Rang non valide récupéré pour {pseudo}: {rank}")
                return

            member: Optional[discord.Member] = interaction.guild.get_member(user.id)
            if not member:
                await interaction.followup.send(
                    "Impossible de trouver votre membre dans le serveur.",
                    ephemeral=True
                )
                logger.error(f"Membre introuvable pour l'utilisateur Discord ID: {user.id}")
                return

            await self.service.assign_rank_role(member, game_name, rank)
            await interaction.followup.send(
                f"Rôle mis à jour pour {user.mention} dans le jeu **{game.name}**. Rang : **{rank.capitalize()}**.",
                ephemeral=True
            )
            logger.info(f"Rôle attribué pour {user.display_name} : {rank} ({game_name}).")
        except Exception as e:
            logger.exception(f"Erreur dans assign_rank: {e}")
            await interaction.followup.send(
                "Une erreur inattendue s'est produite. Veuillez réessayer.",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(AssignRoles(bot))
    logger.info("AssignRoles Cog chargé avec succès.")
