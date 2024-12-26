# cogs/ranking/services/rank_role_service.py
import aiohttp
import re
import logging
from typing import Optional, Dict

import discord
from utils.database import database  # Assurez-vous que ce chemin est correct

logger = logging.getLogger("services.rank_role_service")

# Liste des rangs valides basés sur l'API Riot
VALID_RANKS = [
    "iron 1", "iron 2", "iron 3",
    "bronze 1", "bronze 2", "bronze 3",
    "silver 1", "silver 2", "silver 3",
    "gold 1", "gold 2", "gold 3",
    "platinum 1", "platinum 2", "platinum 3",
    "diamond 1", "diamond 2", "diamond 3",
    "ascendant", "immortal", "radiant"
]

# Mapping des régions Riot vers les régions Valorant
REGION_MAPPING = {
    "na": "americas",
    "eu": "europe",
    "kr": "asia",
    "latam": "americas",
    "br": "americas",
    "ap": "asia"
}

# Mapping des rangs Valorant aux rôles Discord généraux
RANK_TO_ROLE = {
    "iron 1": "fer",
    "iron 2": "fer",
    "iron 3": "fer",
    "bronze 1": "bronze",
    "bronze 2": "bronze",
    "bronze 3": "bronze",
    "silver 1": "argent",
    "silver 2": "argent",
    "silver 3": "argent",
    "gold 1": "or",
    "gold 2": "or",
    "gold 3": "or",
    "platinum 1": "platine",
    "platinum 2": "platine",
    "platinum 3": "platine",
    "diamond 1": "diamant",
    "diamond 2": "diamant",
    "diamond 3": "diamant",
    "ascendant": "ascendant",
    "immortal": "immortel",
    "radiant": "radiant"
}

class RankRoleService:
    def __init__(self, riot_api_key: str):
        self.riot_api_key = riot_api_key
        self.database = database  # Attache l'instance globale de la base de données
        logger.debug("RankRoleService initialisé avec la base de données.")

    def is_valid_valorant_username(self, username: str) -> bool:
        """
        Vérifie si un pseudo Valorant est valide (1-16 caractères alphanumériques).
        """
        pattern = r'^[a-zA-Z0-9]{1,16}$'
        is_valid = re.match(pattern, username) is not None
        logger.debug(f"Validation du pseudo '{username}': {is_valid}")
        return is_valid

    async def fetch_puuid(self, game_name: str, tag_line: str, region: str) -> Optional[str]:
        """
        Récupère le PUUID d'un utilisateur Valorant via l'API Riot.
        """
        riot_region = REGION_MAPPING.get(region.lower())
        if not riot_region:
            logger.error(f"Région inconnue ou non supportée: {region}")
            return None

        url = f"https://{riot_region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        headers = {
            "X-Riot-Token": self.riot_api_key
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 403:
                        logger.error(f"Accès interdit avec la clé API pour {game_name}#{tag_line}.")
                        return None
                    elif response.status != 200:
                        logger.error(f"Erreur API Riot pour {game_name}#{tag_line} : {response.status}")
                        return None
                    data = await response.json()
                    puuid = data.get('puuid')
                    logger.debug(f"PUUID récupéré pour {game_name}#{tag_line}: {puuid}")
                    return puuid
        except aiohttp.ClientError as e:
            logger.error(f"Erreur réseau lors de la récupération du PUUID pour {game_name}#{tag_line}: {e}")
            return None

    async def fetch_valorant_rank(self, puuid: str, region: str) -> Optional[str]:
        """
        Récupère le rang compétitif d'un utilisateur Valorant via l'API Riot.
        """
        riot_region = REGION_MAPPING.get(region.lower())
        if not riot_region:
            logger.error(f"Région inconnue ou non supportée: {region}")
            return None

        url = f"https://{riot_region}.api.riotgames.com/val/ranked/v1/leaderboards/by-puuid/{puuid}/by-act"
        headers = {
            "X-Riot-Token": self.riot_api_key
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 403:
                        logger.error(f"Accès interdit avec la clé API pour PUUID {puuid}.")
                        return None
                    elif response.status != 200:
                        logger.error(f"Erreur API Riot pour PUUID {puuid} : {response.status}")
                        return None
                    data = await response.json()
                    # Extraire le rang compétitif
                    if not data:
                        logger.warning(f"Aucune donnée de rang trouvée pour PUUID {puuid}")
                        return None
                    # Supposons que le rang est dans la première entrée
                    rank_info = data[0].get('tier', {}).get('name', '').lower()
                    if rank_info:
                        logger.debug(f"Rang récupéré pour PUUID {puuid}: {rank_info}")
                        return rank_info
                    else:
                        logger.warning(f"Rang non trouvé dans les données pour PUUID {puuid}")
                        return None
        except aiohttp.ClientError as e:
            logger.error(f"Erreur réseau lors de la récupération du rang pour PUUID {puuid}: {e}")
            return None
        except (IndexError, KeyError) as e:
            logger.error(f"Erreur lors de l'analyse des données de rang pour PUUID {puuid}: {e}")
            return None

    async def get_user_game_data(self, discord_id: int, game: str) -> Optional[Dict[str, str]]:
        """
        Récupère le pseudo, le tag et la région pour un utilisateur et un jeu spécifique.
        """
        username_column = f"{game}_pseudo"
        tag_column = f"{game}_tag"
        region_column = f"{game}_region"
        query = f"SELECT {username_column}, {tag_column}, {region_column} FROM user_id WHERE discord_id = $1;"
        result = await self.database.fetchrow(query, discord_id)

        if result and result[username_column] and result[tag_column] and result[region_column]:
            logger.debug(f"Données de jeu récupérées pour discord_id={discord_id}, jeu={game}: {result}")
            return {"pseudo": result[username_column], "tag": result[tag_column], "region": result[region_column]}
        else:
            logger.debug(f"Aucune donnée de jeu trouvée pour discord_id={discord_id}, jeu={game}")
            return None

    async def get_role_mapping(self, guild_id: int, role_name: str) -> Optional[dict]:
        """
        Récupère les informations de rôle dans `roles_configurations`.
        """
        query = """
            SELECT role_id FROM roles_configurations
            WHERE guild_id = $1 AND role_name = $2;
        """
        result = await self.database.fetchrow(query, guild_id, role_name)
        if result:
            logger.debug(f"Mapping rôle trouvé pour {role_name} dans guild {guild_id}: {result}")
        else:
            logger.debug(f"Aucun mapping rôle trouvé pour {role_name} dans guild {guild_id}.")
        return result

    async def assign_rank_role(self, member: discord.Member, game: str, rank: str):
        """
        Attribue un rôle basé sur un rang pour un jeu donné.
        """
        guild_id = member.guild.id
        mapped_role_name = RANK_TO_ROLE.get(rank)
        if not mapped_role_name:
            logger.warning(f"Aucun rôle mappé trouvé pour le rang '{rank}'.")
            return

        role_record = await self.get_role_mapping(guild_id, mapped_role_name)

        if not role_record:
            logger.warning(f"Aucun rôle configuré pour '{mapped_role_name}' dans le serveur {guild_id}.")
            return

        role = member.guild.get_role(role_record["role_id"])
        if not role:
            logger.error(f"Rôle introuvable pour '{mapped_role_name}' dans le serveur {guild_id}.")
            return

        # Retirer les anciens rôles Valorant
        if game == "valorant":
            roles_to_remove = [r for r in member.roles if r.name.lower() in [v.lower() for v in RANK_TO_ROLE.values()]]
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason="Mise à jour du rang Valorant.")
                logger.debug(f"Rôles retirés de {member.display_name}: {[r.name for r in roles_to_remove]}")

        # Ajouter le nouveau rôle
        await member.add_roles(role, reason=f"Attribution du rang {rank}.")
        logger.info(f"Rôle '{role.name}' attribué à {member.display_name} pour le jeu {game.capitalize()}.")

    async def link_user_game(self, discord_id: int, game: str, pseudo: str, region: str) -> None:
        """
        Lier un pseudo et une région de jeu à un utilisateur Discord dans la base de données.
        """
        pseudo_column = f"{game}_pseudo"
        tag_column = f"{game}_tag"
        region_column = f"{game}_region"
        try:
            username, tag = pseudo.split("#")
        except ValueError:
            logger.error(f"Pseudo '{pseudo}' mal formaté. Doit être sous la forme 'Nom#Tag'.")
            return

        # Valider le pseudo
        if not self.is_valid_valorant_username(username):
            logger.error(f"Pseudo '{username}' invalide.")
            return

        query = f"UPDATE user_id SET {pseudo_column} = $1, {tag_column} = $2, {region_column} = $3 WHERE discord_id = $4;"
        logger.debug(f"Exécution de la requête: {query}, params=({username}, {tag}, {region}, {discord_id})")
        await self.database.execute(query, username, tag, region, discord_id)
        logger.info(f"Pseudo {pseudo} et région {region} liés à discord_id={discord_id} pour le jeu {game}.")
