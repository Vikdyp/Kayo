import datetime
import logging
from typing import Optional, List, Tuple, Dict

import discord

from utils.database import database

logger = logging.getLogger("matchmaking_service")


class MatchmakingService:
    """
    Service principal pour la gestion du matchmaking et des équipes.
    """

    # ------------------------------------------------
    # Cache des rôles
    # ------------------------------------------------
    cached_roles = {}

    # ------------------------------------------------
    # Gestion des Utilisateurs
    # ------------------------------------------------

    @staticmethod
    async def get_user_info(discord_id: int) -> Optional[Dict]:
        """
        Récupère les informations Valorant d'un utilisateur à partir de la base de données.
        Retourne un dict { "elo": int, "region": str }, ou None si introuvable.
        """
        query = """
        SELECT valorant_elo, valorant_region
        FROM user_id
        WHERE discord_id = $1;
        """
        try:
            row = await database.fetchrow(query, discord_id)
            if row:
                logger.debug(f"Infos récupérées pour Discord ID {discord_id}: {row}")
                return {
                    "elo": row["valorant_elo"],
                    "region": row["valorant_region"]
                }
            logger.warning(f"Infos Valorant non trouvées pour Discord ID {discord_id}.")
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des infos user {discord_id}: {e}")
        return None

    @staticmethod
    async def is_user_leader_of_team(member_id: int) -> Optional[str]:
        """
        Vérifie si un utilisateur est le leader d'une équipe (table 'teams').
        Retourne le code de l'équipe si oui, None sinon.
        """
        query = "SELECT code FROM teams WHERE leader_id = $1;"
        try:
            row = await database.fetchrow(query, member_id)
            if row:
                logger.info(f"L'utilisateur {member_id} est leader de l'équipe {row['code']}.")
                return row["code"]
            logger.info(f"L'utilisateur {member_id} n'est leader d'aucune équipe.")
            return None
        except Exception as e:
            logger.error(f"Erreur vérification leader user {member_id}: {e}")
            return None

    @staticmethod
    async def is_user_in_any_team(member_id: int) -> Optional[str]:
        """
        Vérifie si un utilisateur est membre de n'importe quelle équipe (table 'team_members').
        Retourne le code de l'équipe si trouvé, None sinon.
        """
        query = """
        SELECT team_code 
        FROM team_members 
        WHERE member_id = $1 
        LIMIT 1;
        """
        try:
            row = await database.fetchrow(query, member_id)
            return row["team_code"] if row else None
        except Exception as e:
            logger.error(f"Erreur vérif appartenance user {member_id}: {e}")
            return None

    @staticmethod
    async def get_members_from_ids(member_ids: List[int]) -> List[discord.Member]:
        """
        Récupère les objets discord.Member à partir de leurs IDs (multi-guild).
        """
        members = []
        for mid in member_ids:
            found_member = None
            # ATTENTION: ceci requiert que 'database.bot' soit défini ou qu'on ait un accès global au bot
            # Adaptez si nécessaire (ex: un "global bot" ou un "from main import bot" en fonction de votre archi).
            for guild in database.bot.guilds:  
                m = guild.get_member(mid)
                if m:
                    found_member = m
                    break
            if found_member:
                members.append(found_member)
            else:
                logger.warning(f"Membre introuvable en cache Discord: {mid}")
        return members

    # ------------------------------------------------
    # Gestion des Serveurs & Rôles
    # ------------------------------------------------

    @staticmethod
    async def get_server_id(guild_id: int) -> Optional[int]:
        """
        Récupère l'ID interne du serveur depuis un guild_id Discord.
        """
        query = "SELECT id FROM serveur_id WHERE guild_id = $1;"
        try:
            server_id = await database.fetchval(query, guild_id)
            if not server_id:
                logger.warning(f"Serveur non trouvé pour Guild ID {guild_id}.")
            return server_id
        except Exception as e:
            logger.error(f"Erreur get_server_id pour guild {guild_id}: {e}")
            return None

    @staticmethod
    async def get_server_id_by_guild_id(guild_id: int) -> Optional[int]:
        """
        Pareil que get_server_id, avec logs différents.
        """
        query = "SELECT id FROM serveur_id WHERE guild_id = $1;"
        try:
            server_id = await database.fetchval(query, guild_id)
            if server_id:
                logger.info(f"Server ID={server_id} récupéré pour Guild ID={guild_id}")
            else:
                logger.warning(f"Aucun server_id pour Guild ID={guild_id}.")
            return server_id
        except Exception as e:
            logger.error(f"Erreur get_server_id_by_guild_id {guild_id}: {e}")
            return None

    @staticmethod
    async def ensure_roles_cache(guild_id: int) -> None:
        """
        Vérifie que le cache des rôles (cached_roles) est initialisé pour la guilde.
        Sinon, on l'initialise via initialize_filtered_roles_cache(guild_id).
        """
        server_id = await MatchmakingService.get_server_id_by_guild_id(guild_id)
        if not server_id:
            logger.warning(f"Impossible d'init le cache des rôles pour guild {guild_id}: server_id introuvable.")
            return
        if server_id not in MatchmakingService.cached_roles:
            logger.info(f"Aucun rôle en cache pour server_id={server_id}. Initialisation.")
            await MatchmakingService.initialize_filtered_roles_cache(guild_id)
        else:
            logger.info(f"Cache des rôles déjà chargé pour server_id={server_id}.")

    @staticmethod
    async def initialize_filtered_roles_cache(guild_id: int) -> None:
        """
        Méthode manquante : charge les rôles pertinents pour une guilde donnée,
        puis les stocke dans MatchmakingService.cached_roles[server_id].
        """
        server_id = await MatchmakingService.get_server_id_by_guild_id(guild_id)
        if not server_id:
            logger.warning(f"Impossible de charger les rôles pour la guilde {guild_id}: server_id introuvable.")
            return
        roles = await MatchmakingService.load_filtered_roles_for_server(server_id)
        MatchmakingService.cached_roles[server_id] = roles
        logger.info(f"Cache des rôles filtrés initialisé pour guild={guild_id} (server_id={server_id}): {roles}")

    @staticmethod
    async def load_filtered_roles_for_server(server_id: int) -> Dict[str, int]:
        """
        Charge uniquement les rôles spécifiés (duelist, sentinel, etc.) pour un serveur donné.
        """
        target_roles = [
            "sentinel", "duelist", "controller", "initiator", "fill",
            "francais", "anglais", "espagnol", "pc", "console"
        ]
        query = """
        SELECT role_name, role_id
        FROM roles_configurations
        WHERE server_id = $1 AND role_name = ANY($2::text[]);
        """
        roles = {}
        try:
            rows = await database.fetch(query, server_id, target_roles)
            for row in rows:
                roles[row["role_name"]] = row["role_id"]
            logger.info(f"Rôles filtrés pour server_id={server_id}: {roles}")
            return roles
        except Exception as e:
            logger.error(f"Erreur load_filtered_roles_for_server {server_id}: {e}")
            return {}

    @staticmethod
    async def get_user_roles_from_member(member: discord.Member, server_id: int) -> Dict[str, int]:
        """
        Détermine les rôles pertinents (filtrés) qu'un utilisateur Discord possède.
        Retourne {role_name: role_id} pour le server_id donné.
        """
        user_role_ids = {r.id for r in member.roles}
        if server_id not in MatchmakingService.cached_roles:
            logger.warning(f"Aucun rôle filtré en cache pour server_id={server_id}.")
            return {}
        relevant = {
            rn: rid
            for rn, rid in MatchmakingService.cached_roles[server_id].items()
            if rid in user_role_ids
        }
        logger.debug(f"User={member.id} roles filtrés: {relevant}")
        return relevant

    # ------------------------------------------------
    # Gestion des Messages Persistants
    # ------------------------------------------------

    @staticmethod
    async def get_persistent_message(guild_id: int, message_type: str) -> Optional[Tuple[int, int]]:
        """
        Récupère (channel_id, message_id) pour un message persistant dans 'persistent_messages'.
        """
        server_id = await MatchmakingService.get_server_id(guild_id)
        if not server_id:
            logger.warning(f"Serveur ID non trouvé pour guild {guild_id}.")
            return None
        query = """
        SELECT channel_id, message_id
        FROM persistent_messages
        WHERE guild_id = $1 AND message_type = $2;
        """
        try:
            row = await database.fetchrow(query, server_id, message_type)
            if row:
                return (row["channel_id"], row["message_id"])
            logger.warning(f"Message persistant '{message_type}' non trouvé (guild={guild_id}).")
        except Exception as e:
            logger.error(f"Erreur get_persistent_message: {e}")
        return None

    @staticmethod
    async def save_persistent_message(discord_guild_id: int, message_type: str,
                                      channel_id: int, message_id: int,
                                      requester_id: Optional[int] = None) -> None:
        """
        Sauvegarde (ou met à jour) un message persistant dans la table 'persistent_messages'.
        """
        server_id = await MatchmakingService.get_server_id(discord_guild_id)
        if not server_id:
            logger.error(f"Impossible de save_persistent_message: server_id introuvable pour {discord_guild_id}.")
            return
        query = """
        INSERT INTO persistent_messages (guild_id, message_type, channel_id, message_id, requester_id)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (guild_id, message_type)
        DO UPDATE SET channel_id=EXCLUDED.channel_id, message_id=EXCLUDED.message_id, requester_id=EXCLUDED.requester_id;
        """
        try:
            await database.execute(query, server_id, message_type, channel_id, message_id, requester_id)
            logger.info(f"Message persistant '{message_type}' sauvegardé pour guild {discord_guild_id}.")
        except Exception as e:
            logger.error(f"Erreur save_persistent_message: {e}")

    # ------------------------------------------------
    # Gestion des Équipes (tables 'teams', 'team_members')
    # ------------------------------------------------

    @staticmethod
    async def create_team(code: str, leader_id: int, forum_channel_id: int,
                          thread_id: int, visibility: str,
                          created_at: datetime.datetime) -> bool:
        """
        Crée une nouvelle entrée dans la table 'teams'.
        """
        query = """
        INSERT INTO teams (code, leader_id, forum_channel_id, thread_id, visibility, created_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (code) DO NOTHING;
        """
        try:
            result = await database.execute(query, code, leader_id, forum_channel_id,
                                            thread_id, visibility, created_at)
            if result == "INSERT 0 1":
                logger.info(f"Équipe '{code}' créée avec succès.")
                return True
            else:
                logger.warning(f"Équipe '{code}' existe déjà ou conflit.")
                return False
        except Exception as e:
            logger.error(f"Erreur create_team '{code}': {e}")
            return False

    @staticmethod
    async def add_member_to_team(code: str, member_id: int) -> bool:
        """
        Ajoute un membre à l'équipe (table 'team_members').
        """
        query = """
        INSERT INTO team_members (team_code, member_id)
        VALUES ($1, $2)
        ON CONFLICT DO NOTHING;
        """
        try:
            await database.execute(query, code, member_id)
            logger.info(f"Membre {member_id} ajouté à l'équipe '{code}'.")
            return True
        except Exception as e:
            logger.error(f"Erreur add_member_to_team {member_id} -> '{code}': {e}")
            return False

    @staticmethod
    async def remove_member_from_team(code: str, member_id: int) -> bool:
        """
        Retire un membre de l'équipe (table 'team_members').
        """
        query = """
        DELETE FROM team_members
        WHERE team_code=$1 AND member_id=$2;
        """
        try:
            result = await database.execute(query, code, member_id)
            if result == "DELETE 1":
                logger.info(f"Membre {member_id} retiré de l'équipe '{code}'.")
                return True
            else:
                logger.warning(f"Membre {member_id} pas présent dans l'équipe '{code}'.")
                return False
        except Exception as e:
            logger.error(f"Erreur remove_member_from_team {member_id} -> '{code}': {e}")
            return False

    @staticmethod
    async def get_team(code: str) -> Optional[Dict]:
        """
        Récupère l'équipe (table 'teams') via son code.
        """
        query = "SELECT * FROM teams WHERE code=$1;"
        try:
            row = await database.fetchrow(query, code)
            if row:
                return {
                    "code": row["code"],
                    "leader_id": row["leader_id"],
                    "forum_channel_id": row["forum_channel_id"],
                    "thread_id": row["thread_id"],
                    "visibility": row["visibility"],
                    "voice_channel_id": row["voice_channel_id"]
                }
            logger.warning(f"Équipe '{code}' introuvable.")
            return None
        except Exception as e:
            logger.error(f"Erreur get_team {code}: {e}")
            return None

    @staticmethod
    async def get_team_members(code: str) -> List[int]:
        """
        Récupère la liste des member_id (table 'team_members') pour l'équipe donnée.
        """
        query = "SELECT member_id FROM team_members WHERE team_code=$1;"
        try:
            rows = await database.fetch(query, code)
            return [r["member_id"] for r in rows]
        except Exception as e:
            logger.error(f"Erreur get_team_members '{code}': {e}")
            return []

    @staticmethod
    async def delete_team(code: str) -> bool:
        """
        Supprime l'équipe (table 'teams') + triggers on 'team_members' si on veut ON DELETE CASCADE.
        """
        query = "DELETE FROM teams WHERE code=$1;"
        try:
            result = await database.execute(query, code)
            if result.startswith("DELETE"):
                logger.info(f"Équipe '{code}' supprimée avec succès.")
                return True
            else:
                logger.warning(f"Équipe '{code}' introuvable pour suppression.")
                return False
        except Exception as e:
            logger.error(f"Erreur delete_team '{code}': {e}")
            return False

    @staticmethod
    async def update_voice_channel_id(code: str, voice_channel_id: int) -> bool:
        """
        Met à jour le champ voice_channel_id dans table 'teams'.
        """
        query = """
        UPDATE teams
        SET voice_channel_id=$2
        WHERE code=$1;
        """
        try:
            result = await database.execute(query, code, voice_channel_id)
            if result == "UPDATE 1":
                logger.info(f"voice_channel_id={voice_channel_id} mis à jour pour team '{code}'.")
                return True
            else:
                logger.warning(f"Impossible d'update team '{code}'.")
                return False
        except Exception as e:
            logger.error(f"Erreur update_voice_channel_id '{code}': {e}")
            return False

    @staticmethod
    async def get_all_teams() -> List[Dict]:
        """
        Récupère toutes les équipes (table 'teams').
        """
        query = "SELECT * FROM teams;"
        try:
            rows = await database.fetch(query)
            teams = []
            for r in rows:
                teams.append({
                    "code": r["code"],
                    "leader_id": r["leader_id"],
                    "forum_channel_id": r["forum_channel_id"],
                    "thread_id": r["thread_id"],
                    "visibility": r["visibility"],
                    "voice_channel_id": r["voice_channel_id"]
                })
            return teams
        except Exception as e:
            logger.error(f"Erreur get_all_teams: {e}")
            return []

    @staticmethod
    async def get_public_teams() -> List[Dict]:
        """
        Récupère toutes les équipes avec visibility='public'.
        """
        query = """
        SELECT code, leader_id, visibility 
        FROM teams 
        WHERE visibility='public';
        """
        try:
            rows = await database.fetch(query)
            return [
                {"code": r["code"], "leader_id": r["leader_id"], "visibility": r["visibility"]}
                for r in rows
            ]
        except Exception as e:
            logger.error(f"Erreur get_public_teams: {e}")
            return []

    @staticmethod
    async def get_teams_older_than(hours: int = 24) -> List[Dict]:
        """
        Récupère toutes les équipes dont created_at < now() - hours.
        """
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
        query = "SELECT * FROM teams WHERE created_at < $1;"
        try:
            rows = await database.fetch(query, cutoff)
            results = []
            for r in rows:
                results.append({
                    "code": r["code"],
                    "leader_id": r["leader_id"],
                    "forum_channel_id": r["forum_channel_id"],
                    "thread_id": r["thread_id"],
                    "visibility": r["visibility"],
                    "voice_channel_id": r["voice_channel_id"]
                })
            return results
        except Exception as e:
            logger.error(f"Erreur get_teams_older_than: {e}")
            return []

    # ------------------------------------------------
    # Gestion de la queue (table 'matchmaking_queue')
    # ------------------------------------------------

    @staticmethod
    async def add_entry_to_queue(
        entry_type: int,                 # 1=solo,2=duo,3=trio,4=quatuor,5=full
        discord_member_id: int,         # ID du leader ou du joueur solo
        team_member_ids: Optional[List[int]],
        langue: str,
        region: str,
        platform: str,
        team_size: int,                 # taille finale (2,3,5,... ou 0='n'importe')
        mmr_extended: bool,
        elo: Optional[int],
        elo_high: Optional[int],
        elo_low: Optional[int],
        roles: List[str]
    ) -> None:
        """
        Ajoute un bloc (solo ou groupe) dans la table matchmaking_queue, 
        avec la nouvelle structure unifiée.
        """
        query = """
        INSERT INTO matchmaking_queue (
            entry_type,
            discord_member_id,
            team_member_ids,
            langue,
            region,
            platform,
            team_size,
            mmr_extended,
            elo,
            elo_high,
            elo_low,
            roles
        )
        VALUES ($1, $2, $3, $4, $5, $6,
                $7, $8, $9, $10, $11, $12)
        """
        try:
            await database.execute(
                query,
                entry_type,
                discord_member_id,
                team_member_ids if team_member_ids else None,
                langue,
                region,
                platform,
                team_size,
                mmr_extended,
                elo,
                elo_high,
                elo_low,
                roles
            )
            logger.info(
                f"[Queue] Entry added: entry_type={entry_type}, leader_id={discord_member_id}, "
                f"team_size={team_size}, mmr_extended={mmr_extended}, "
                f"elo={elo}, elo_high={elo_high}, elo_low={elo_low}, roles={roles}"
            )
        except Exception as e:
            logger.error(f"[Queue] Erreur insertion matchmaking_queue: {e}")
            raise e

    @staticmethod
    async def get_queue_entries() -> List[Dict]:
        """
        Récupère toutes les entrées (matchmaking_queue), triées par timestamp ASC.
        """
        query = """
        SELECT * 
        FROM matchmaking_queue
        ORDER BY timestamp ASC;
        """
        try:
            rows = await database.fetch(query)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Erreur get_queue_entries: {e}")
            return []

    @staticmethod
    async def remove_player_from_queue(discord_id: int) -> bool:
        """
        Supprime UNE entrée repérée par discord_member_id (cas solo ou leader).
        Note : si c'est un groupe, on laisse la question de la suppr complète ou non au code du cog.
        """
        query = "DELETE FROM matchmaking_queue WHERE discord_member_id = $1;"
        try:
            result = await database.execute(query, discord_id)
            if "DELETE 1" in result:
                logger.info(f"[Queue] Joueur/leader {discord_id} retiré de la queue.")
                return True
            else:
                logger.warning(f"[Queue] {discord_id} non trouvé ou déjà retiré.")
                return False
        except Exception as e:
            logger.error(f"[Queue] Erreur remove_player_from_queue {discord_id}: {e}")
            return False

    @staticmethod
    async def remove_players_from_queue(member_ids: List[int]) -> None:
        """
        Retire plusieurs joueurs en se basant sur discord_member_id IN (..).
        """
        query = """
        DELETE FROM matchmaking_queue
        WHERE discord_member_id = ANY($1::bigint[]);
        """
        try:
            await database.execute(query, member_ids)
            logger.info(f"[Queue] Joueurs retirés: {member_ids}")
        except Exception as e:
            logger.error(f"[Queue] Erreur remove_players_from_queue {member_ids}: {e}")

    @staticmethod
    async def is_player_in_queue(discord_id: int) -> bool:
        """
        Vérifie si un discord_member_id (solo ou leader) figure dans matchmaking_queue.
        """
        query = "SELECT 1 FROM matchmaking_queue WHERE discord_member_id=$1 LIMIT 1;"
        try:
            row = await database.fetchrow(query, discord_id)
            return (row is not None)
        except Exception as e:
            logger.error(f"Erreur is_player_in_queue {discord_id}: {e}")
            return False

    #
    # Méthodes de comptage (optionnelles) :
    #

    @staticmethod
    async def count_solos_in_queue() -> int:
        """
        Compte les entrées 'solo' => entry_type=1
        """
        query = "SELECT COUNT(*) FROM matchmaking_queue WHERE entry_type=1;"
        try:
            return await database.fetchval(query) or 0
        except Exception as e:
            logger.error(f"Erreur count_solos_in_queue: {e}")
            return 0

    @staticmethod
    async def count_teams_in_queue() -> int:
        """
        Compte les blocs où entry_type>1 (duo, trio, quatuor, 5-stack).
        """
        query = "SELECT COUNT(*) FROM matchmaking_queue WHERE entry_type>1;"
        try:
            return await database.fetchval(query) or 0
        except Exception as e:
            logger.error(f"Erreur count_teams_in_queue: {e}")
            return 0

    @staticmethod
    async def count_total_members_in_queue() -> int:
        """
        Compte le nombre total d'entrées (pas le nombre total de PERSONNES).
        Si vous voulez réellement la somme de tous les membres :
        - Option : SUM cardinalité de team_member_ids + count solo
        """
        query = "SELECT COUNT(*) FROM matchmaking_queue;"
        try:
            return await database.fetchval(query) or 0
        except Exception as e:
            logger.error(f"Erreur count_total_members_in_queue: {e}")
            return 0

    @staticmethod
    async def get_roles_for_discord_member(discord_id: int) -> Optional[List[str]]:
        """
        Récupère la liste des rôles (ex: ["duelist", "controller"])
        depuis la table matchmaking_queue pour un discord_member_id donné.
        
        Note: si ce membre n'est plus dans la queue, ça retournera None.
        """
        query = """
        SELECT roles 
        FROM matchmaking_queue
        WHERE discord_member_id=$1
        LIMIT 1;
        """
        try:
            row = await database.fetchrow(query, discord_id)
            if row:
                return row["roles"]  # c'est un tableau / liste
            return None
        except Exception as e:
            logger.error(f"Erreur get_roles_for_discord_member {discord_id}: {e}")
            return None

    # Fin
