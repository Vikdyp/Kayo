# cogs/accueil/services/accueil_service.py
"""
Service métier pour le domaine accueil.
- Logique métier uniquement
- Validation des entrées
- Appelle les services DB
- AUCUN SQL ici
"""

import io
import logging
from datetime import date, timedelta, timezone
from dataclasses import dataclass
from typing import Optional

from matplotlib import ticker
import matplotlib.pyplot as plt

from database.services.member_stats_service import MemberStatsService
from database.services.persistent_messages_service import (
    PersistentMessagesService,
    PersistentMessageInfo,
)
from database.services.guild_channels_service import ChannelConfigurationService

from cogs.accueil.constants import (
    ACCUEIL_STATS_EMBED,
    ACCUEIL_STATS_THREAD,
    CHANNEL_WELCOME,
    CHANNEL_RULES,
    CHANNEL_INTRODUCTIONS,
    CHANNEL_STATS_EMBED,
    _CHANNEL_STATS_EMBED_ALIASES,
)

logger = logging.getLogger(__name__)


# ============================================================
# MODÈLES DE DOMAINE
# ============================================================


@dataclass(frozen=True)
class WelcomeChannels:
    """Channels nécessaires pour le message de bienvenue."""

    welcome_channel_id: Optional[int]
    rules_channel_id: Optional[int]
    introductions_channel_id: Optional[int]


@dataclass(frozen=True)
class StatsEmbedData:
    """Données pour construire l'embed de statistiques."""

    current_members: int
    join_count: int
    leave_count: int
    ratio: str
    period_label: str


@dataclass(frozen=True)
class EvolutionDataPoint:
    """Point de données pour le graphique d'évolution."""

    date: date
    join_count: int
    leave_count: int
    net_change: int


# ============================================================
# SERVICE ACCUEIL
# ============================================================


class AccueilService:
    """
    Service métier pour les fonctionnalités d'accueil.
    Combine logique métier et orchestration des services DB.
    """

    def __init__(
        self,
        member_stats_svc: MemberStatsService,
        persistent_msg_svc: PersistentMessagesService,
        channel_config_svc: ChannelConfigurationService,
    ):
        self._member_stats = member_stats_svc
        self._persistent_msg = persistent_msg_svc
        self._channel_config = channel_config_svc

    # --------------------------------------------------
    # CHANNELS
    # --------------------------------------------------

    async def get_welcome_channels(self, guild_id: int) -> WelcomeChannels:
        """Récupère tous les channels nécessaires pour le message de bienvenue."""
        all_channels = await self._channel_config.get_all(guild_id)

        return WelcomeChannels(
            welcome_channel_id=all_channels.get(CHANNEL_WELCOME),
            rules_channel_id=all_channels.get(CHANNEL_RULES),
            introductions_channel_id=all_channels.get(CHANNEL_INTRODUCTIONS),
        )

    async def get_stats_channel_id(self, guild_id: int) -> Optional[int]:
        """Récupère l'ID du channel pour l'embed de stats."""
        all_channels = await self._channel_config.get_all(guild_id)

        # Clé canonique d'abord
        if CHANNEL_STATS_EMBED in all_channels:
            return all_channels[CHANNEL_STATS_EMBED]

        # Alias pour compatibilité
        for alias in _CHANNEL_STATS_EMBED_ALIASES:
            if alias in all_channels:
                return all_channels[alias]

        return None

    # --------------------------------------------------
    # ÉVÉNEMENTS MEMBRES
    # --------------------------------------------------

    async def on_member_join(self, guild_id: int, guild_name: str) -> None:
        """Enregistre un événement de join."""
        await self._member_stats.record_join(guild_id, guild_name)
        logger.debug(f"Join enregistré pour guild {guild_id}")

    async def on_member_leave(self, guild_id: int, guild_name: str) -> None:
        """Enregistre un événement de départ."""
        await self._member_stats.record_leave(guild_id, guild_name)
        logger.debug(f"Leave enregistré pour guild {guild_id}")

    # --------------------------------------------------
    # STATISTIQUES
    # --------------------------------------------------

    @staticmethod
    def _period_to_days(period: str) -> tuple[Optional[int], str]:
        """Convertit une période en nombre de jours et label."""
        mapping = {
            "7j": (7, "7 jours"),
            "1m": (30, "1 mois"),
            "1a": (365, "1 an"),
            "total": (None, "Total"),
            "default": (30, "30 jours"),
        }
        return mapping.get(period, (30, "30 jours"))

    async def get_stats_embed_data(
        self,
        guild_id: int,
        period: str,
        current_member_count: int,
    ) -> StatsEmbedData:
        """Prépare les données pour l'embed de statistiques."""
        days, period_label = self._period_to_days(period)
        stats = await self._member_stats.get_period_stats(guild_id, days)

        return StatsEmbedData(
            current_members=current_member_count,
            join_count=stats.join_count,
            leave_count=stats.leave_count,
            ratio=stats.ratio,
            period_label=period_label,
        )

    async def get_evolution_data(
        self,
        guild_id: int,
        period: str,
    ) -> list[EvolutionDataPoint]:
        """
        Récupère et prépare les données d'évolution pour le graphique.
        Interpole les jours manquants.
        """
        days, _ = self._period_to_days(period)
        raw_data = await self._member_stats.get_evolution_data(guild_id, days)

        # Convertir en dict pour accès rapide
        data_by_date = {row.date: row for row in raw_data}

        # Déterminer la plage de dates
        from datetime import datetime

        today = datetime.now(timezone.utc).date()

        if days is not None:
            start_date = today - timedelta(days=days)
        elif raw_data:
            start_date = min(row.date for row in raw_data)
        else:
            start_date = today

        # Remplir les jours manquants
        result = []
        current_date = start_date
        while current_date <= today:
            if current_date in data_by_date:
                row = data_by_date[current_date]
                result.append(
                    EvolutionDataPoint(
                        date=current_date,
                        join_count=row.join_count,
                        leave_count=row.leave_count,
                        net_change=row.join_count - row.leave_count,
                    )
                )
            else:
                result.append(
                    EvolutionDataPoint(
                        date=current_date,
                        join_count=0,
                        leave_count=0,
                        net_change=0,
                    )
                )
            current_date += timedelta(days=1)

        return result

    # --------------------------------------------------
    # GRAPHIQUE
    # --------------------------------------------------

    async def generate_member_evolution_graph(
        self,
        guild_id: int,
        period: str,
        current_member_count: int,
    ) -> Optional[io.BytesIO]:
        """
        Génère un graphique de l'évolution des membres sur la période donnée.

        Returns:
            io.BytesIO contenant l'image PNG, ou None si pas de données.
        """
        evolution_data = await self.get_evolution_data(guild_id, period)

        if not evolution_data:
            logger.info("Aucune donnée d'évolution trouvée pour la période demandée.")
            return None

        dates = [dp.date.strftime("%d-%m") for dp in evolution_data]
        net_changes = [dp.net_change for dp in evolution_data]

        # Calcul cumulatif : on part du nombre actuel et on remonte
        cumulative = [0] * len(net_changes)
        cumulative[-1] = current_member_count
        for i in range(len(net_changes) - 2, -1, -1):
            cumulative[i] = cumulative[i + 1] - net_changes[i + 1]

        # Créer le graphique
        plt.figure(figsize=(10, 5))
        plt.plot(range(len(dates)), cumulative, marker="o", linestyle="-", color="#2ecc71", markersize=4)
        plt.fill_between(range(len(dates)), cumulative, alpha=0.3, color="#2ecc71")
        plt.title("Évolution du nombre de membres", fontsize=14, fontweight="bold")
        plt.xlabel("Date", fontsize=10)
        plt.ylabel("Nombre de membres", fontsize=10)

        ax = plt.gca()
        ax.set_facecolor("#f8f9fa")
        plt.gcf().set_facecolor("#ffffff")

        if len(dates) > 15:
            step = max(1, len(dates) // 10)
            tick_positions = list(range(0, len(dates), step))
            if len(dates) - 1 not in tick_positions:
                tick_positions.append(len(dates) - 1)
            ax.xaxis.set_major_locator(ticker.FixedLocator(tick_positions))
            ax.set_xticklabels([dates[i] for i in tick_positions], rotation=45, ha="right")
        else:
            ax.xaxis.set_major_locator(ticker.FixedLocator(range(len(dates))))
            ax.set_xticklabels(dates, rotation=45, ha="right")

        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=100)
        buf.seek(0)
        plt.close()
        return buf

    # --------------------------------------------------
    # MESSAGES PERSISTANTS
    # --------------------------------------------------

    async def get_stats_embed_message(
        self,
        guild_id: int,
    ) -> Optional[PersistentMessageInfo]:
        """Récupère l'info du message d'embed de stats."""
        return await self._persistent_msg.get(guild_id, ACCUEIL_STATS_EMBED)

    async def save_stats_embed_message(
        self,
        guild_id: int,
        guild_name: str,
        channel_id: int,
        message_id: int,
    ) -> None:
        """Sauvegarde le message d'embed de stats."""
        await self._persistent_msg.save(
            guild_id, guild_name, ACCUEIL_STATS_EMBED, channel_id, message_id
        )
        logger.info(f"Stats embed sauvegardé pour guild {guild_id}")

    async def get_stats_thread(
        self,
        guild_id: int,
    ) -> Optional[PersistentMessageInfo]:
        """Récupère l'info du thread de notifications."""
        return await self._persistent_msg.get(guild_id, ACCUEIL_STATS_THREAD)

    async def save_stats_thread(
        self,
        guild_id: int,
        guild_name: str,
        thread_id: int,
        first_message_id: int,
    ) -> None:
        """
        Sauvegarde le thread de notifications.
        channel_id = thread_id, message_id = premier message du thread.
        """
        await self._persistent_msg.save(
            guild_id, guild_name, ACCUEIL_STATS_THREAD, thread_id, first_message_id
        )
        logger.info(f"Stats thread sauvegardé pour guild {guild_id}")
