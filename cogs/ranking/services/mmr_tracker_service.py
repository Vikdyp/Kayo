import re
from datetime import datetime
import logging

from asyncpg import Record
from utils.database import database
from datetime import date
from typing import Any, Optional, List, Dict, Tuple
from cogs.ranking.services.valorant_service import get_puuid, get_mmr_history, get_stored_mmr_history, RateLimitException

logger = logging.getLogger('tracker_service')

class ValorantService:
    @staticmethod
    async def _get_internal_id(discord_id: int) -> Optional[int]:
        """
        Retourne l'ID interne (user_id) à partir du Discord ID.
        """
        return await database.fetchval(
            "SELECT id FROM user_id WHERE discord_id = $1",
            discord_id
        )

    @staticmethod
    async def enable_tracking(discord_id: int) -> None:
        """
        Active le suivi MMR pour l’utilisateur via son Discord ID.
        """
        internal_id = await ValorantService._get_internal_id(discord_id)
        if not internal_id:
            logger.warning(f"[ValorantService] Aucun utilisateur interne pour discord_id={discord_id}")
            return
        await database.execute(
            "UPDATE valorant_info SET tracking_enabled = TRUE WHERE user_id = $1",
            internal_id
        )
        logger.info(f"[ValorantService] Tracking MMR activé pour user_id={internal_id}")

    @staticmethod
    async def disable_tracking(discord_id: int) -> None:
        """
        Désactive le suivi MMR pour l’utilisateur via son Discord ID.
        """
        internal_id = await ValorantService._get_internal_id(discord_id)
        if not internal_id:
            logger.warning(f"[ValorantService] Aucun utilisateur interne pour discord_id={discord_id}")
            return
        await database.execute(
            "UPDATE valorant_info SET tracking_enabled = FALSE WHERE user_id = $1",
            internal_id
        )
        logger.info(f"[ValorantService] Tracking MMR désactivé pour user_id={internal_id}")

    @staticmethod
    async def get_tracked_players() -> List[Dict[str, int]]:
        """
        Retourne la liste des joueurs (user_id interne et elo) dont le suivi est activé.
        """
        return await database.fetch(
            "SELECT user_id, elo FROM valorant_info WHERE tracking_enabled = TRUE"
        )

    @staticmethod
    async def get_last_elo(user_id: int) -> Optional[int]:
        """
        Récupère le dernier elo historisé pour la clé interne user_id.
        """
        row = await database.fetchrow(
            """
            SELECT elo
              FROM valorant_elo_history
             WHERE user_id = $1
             ORDER BY recorded_at DESC
             LIMIT 1
            """,
            user_id
        )
        return row["elo"] if row else None

    @staticmethod
    async def record_elo(user_id: int, new_elo: int, is_win: bool) -> None:
        """
        Insère une nouvelle entrée dans l’historique MMR.
        """
        await database.execute(
            """
            INSERT INTO valorant_elo_history (user_id, elo, is_win)
            VALUES ($1, $2, $3)
            """,
            user_id, new_elo, is_win
        )
        logger.info(
            f"[ValorantService] Historique MMR ajouté pour user_id={user_id}: "
            f"elo={new_elo}, is_win={is_win}"
        )

    @staticmethod
    async def get_stats_today(discord_id: int) -> Dict[str, float]:
        """
        Calcule pour aujourd’hui (basé sur UTC) :
          - total de changements
          - moyenne elo sur wins
          - moyenne elo sur losses
          - dernier elo enregistré
        """
        internal_id = await ValorantService._get_internal_id(discord_id)
        if not internal_id:
            return {"total": 0, "avg_win": 0.0, "avg_loss": 0.0, "last_elo": 0}

        today = date.today()
        row = await database.fetchrow(
            """
            SELECT
              COUNT(*) FILTER (WHERE recorded_at::date = $2)     AS total,
              AVG(elo)   FILTER (WHERE is_win AND recorded_at::date = $2) AS avg_win,
              AVG(elo)   FILTER (WHERE NOT is_win AND recorded_at::date = $2) AS avg_loss,
              MAX(recorded_at) FILTER (WHERE recorded_at::date = $2) AS last_time
            FROM valorant_elo_history
            WHERE user_id = $1
            """,
            internal_id, today
        )
        if not row:
            return {"total": 0, "avg_win": 0.0, "avg_loss": 0.0, "last_elo": 0}

        total    = row["total"]    or 0
        avg_win  = float(row["avg_win"]  or 0)
        avg_loss = float(row["avg_loss"] or 0)
        last_elo = 0

        last_time = row.get("last_time")
        if last_time:
            last_row = await database.fetchrow(
                "SELECT elo FROM valorant_elo_history WHERE user_id = $1 AND recorded_at = $2",
                internal_id, last_time
            )
            last_elo = last_row["elo"] if last_row else 0

        return {
            "total":    total,
            "avg_win":  avg_win,
            "avg_loss": avg_loss,
            "last_elo": last_elo
        }

    @staticmethod
    async def get_history(
        discord_id: int,
        season: Optional[int] = None,
        act: Optional[int]    = None
    ) -> List[Dict[str, Any]]:
        """
        Récupère l'historique (season, act, date, elo),
        filtré sur une partition si season+act fournis.
        """
        internal_id = await ValorantService._get_internal_id(discord_id)
        if not internal_id:
            return []

        sql = (
            "SELECT season, act, recorded_at, elo "
            "  FROM valorant_elo_history_parent "
            " WHERE user_id = $1"
        )
        params: List[Any] = [internal_id]

        if season is not None and act is not None:
            sql += " AND season = $2 AND act = $3"
            params += [season, act]

        sql += " ORDER BY recorded_at"
        return await database.fetch(sql, *params)
    
    async def ensure_partitions(season_num: int, act_num: int) -> None:
        """
        Crée la partition season_{season_num} et la sous-partition act_{act_num}
        si elles n'existent pas déjà.
        """
        season_table = f"valorant_elo_history_season_{season_num}"
        # Partition de saison
        await database.execute(f"""
            CREATE TABLE IF NOT EXISTS {season_table}
            PARTITION OF valorant_elo_history_parent
            FOR VALUES IN ({season_num})
            PARTITION BY LIST (act);
        """)
        # Sous-partition d'act
        act_table = f"{season_table}_act_{act_num}"
        await database.execute(f"""
            CREATE TABLE IF NOT EXISTS {act_table}
            PARTITION OF {season_table}
            FOR VALUES IN ({act_num});
        """)


    async def insert_history_entry(user_id: int, entry: Dict[str, Any]) -> None:
        """
        Insère une entrée d'historique MMR dans la bonne partition, sans duplication.
        """
        # 1) Lecture des champs essentiels
        recorded_at = entry.get("date")
        elo         = entry.get("elo")
        rr          = entry.get("rr", 0)
        is_win      = rr >= 0

        # 2) Extraction de season.short (ex. "e1a1")
        season_info  = entry.get("season") or {}
        season_short = season_info.get("short", "")
        if not season_short:
            logger.warning(
                f"[insert_history_entry] Pas de season.short pour user_id={user_id}, date={recorded_at}. Ignoré."
            )
            return

        m = re.match(r"e(\d+)a(\d+)", season_short)
        if not m:
            logger.warning(
                f"[insert_history_entry] Format invalide pour season.short='{season_short}' "
                f"(user_id={user_id}, date={recorded_at}). Ignoré."
            )
            return
        season_num, act_num = map(int, m.groups())

        # 3) Création des partitions si nécessaire
        await ValorantService.ensure_partitions(season_num, act_num)

        raw = entry.get("date")
        if not raw:
            logger.warning(f"[insert_history_entry] Pas de date pour user_id={user_id}, entry={entry!r}")
            return
        
        recorded_at = datetime.fromisoformat(raw.replace('Z', '+00:00'))
         
        # 4) Insertion idempotente
        await database.execute(
            """
            INSERT INTO valorant_elo_history_parent
            (season, act, user_id, recorded_at, elo, is_win)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (season, act, user_id, recorded_at) DO NOTHING
            """,
            season_num, act_num, user_id, recorded_at, elo, is_win
        )
        logger.debug(
            f"[insert_history_entry] Inséré user_id={user_id} season={season_num} act={act_num} "
            f"date={recorded_at} elo={elo}"
        )
        
    @staticmethod
    async def fetch_full_history(discord_id: int) -> None:
        logger.info(f"[fetch_full_history] Démarrage pour discord_id={discord_id}")

        # 1) ID interne
        internal_id = await ValorantService._get_internal_id(discord_id)
        if not internal_id:
            logger.warning(f"[fetch_full_history] Aucun ID interne pour discord_id={discord_id}")
            return

        # 2) Lecture valorant_info
        row = await database.fetchrow(
            "SELECT pseudo, tag, region, puuid FROM valorant_info WHERE user_id = $1",
            internal_id
        )
        if not row:
            logger.warning(f"[fetch_full_history] Pas de valorant_info pour user_id={internal_id}")
            return
        pseudo, tag, region, puuid = row["pseudo"], row["tag"], row["region"], row["puuid"]

        # 3) Récupération du PUUID si manquant
        if not puuid:
            try:
                result = await get_puuid(pseudo, tag)
            except RateLimitException as e:
                logger.error(f"[fetch_full_history] RateLimit sur get_puuid: {e}")
                return
            if not result:
                logger.warning(f"[fetch_full_history] Profil introuvable pour {pseudo}#{tag}")
                return
            _, region, puuid = result
            await database.execute(
                "UPDATE valorant_info SET puuid = $1 WHERE user_id = $2",
                puuid, internal_id
            )
            logger.info(f"[fetch_full_history] PUUID mis à jour en BDD: {puuid}")

        # 4) Tentative d'historique stocké
        logger.info(f"[fetch_full_history] Appel get_stored_mmr_history pour puuid={puuid}")
        try:
            history = await get_stored_mmr_history(region, puuid)
        except RateLimitException as e:
            logger.error(f"[fetch_full_history] RateLimit sur stored history: {e}")
            return

        # 5) Fallback vers live history si vide
        if not history:
            logger.info(f"[fetch_full_history] Aucun historique stocké pour {puuid}, fallback sur live")
            try:
                live = await get_mmr_history(region, puuid)
            except RateLimitException as e:
                logger.error(f"[fetch_full_history] RateLimit sur live history: {e}")
                return

            if not live:
                logger.warning(f"[fetch_full_history] Pas d'historique même en live pour {puuid}")
                return

            # On reconstruit la liste 'history' avec le format attendu par insert_history_entry
            history = [
                {
                    "date":   e["date"],
                    "season": e["season"],
                    "elo":    e["elo"],
                    "rr":     e.get("rr", 0)
                }
                for e in live
            ]

        # 6) Insertion des entrées
        logger.info(f"[fetch_full_history] Insertion de {len(history)} entrées en BDD")
        for entry in history:
            await ValorantService.insert_history_entry(internal_id, entry)

        logger.info(f"[fetch_full_history] Terminé pour user_id={internal_id}")

    @staticmethod
    async def get_partitions(discord_id: int) -> List[Tuple[int, int]]:
        """
        Retourne la liste des (season, act) pour lesquelles user_id a au moins une entrée.
        """
        internal_id = await ValorantService._get_internal_id(discord_id)
        if not internal_id:
            return []
        rows = await database.fetch(
            """
            SELECT DISTINCT season, act
              FROM valorant_elo_history_parent
             WHERE user_id = $1
             ORDER BY season DESC, act DESC
            """,
            internal_id
        )
        return [(r["season"], r["act"]) for r in rows]
    
    @staticmethod
    async def fetch_current_partition() -> Tuple[int, int]:
        import re
        from cogs.ranking.services.valorant_service import get_mmr_history
        from utils.database import database

        # a) Choisir un joueur tracké au hasard (ou le premier)
        row = await database.fetchrow(
            "SELECT region, puuid FROM valorant_info WHERE tracking_enabled = TRUE LIMIT 1"
        )
        if not row or not row["puuid"]:
            # fallback sur la dernière partition connue en base
            row = await database.fetchrow("""
                SELECT season, act
                  FROM valorant_elo_history_parent
                 GROUP BY season, act
                 ORDER BY season DESC, act DESC
                 LIMIT 1
            """)
            return row["season"], row["act"]

        region, puuid = row["region"], row["puuid"]

        # b) Appel à l'API pour n'avoir QUE le dernier historique (v2)
        history = await get_mmr_history(region, puuid)
        if not history:
            # même fallback si l’API ne renvoie rien
            row = await database.fetchrow("""
                SELECT season, act
                  FROM valorant_elo_history_parent
                 GROUP BY season, act
                 ORDER BY season DESC, act DESC
                 LIMIT 1
            """)
            return row["season"], row["act"]

        # c) On parse "season.short" (ex. "e10a3")
        short = history[0]["season"]["short"]
        m = re.match(r"e(\d+)a(\d+)", short, re.I)
        if not m:
            raise ValueError(f"Impossible de parser season.short='{short}'")
        return map(int, m.groups())

    @staticmethod
    async def get_last_history_row(user_id: int) -> Optional[Record]:
        return await database.fetchrow("""
            SELECT season, act, elo
            FROM valorant_elo_history_parent
            WHERE user_id = $1
            ORDER BY recorded_at DESC
            LIMIT 1
        """, user_id)
