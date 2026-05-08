#cogs\voice_management\services\five_stack_service.py
import datetime
import logging
from typing import Optional, List, Tuple, Dict, Any

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
        
        Désormais, on joint la table `valorant_info` et `user_id`.
        """
        query = """
        SELECT v.elo, v.region
          FROM valorant_info v
          JOIN user_id u ON v.user_id = u.id
         WHERE u.discord_id = $1
        """
        try:
            row = await database.fetchrow(query, discord_id)
            if row:
                logger.debug(f"Infos Valorant récupérées pour Discord ID {discord_id}: {row}")
                return {
                    "elo": row["elo"],
                    "region": row["region"]
                }
            logger.warning(f"Infos Valorant non trouvées pour Discord ID {discord_id}.")
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des infos user {discord_id}: {e}")
        return None

    @staticmethod
    async def is_user_leader_of_team(member_id: int, server_id: int) -> Optional[str]:
        """
        Vérifie si un utilisateur est le leader d'une équipe (table 'teams').
        Retourne le code de l'équipe si oui, None sinon.
        """
        query = "SELECT code FROM teams WHERE leader_id = $1 AND server_id = $2;"
        try:
            row = await database.fetchrow(query, member_id, server_id)
            if row:
                logger.info(f"L'utilisateur {member_id} est leader de l'équipe {row['code']}.")
                return row["code"]
            logger.info(f"L'utilisateur {member_id} n'est leader d'aucune équipe.")
            return None
        except Exception as e:
            logger.error(f"Erreur vérification leader user {member_id}: {e}")
            return None

    @staticmethod
    async def is_user_in_any_team(member_id: int, server_id: int) -> Optional[str]:
        """
        Vérifie si un utilisateur est membre de n'importe quelle équipe (table 'team_members').
        Retourne le code de l'équipe si trouvé, None sinon.
        """
        query = """
        SELECT team_code
        FROM team_members
        WHERE member_id = $1 AND server_id = $2
        LIMIT 1;
        """
        try:
            row = await database.fetchrow(query, member_id, server_id)
            return row["team_code"] if row else None
        except Exception as e:
            logger.error(f"Erreur vérif appartenance user {member_id}: {e}")
            return None

    @staticmethod
    async def get_user_team(member_id: int, server_id: int) -> Optional[Dict[str, Any]]:
        """
        Récupère l'équipe complète d'un utilisateur s'il en fait partie.

        Args:
            member_id: ID Discord du membre
            server_id: ID interne du serveur

        Returns:
            Dict avec les infos de l'équipe ou None
        """
        query = """
        SELECT t.code, t.leader_id, t.forum_channel_id, t.thread_id,
               t.visibility, t.voice_channel_id, t.created_at, t.server_id
        FROM teams t
        INNER JOIN team_members tm ON t.code = tm.team_code AND t.server_id = tm.server_id
        WHERE tm.member_id = $1 AND tm.server_id = $2
        LIMIT 1;
        """
        try:
            row = await database.fetchrow(query, member_id, server_id)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Erreur récupération équipe pour user {member_id}: {e}")
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
        WHERE server_id = $1 AND message_type = $2;
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
        INSERT INTO persistent_messages (server_id, message_type, channel_id, message_id, requester_id)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (server_id, message_type)
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
    async def create_team(
        code: str,
        leader_id: int,
        forum_channel_id: int,
        thread_id: int,
        visibility: str,
        created_at: datetime.datetime,
        server_id: int,
    ) -> bool:
        """
        Crée une nouvelle entrée dans la table 'teams'.
        """
        query = """
        INSERT INTO teams (code, leader_id, forum_channel_id, thread_id, visibility, created_at, server_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (code) DO NOTHING;
        """
        try:
            result = await database.execute(query, code, leader_id, forum_channel_id,
                                            thread_id, visibility, created_at, server_id)
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
    async def add_member_to_team(code: str, member_id: int, server_id: int) -> bool:
        """
        Ajoute un membre à l'équipe (table 'team_members').
        """
        query = """
        INSERT INTO team_members (team_code, member_id, server_id)
        VALUES ($1, $2, $3)
        ON CONFLICT DO NOTHING;
        """
        try:
            await database.execute(query, code, member_id, server_id)
            logger.info(f"Membre {member_id} ajouté à l'équipe '{code}'.")
            return True
        except Exception as e:
            logger.error(f"Erreur add_member_to_team {member_id} -> '{code}': {e}")
            return False

    @staticmethod
    async def remove_member_from_team(code: str, member_id: int, server_id: int) -> bool:
        """
        Retire un membre de l'équipe (table 'team_members').
        """
        query = """
        DELETE FROM team_members
        WHERE team_code=$1 AND member_id=$2 AND server_id=$3;
        """
        try:
            result = await database.execute(query, code, member_id, server_id)
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
    async def get_team(code: str, server_id: int) -> Optional[Dict]:
        """
        Récupère l'équipe (table 'teams') via son code.
        """
        query = "SELECT * FROM teams WHERE code=$1 AND server_id=$2;"
        try:
            row = await database.fetchrow(query, code, server_id)
            if row:
                return {
                    "code": row["code"],
                    "leader_id": row["leader_id"],
                    "forum_channel_id": row["forum_channel_id"],
                    "thread_id": row["thread_id"],
                    "visibility": row["visibility"],
                    "voice_channel_id": row["voice_channel_id"],
                    "server_id": row["server_id"],
                }
            logger.warning(f"Équipe '{code}' introuvable.")
            return None
        except Exception as e:
            logger.error(f"Erreur get_team {code}: {e}")
            return None

    @staticmethod
    async def get_team_members(code: str, server_id: int) -> List[int]:
        """
        Récupère la liste des member_id (table 'team_members') pour l'équipe donnée.
        """
        query = "SELECT member_id FROM team_members WHERE team_code=$1 AND server_id=$2;"
        try:
            rows = await database.fetch(query, code, server_id)
            return [r["member_id"] for r in rows]
        except Exception as e:
            logger.error(f"Erreur get_team_members '{code}': {e}")
            return []

    @staticmethod
    async def delete_team(code: str, server_id: int) -> bool:
        """
        Supprime l'équipe (table 'teams') + triggers on 'team_members' si on veut ON DELETE CASCADE.
        """
        query = "DELETE FROM teams WHERE code=$1 AND server_id=$2;"
        try:
            result = await database.execute(query, code, server_id)
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
    async def update_voice_channel_id(code: str, voice_channel_id: int, server_id: int) -> bool:
        """
        Met à jour le champ voice_channel_id dans table 'teams'.
        """
        query = """
        UPDATE teams
        SET voice_channel_id=$2
        WHERE code=$1 AND server_id=$3;
        """
        try:
            result = await database.execute(query, code, voice_channel_id, server_id)
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
    async def get_all_teams(server_id: int) -> List[Dict]:
        """
        Récupère toutes les équipes (table 'teams').
        """
        query = "SELECT * FROM teams WHERE server_id=$1;"
        try:
            rows = await database.fetch(query, server_id)
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
    async def get_public_teams(server_id: int) -> List[Dict]:
        """
        Récupère toutes les équipes avec visibility='public'.
        """
        query = """
        SELECT code, leader_id, visibility 
        FROM teams
        WHERE visibility='public' AND server_id=$1;
        """
        try:
            rows = await database.fetch(query, server_id)
            return [
                {"code": r["code"], "leader_id": r["leader_id"], "visibility": r["visibility"]}
                for r in rows
            ]
        except Exception as e:
            logger.error(f"Erreur get_public_teams: {e}")
            return []

    @staticmethod
    async def get_teams_older_than(server_id: Optional[int] = None, hours: int = 24) -> List[Dict]:
        """
        Récupère toutes les équipes dont created_at < now() - hours.
        """
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
        try:
            if server_id is None:
                query = "SELECT * FROM teams WHERE created_at < $1;"
                rows = await database.fetch(query, cutoff)
            else:
                query = "SELECT * FROM teams WHERE created_at < $1 AND server_id=$2;"
                rows = await database.fetch(query, cutoff, server_id)
            results = []
            for r in rows:
                results.append({
                    "code": r["code"],
                    "leader_id": r["leader_id"],
                    "forum_channel_id": r["forum_channel_id"],
                    "thread_id": r["thread_id"],
                    "visibility": r["visibility"],
                    "voice_channel_id": r["voice_channel_id"],
                    "server_id": r["server_id"],
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
        server_id: int,
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
            server_id,
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
                $7, $8, $9, $10, $11, $12, $13)
        """
        try:
            await database.execute(
                query,
                server_id,
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
    async def get_queue_entries(server_id: Optional[int] = None) -> List[Dict]:
        """
        Récupère toutes les entrées (matchmaking_queue), triées par timestamp ASC.
        """
        try:
            if server_id is None:
                query = """
                SELECT *
                FROM matchmaking_queue
                ORDER BY timestamp ASC;
                """
                rows = await database.fetch(query)
            else:
                query = """
                SELECT *
                FROM matchmaking_queue
                WHERE server_id = $1
                ORDER BY timestamp ASC;
                """
                rows = await database.fetch(query, server_id)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Erreur get_queue_entries: {e}")
            return []

    @staticmethod
    async def remove_player_from_queue(server_id: int, discord_id: int) -> bool:
        """
        Supprime UNE entrée repérée par discord_member_id (cas solo ou leader).
        Note : si c'est un groupe, on laisse la question de la suppr complète ou non au code du cog.
        """
        query = "DELETE FROM matchmaking_queue WHERE discord_member_id = $1 AND server_id = $2;"
        try:
            result = await database.execute(query, discord_id, server_id)
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
    async def remove_players_from_queue(server_id: int, member_ids: List[int]) -> None:
        """
        Retire plusieurs joueurs en se basant sur discord_member_id IN (..).
        """
        query = """
        DELETE FROM matchmaking_queue
        WHERE discord_member_id = ANY($1::bigint[]) AND server_id = $2;
        """
        try:
            await database.execute(query, member_ids, server_id)
            logger.info(f"[Queue] Joueurs retirés: {member_ids}")
        except Exception as e:
            logger.error(f"[Queue] Erreur remove_players_from_queue {member_ids}: {e}")

    @staticmethod
    async def is_player_in_queue(server_id: int, discord_id: int) -> bool:
        """
        Vérifie si un discord_member_id (solo ou leader) figure dans matchmaking_queue.
        """
        query = "SELECT 1 FROM matchmaking_queue WHERE discord_member_id=$1 AND server_id=$2 LIMIT 1;"
        try:
            row = await database.fetchrow(query, discord_id, server_id)
            return (row is not None)
        except Exception as e:
            logger.error(f"Erreur is_player_in_queue {discord_id}: {e}")
            return False

    #
    # Méthodes de comptage (optionnelles) :
    #

    @staticmethod
    async def count_solos_in_queue(server_id: int) -> int:
        """
        Compte les entrées 'solo' => entry_type=1
        """
        query = "SELECT COUNT(*) FROM matchmaking_queue WHERE entry_type=1 AND server_id=$1;"
        try:
            return await database.fetchval(query, server_id) or 0
        except Exception as e:
            logger.error(f"Erreur count_solos_in_queue: {e}")
            return 0

    @staticmethod
    async def count_teams_in_queue(server_id: int) -> int:
        """
        Compte les blocs où entry_type>1 (duo, trio, quatuor, 5-stack).
        """
        query = "SELECT COUNT(*) FROM matchmaking_queue WHERE entry_type>1 AND server_id=$1;"
        try:
            return await database.fetchval(query, server_id) or 0
        except Exception as e:
            logger.error(f"Erreur count_teams_in_queue: {e}")
            return 0

    @staticmethod
    async def count_total_members_in_queue(server_id: int) -> int:
        """
        Compte le nombre total d'entrées (pas le nombre total de PERSONNES).
        Si vous voulez réellement la somme de tous les membres :
        - Option : SUM cardinalité de team_member_ids + count solo
        """
        query = "SELECT COUNT(*) FROM matchmaking_queue WHERE server_id=$1;"
        try:
            return await database.fetchval(query, server_id) or 0
        except Exception as e:
            logger.error(f"Erreur count_total_members_in_queue: {e}")
            return 0

    @staticmethod
    async def get_roles_for_discord_member(server_id: int, discord_id: int) -> Optional[List[str]]:
        """
        Récupère la liste des rôles (ex: ["duelist", "controller"])
        depuis la table matchmaking_queue pour un discord_member_id donné.
        
        Note: si ce membre n'est plus dans la queue, ça retournera None.
        """
        query = """
        SELECT roles 
        FROM matchmaking_queue
        WHERE discord_member_id=$1 AND server_id=$2
        LIMIT 1;
        """
        try:
            row = await database.fetchrow(query, discord_id, server_id)
            if row:
                return row["roles"]  # c'est un tableau / liste
            return None
        except Exception as e:
            logger.error(f"Erreur get_roles_for_discord_member {discord_id}: {e}")
            return None
        
    @classmethod
    async def update_team_leader(cls, code: str, new_leader_id: int, server_id: int) -> bool:
        """
        Met à jour le leader de l'équipe (table 'teams').
        Retourne True si une ligne a été mise à jour, False sinon.
        """
        query = """
            UPDATE teams
            SET leader_id=$1
            WHERE code=$2 AND server_id=$3
        """
        try:
            result = await database.execute(query, new_leader_id, code, server_id)
            # Souvent, asyncpg renvoie un string style "UPDATE 1" si 1 ligne mise à jour.
            if result == "UPDATE 1":
                logger.info(f"Leader mis à jour: {new_leader_id} pour équipe '{code}'.")
                return True
            else:
                logger.warning(f"UPDATE leader échouée ou 0 lignes impactées (code='{code}').")
                return False
        except Exception as e:
            logger.error(f"Erreur update_team_leader: {e}")
            return False

    @staticmethod
    async def count_total_players_in_queue(server_id: int) -> int:
        """
        Compte le nombre total de joueurs en file :
        - Si entry_type=1, on compte 1
        - Sinon, on compte cardinality(team_member_ids)
        """
        query = """
        SELECT COALESCE(SUM(
            CASE WHEN entry_type = 1 THEN 1
                 ELSE cardinality(team_member_ids)
            END
        ), 0)
        FROM matchmaking_queue
        WHERE server_id=$1;
        """
        try:
            return await database.fetchval(query, server_id) or 0
        except Exception as e:
            logger.error(f"Erreur count_total_players_in_queue: {e}")
            return 0

    @staticmethod
    async def update_entry_team_size_any(entry_id: int, server_id: int) -> bool:
        """
        Passe team_size à 0 (any) pour une entrée donnée.
        """
        query = """
        UPDATE matchmaking_queue
        SET team_size = 0
        WHERE id = $1 AND server_id = $2;
        """
        try:
            result = await database.execute(query, entry_id, server_id)
            return result == "UPDATE 1"
        except Exception as e:
            logger.error(f"Erreur update_entry_team_size_any {entry_id}: {e}")
            return False

    @staticmethod
    async def remove_entry(entry_id: int, server_id: int) -> bool:
        """
        Supprime l'entrée de matchmaking_queue par son ID.
        """
        query = "DELETE FROM matchmaking_queue WHERE id = $1 AND server_id = $2;"
        try:
            result = await database.execute(query, entry_id, server_id)
            return result.startswith("DELETE")
        except Exception as e:
            logger.error(f"Erreur remove_entry {entry_id}: {e}")
            return False

    # ------------------------------------------------
    # Gestion de l'historique des matchs (table 'match_history')
    # ------------------------------------------------

    @staticmethod
    async def create_match_history(
        server_id: int,
        match_code: str,
        voice_channel_id: Optional[int],
        match_quality_score: Optional[float],
        elo_spread: Optional[int],
        avg_elo: Optional[int],
        role_diversity_score: Optional[float],
        total_wait_time_seconds: Optional[int],
        team_size: int,
        langue: str,
        region: str,
        platform: str
    ) -> Optional[int]:
        """
        Crée une entrée dans match_history et retourne l'ID du match créé.
        """
        query = """
        INSERT INTO match_history (
            server_id, match_code, voice_channel_id, match_quality_score,
            elo_spread, avg_elo, role_diversity_score, total_wait_time_seconds,
            team_size, langue, region, platform
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        RETURNING id;
        """
        try:
            match_id = await database.fetchval(
                query, server_id, match_code, voice_channel_id, match_quality_score,
                elo_spread, avg_elo, role_diversity_score, total_wait_time_seconds,
                team_size, langue, region, platform
            )
            logger.info(f"[MatchHistory] Match créé: id={match_id}, code={match_code}")
            return match_id
        except Exception as e:
            logger.error(f"[MatchHistory] Erreur création match: {e}")
            return None

    @staticmethod
    async def add_match_participant(
        match_id: int,
        discord_member_id: int,
        elo_at_match: Optional[int],
        roles_selected: List[str],
        entry_type: int,
        wait_time_seconds: int
    ) -> bool:
        """
        Ajoute un participant à un match.
        """
        query = """
        INSERT INTO match_participants (
            match_id, discord_member_id, elo_at_match, roles_selected,
            entry_type, wait_time_seconds
        )
        VALUES ($1, $2, $3, $4, $5, $6);
        """
        try:
            await database.execute(
                query, match_id, discord_member_id, elo_at_match,
                roles_selected, entry_type, wait_time_seconds
            )
            logger.debug(f"[MatchHistory] Participant ajouté: match={match_id}, member={discord_member_id}")
            return True
        except Exception as e:
            logger.error(f"[MatchHistory] Erreur ajout participant: {e}")
            return False

    @staticmethod
    async def get_match_history(server_id: int, limit: int = 10) -> List[Dict]:
        """
        Récupère les X derniers matchs pour un serveur.
        """
        query = """
        SELECT id, match_code, created_at, match_quality_score, elo_spread,
               avg_elo, role_diversity_score, team_size, langue, region, platform
        FROM match_history
        WHERE server_id = $1
        ORDER BY created_at DESC
        LIMIT $2;
        """
        try:
            rows = await database.fetch(query, server_id, limit)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[MatchHistory] Erreur get_match_history: {e}")
            return []

    @staticmethod
    async def get_player_match_history(discord_id: int, server_id: int, limit: int = 10) -> List[Dict]:
        """
        Récupère l'historique des matchs d'un joueur.
        """
        query = """
        SELECT mh.id, mh.match_code, mh.created_at, mh.match_quality_score,
               mh.team_size, mh.elo_spread, mh.avg_elo,
               mp.elo_at_match, mp.roles_selected, mp.entry_type
        FROM match_history mh
        JOIN match_participants mp ON mh.id = mp.match_id
        WHERE mp.discord_member_id = $1 AND mh.server_id = $2
        ORDER BY mh.created_at DESC
        LIMIT $3;
        """
        try:
            rows = await database.fetch(query, discord_id, server_id, limit)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[MatchHistory] Erreur get_player_match_history: {e}")
            return []

    @staticmethod
    async def get_match_participants(match_id: int) -> List[Dict]:
        """
        Récupère tous les participants d'un match.
        """
        query = """
        SELECT discord_member_id, elo_at_match, roles_selected, entry_type, wait_time_seconds
        FROM match_participants
        WHERE match_id = $1;
        """
        try:
            rows = await database.fetch(query, match_id)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[MatchHistory] Erreur get_match_participants: {e}")
            return []

    # ------------------------------------------------
    # Gestion des statistiques joueur (table 'player_matchmaking_stats')
    # ------------------------------------------------

    @staticmethod
    async def get_player_stats(discord_id: int, server_id: int) -> Optional[Dict]:
        """
        Récupère les statistiques de matchmaking d'un joueur.
        """
        query = """
        SELECT total_matches, total_wait_time_seconds, matches_as_solo,
               matches_in_group, last_match_at, preferred_role,
               CASE WHEN total_matches > 0
                    THEN total_wait_time_seconds / total_matches
                    ELSE 0
               END as avg_wait_time_seconds
        FROM player_matchmaking_stats
        WHERE discord_id = $1 AND server_id = $2;
        """
        try:
            row = await database.fetchrow(query, discord_id, server_id)
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"[Stats] Erreur get_player_stats: {e}")
            return None

    @staticmethod
    async def update_player_stats(
        discord_id: int,
        server_id: int,
        wait_time_seconds: int,
        is_solo: bool,
        roles: Optional[List[str]] = None
    ) -> bool:
        """
        Met à jour les statistiques d'un joueur après un match.
        Utilise UPSERT pour créer l'entrée si elle n'existe pas.

        Args:
            discord_id: ID Discord du joueur
            server_id: ID interne du serveur
            wait_time_seconds: Temps d'attente en secondes
            is_solo: True si le joueur était en solo
            roles: Liste des rôles sélectionnés (le premier non-fill sera le préféré)
        """
        # Déterminer le rôle préféré (premier rôle non-fill)
        preferred_role = None
        if roles:
            for r in roles:
                if r.lower() != 'fill':
                    preferred_role = r
                    break

        query = """
        INSERT INTO player_matchmaking_stats (
            discord_id, server_id, total_matches, total_wait_time_seconds,
            matches_as_solo, matches_in_group, last_match_at, preferred_role
        )
        VALUES ($1, $2, 1, $3, $4, $5, NOW(), $6)
        ON CONFLICT (discord_id, server_id) DO UPDATE SET
            total_matches = player_matchmaking_stats.total_matches + 1,
            total_wait_time_seconds = player_matchmaking_stats.total_wait_time_seconds + $3,
            matches_as_solo = player_matchmaking_stats.matches_as_solo + $4,
            matches_in_group = player_matchmaking_stats.matches_in_group + $5,
            last_match_at = NOW(),
            preferred_role = COALESCE($6, player_matchmaking_stats.preferred_role);
        """
        try:
            solo_increment = 1 if is_solo else 0
            group_increment = 0 if is_solo else 1
            await database.execute(
                query, discord_id, server_id, wait_time_seconds,
                solo_increment, group_increment, preferred_role
            )
            logger.debug(f"[Stats] Stats mises à jour pour {discord_id}")
            return True
        except Exception as e:
            logger.error(f"[Stats] Erreur update_player_stats: {e}")
            return False

    @staticmethod
    async def get_server_stats(server_id: int) -> Dict:
        """
        Récupère les statistiques globales de matchmaking pour un serveur.
        """
        query = """
        SELECT
            COUNT(*) as total_matches,
            AVG(match_quality_score) as avg_quality_score,
            AVG(elo_spread) as avg_elo_spread,
            AVG(total_wait_time_seconds) as avg_total_wait_time
        FROM match_history
        WHERE server_id = $1;
        """
        try:
            row = await database.fetchrow(query, server_id)
            if row:
                return dict(row)
            return {"total_matches": 0, "avg_quality_score": 0, "avg_elo_spread": 0, "avg_total_wait_time": 0}
        except Exception as e:
            logger.error(f"[Stats] Erreur get_server_stats: {e}")
            return {"total_matches": 0, "avg_quality_score": 0, "avg_elo_spread": 0, "avg_total_wait_time": 0}

    # ------------------------------------------------
    # Gestion du feedback (table 'match_feedback')
    # ------------------------------------------------

    @staticmethod
    async def save_match_feedback(
        match_id: int,
        reporter_id: int,
        rating: int,
        feedback_type: str,
        issues: Optional[List[str]] = None,
        comment: Optional[str] = None
    ) -> bool:
        """
        Enregistre le feedback d'un joueur pour un match.
        """
        query = """
        INSERT INTO match_feedback (match_id, reporter_id, rating, feedback_type, issues, comment)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (match_id, reporter_id) DO UPDATE SET
            rating = EXCLUDED.rating,
            feedback_type = EXCLUDED.feedback_type,
            issues = EXCLUDED.issues,
            comment = EXCLUDED.comment,
            created_at = NOW();
        """
        try:
            await database.execute(query, match_id, reporter_id, rating, feedback_type, issues, comment)
            logger.info(f"[Feedback] Feedback enregistré: match={match_id}, reporter={reporter_id}, rating={rating}")
            return True
        except Exception as e:
            logger.error(f"[Feedback] Erreur save_match_feedback: {e}")
            return False

    @staticmethod
    async def get_match_feedback(match_id: int) -> List[Dict]:
        """
        Récupère tous les feedbacks pour un match.
        """
        query = """
        SELECT reporter_id, rating, feedback_type, issues, comment, created_at
        FROM match_feedback
        WHERE match_id = $1;
        """
        try:
            rows = await database.fetch(query, match_id)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[Feedback] Erreur get_match_feedback: {e}")
            return []

    @staticmethod
    async def has_user_given_feedback(match_id: int, reporter_id: int) -> bool:
        """
        Vérifie si un utilisateur a déjà donné son feedback pour un match.
        """
        query = "SELECT 1 FROM match_feedback WHERE match_id = $1 AND reporter_id = $2 LIMIT 1;"
        try:
            row = await database.fetchrow(query, match_id, reporter_id)
            return row is not None
        except Exception as e:
            logger.error(f"[Feedback] Erreur has_user_given_feedback: {e}")
            return False

    @staticmethod
    async def get_avg_feedback_rating(server_id: int) -> Optional[float]:
        """
        Récupère la note moyenne des feedbacks pour un serveur.
        """
        query = """
        SELECT AVG(mf.rating) as avg_rating
        FROM match_feedback mf
        JOIN match_history mh ON mf.match_id = mh.id
        WHERE mh.server_id = $1;
        """
        try:
            return await database.fetchval(query, server_id)
        except Exception as e:
            logger.error(f"[Feedback] Erreur get_avg_feedback_rating: {e}")
            return None

    @staticmethod
    async def get_matches_pending_feedback(discord_id: int, server_id: int, hours: int = 24) -> List[Dict]:
        """
        Récupère les matchs récents d'un joueur pour lesquels il n'a pas encore donné de feedback.
        """
        query = """
        SELECT mh.id, mh.match_code, mh.created_at, mh.team_size
        FROM match_history mh
        JOIN match_participants mp ON mh.id = mp.match_id
        LEFT JOIN match_feedback mf ON mh.id = mf.match_id AND mf.reporter_id = $1
        WHERE mp.discord_member_id = $1
          AND mh.server_id = $2
          AND mh.created_at > NOW() - INTERVAL '%s hours'
          AND mf.id IS NULL
        ORDER BY mh.created_at DESC;
        """ % hours
        try:
            rows = await database.fetch(query, discord_id, server_id)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[Feedback] Erreur get_matches_pending_feedback: {e}")
            return []

    # ------------------------------------------------
    # Utilitaires pour le matching amélioré
    # ------------------------------------------------

    @staticmethod
    async def get_avg_match_interval(server_id: int) -> int:
        """
        Calcule l'intervalle moyen entre les matchs en secondes.
        Utile pour estimer le temps d'attente.
        """
        query = """
        WITH match_times AS (
            SELECT created_at,
                   LAG(created_at) OVER (ORDER BY created_at) as prev_created_at
            FROM match_history
            WHERE server_id = $1
            ORDER BY created_at DESC
            LIMIT 100
        )
        SELECT AVG(EXTRACT(EPOCH FROM (created_at - prev_created_at)))::int as avg_interval
        FROM match_times
        WHERE prev_created_at IS NOT NULL;
        """
        try:
            result = await database.fetchval(query, server_id)
            return result or 300  # Default: 5 minutes
        except Exception as e:
            logger.error(f"[Stats] Erreur get_avg_match_interval: {e}")
            return 300

    @staticmethod
    async def remove_entries_batch(entry_ids: List[int], server_id: int) -> int:
        """
        Supprime plusieurs entrées de la queue en une seule requête.
        Retourne le nombre d'entrées supprimées.
        """
        if not entry_ids:
            return 0
        query = """
        DELETE FROM matchmaking_queue
        WHERE id = ANY($1::integer[]) AND server_id = $2
        RETURNING id;
        """
        try:
            rows = await database.fetch(query, entry_ids, server_id)
            count = len(rows)
            logger.info(f"[Queue] Batch suppression: {count} entrées supprimées")
            return count
        except Exception as e:
            logger.error(f"[Queue] Erreur remove_entries_batch: {e}")
            return 0

    @staticmethod
    async def get_match_by_id(match_id: int) -> Optional[Dict]:
        """
        Récupère les détails d'un match par son ID.
        """
        query = """
        SELECT id, server_id, match_code, created_at, voice_channel_id,
               match_quality_score, elo_spread, avg_elo, role_diversity_score,
               total_wait_time_seconds, team_size, langue, region, platform
        FROM match_history
        WHERE id = $1;
        """
        try:
            row = await database.fetchrow(query, match_id)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"[MatchHistory] Erreur get_match_by_id: {e}")
            return None

    @staticmethod
    async def get_server_matchmaking_stats(server_id: int) -> Dict:
        """
        Récupère les statistiques détaillées de matchmaking pour un serveur.
        Inclut le nombre de matchs aujourd'hui, cette semaine, joueurs uniques, etc.
        """
        query = """
        WITH match_stats AS (
            SELECT
                COUNT(*) as total_matches,
                AVG(match_quality_score) as avg_quality_score,
                AVG(total_wait_time_seconds) as avg_wait_time_seconds,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 day') as matches_today,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') as matches_this_week
            FROM match_history
            WHERE server_id = $1
        ),
        player_stats AS (
            SELECT COUNT(DISTINCT mp.discord_member_id) as unique_players
            FROM match_participants mp
            JOIN match_history mh ON mp.match_id = mh.id
            WHERE mh.server_id = $1
        ),
        size_dist AS (
            SELECT team_size, COUNT(*) as count
            FROM match_history
            WHERE server_id = $1
            GROUP BY team_size
        )
        SELECT
            ms.total_matches,
            ms.avg_quality_score,
            ms.avg_wait_time_seconds,
            ms.matches_today,
            ms.matches_this_week,
            ps.unique_players
        FROM match_stats ms, player_stats ps;
        """
        size_query = """
        SELECT team_size, COUNT(*) as count
        FROM match_history
        WHERE server_id = $1
        GROUP BY team_size;
        """
        try:
            row = await database.fetchrow(query, server_id)
            size_rows = await database.fetch(size_query, server_id)

            result = dict(row) if row else {
                'total_matches': 0,
                'avg_quality_score': 0,
                'avg_wait_time_seconds': 0,
                'matches_today': 0,
                'matches_this_week': 0,
                'unique_players': 0
            }

            # Ajouter la distribution par taille
            result['team_size_distribution'] = {
                r['team_size']: r['count'] for r in size_rows
            } if size_rows else {}

            return result
        except Exception as e:
            logger.error(f"[Stats] Erreur get_server_matchmaking_stats: {e}")
            return {
                'total_matches': 0,
                'avg_quality_score': 0,
                'avg_wait_time_seconds': 0,
                'matches_today': 0,
                'matches_this_week': 0,
                'unique_players': 0,
                'team_size_distribution': {}
            }

    @staticmethod
    async def get_leaderboard(server_id: int, category: str = "matches", limit: int = 10) -> List[Dict]:
        """
        Récupère le classement des joueurs selon une catégorie.

        Args:
            server_id: ID du serveur
            category: "matches" ou "wait_time"
            limit: Nombre de joueurs à retourner

        Returns:
            Liste de dictionnaires avec discord_id et la valeur de classement
        """
        if category == "matches":
            query = """
            SELECT discord_id, total_matches, total_wait_time_seconds
            FROM player_matchmaking_stats
            WHERE server_id = $1
            ORDER BY total_matches DESC
            LIMIT $2;
            """
        elif category == "wait_time":
            query = """
            SELECT discord_id, total_matches, total_wait_time_seconds
            FROM player_matchmaking_stats
            WHERE server_id = $1
            ORDER BY total_wait_time_seconds DESC
            LIMIT $2;
            """
        else:
            return []

        try:
            rows = await database.fetch(query, server_id, limit)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[Stats] Erreur get_leaderboard: {e}")
            return []
