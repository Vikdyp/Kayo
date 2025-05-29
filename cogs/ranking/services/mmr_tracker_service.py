import logging
from utils.database import database
from datetime import date
from typing import Optional, List, Dict

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
    async def get_history(discord_id: int) -> List[Dict[str, any]]:
        """
        Récupère l'historique complet (dates et elo) pour générer le graphique.
        """
        internal_id = await ValorantService._get_internal_id(discord_id)
        if not internal_id:
            return []
        return await database.fetch(
            "SELECT recorded_at, elo FROM valorant_elo_history "
            "WHERE user_id = $1 ORDER BY recorded_at",
            internal_id
        )
