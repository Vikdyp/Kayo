# cogs/voice_management/services/match_service.py
"""
Service de gestion du cycle de vie des matchs.
Gère la création des matchs, l'envoi des feedbacks automatiques, etc.
"""

import asyncio
import logging
import random
import string
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

import discord

from .five_stack_service import MatchmakingService

logger = logging.getLogger(__name__)

# Délai avant d'envoyer la demande de feedback (en secondes)
FEEDBACK_DELAY_SECONDS = 30 * 60  # 30 minutes


def generate_match_code(length: int = 8) -> str:
    """Génère un code de match unique."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


class MatchService:
    """
    Service pour gérer le cycle de vie des matchs formés.

    Responsabilités:
    - Créer un match dans la base après formation
    - Programmer l'envoi des demandes de feedback
    - Mettre à jour les statistiques des joueurs
    """

    # Dictionnaire des tâches de feedback en cours {match_id: asyncio.Task}
    _pending_feedback_tasks: Dict[int, asyncio.Task] = {}
    _bot: Optional[discord.Client] = None

    @classmethod
    def set_bot(cls, bot: discord.Client) -> None:
        """Configure l'instance du bot pour l'envoi de DMs."""
        cls._bot = bot

    @classmethod
    async def create_match_from_queue(
        cls,
        server_id: int,
        blocks: List[Dict[str, Any]],
        team_size: int,
        quality_score: float,
        elo_spread: int,
        avg_elo: int,
        voice_channel_id: Optional[int] = None,
        langue: Optional[str] = None,
        region: Optional[str] = None,
        platform: Optional[str] = None
    ) -> Optional[int]:
        """
        Crée un match à partir des blocs de queue sélectionnés.

        Args:
            server_id: ID du serveur
            blocks: Blocs de queue formant le match
            team_size: Taille de l'équipe
            quality_score: Score de qualité du match
            elo_spread: Écart ELO entre les joueurs
            avg_elo: ELO moyen du match
            voice_channel_id: ID du salon vocal créé
            langue: Langue commune
            region: Région commune
            platform: Plateforme commune

        Returns:
            ID du match créé ou None si erreur
        """
        match_code = generate_match_code()

        # Calculer le temps d'attente total
        now = datetime.now(timezone.utc)
        total_wait_time = 0
        participants_data = []

        for block in blocks:
            # Récupérer les infos de chaque participant
            entry_type = block.get('entry_type', 1)
            timestamp = block.get('timestamp')

            if timestamp:
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                wait_seconds = int((now - timestamp).total_seconds())
            else:
                wait_seconds = 0

            total_wait_time += wait_seconds

            # Récupérer les IDs des membres
            team_member_ids = block.get('team_member_ids', [])
            if team_member_ids:
                for member_id in team_member_ids:
                    participants_data.append({
                        'discord_member_id': member_id,
                        'elo_at_match': block.get('elo'),
                        'roles_selected': block.get('roles', []),
                        'entry_type': entry_type,
                        'wait_time_seconds': wait_seconds
                    })
            else:
                participants_data.append({
                    'discord_member_id': block['discord_member_id'],
                    'elo_at_match': block.get('elo'),
                    'roles_selected': block.get('roles', []),
                    'entry_type': entry_type,
                    'wait_time_seconds': wait_seconds
                })

        # Calculer la diversité des rôles
        all_roles = []
        for block in blocks:
            all_roles.extend(block.get('roles', []))
        meaningful_roles = [r for r in all_roles if r.lower() != 'fill']
        role_diversity = len(set(meaningful_roles)) / max(len(meaningful_roles), 1) if meaningful_roles else 0.0

        # Créer le match dans la base
        match_id = await MatchmakingService.create_match_history(
            server_id=server_id,
            match_code=match_code,
            voice_channel_id=voice_channel_id,
            match_quality_score=quality_score,
            elo_spread=elo_spread,
            avg_elo=avg_elo,
            role_diversity_score=role_diversity,
            total_wait_time_seconds=total_wait_time,
            team_size=team_size,
            langue=langue,
            region=region,
            platform=platform
        )

        if not match_id:
            logger.error(f"Échec création match_history pour {match_code}")
            return None

        # Ajouter les participants
        for participant in participants_data:
            await MatchmakingService.add_match_participant(
                match_id=match_id,
                discord_member_id=participant['discord_member_id'],
                elo_at_match=participant['elo_at_match'],
                roles_selected=participant['roles_selected'],
                entry_type=participant['entry_type'],
                wait_time_seconds=participant['wait_time_seconds']
            )

            # Mettre à jour les stats du joueur
            is_solo = participant['entry_type'] == 1
            await MatchmakingService.update_player_stats(
                discord_id=participant['discord_member_id'],
                server_id=server_id,
                wait_time_seconds=participant['wait_time_seconds'],
                is_solo=is_solo,
                roles=participant['roles_selected']
            )

        logger.info(
            f"Match {match_code} (ID: {match_id}) créé avec {len(participants_data)} participants, "
            f"qualité={quality_score:.2f}, ELO spread={elo_spread}"
        )

        # Programmer l'envoi du feedback
        cls._schedule_feedback_request(match_id, match_code, team_size, participants_data)

        return match_id

    @classmethod
    def _schedule_feedback_request(
        cls,
        match_id: int,
        match_code: str,
        team_size: int,
        participants: List[Dict]
    ) -> None:
        """
        Programme l'envoi des demandes de feedback après le délai configuré.
        """
        if cls._bot is None:
            logger.warning("Bot non configuré pour MatchService, feedback non programmé")
            return

        async def send_feedback_after_delay():
            try:
                await asyncio.sleep(FEEDBACK_DELAY_SECONDS)
                await cls._send_feedback_requests(match_id, match_code, team_size, participants)
            except asyncio.CancelledError:
                logger.info(f"Tâche de feedback annulée pour match {match_id}")
            except Exception as e:
                logger.error(f"Erreur dans la tâche de feedback pour match {match_id}: {e}")
            finally:
                cls._pending_feedback_tasks.pop(match_id, None)

        task = asyncio.create_task(send_feedback_after_delay())
        cls._pending_feedback_tasks[match_id] = task
        logger.debug(f"Feedback programmé pour match {match_id} dans {FEEDBACK_DELAY_SECONDS}s")

    @classmethod
    async def _send_feedback_requests(
        cls,
        match_id: int,
        match_code: str,
        team_size: int,
        participants: List[Dict]
    ) -> None:
        """
        Envoie les demandes de feedback à tous les participants.
        """
        from ..views.feedback_views import MatchFeedbackView

        if cls._bot is None:
            return

        # Créer l'embed et la vue
        embed = MatchFeedbackView.create_feedback_embed(match_code, team_size)

        sent_count = 0
        failed_count = 0

        for participant in participants:
            member_id = participant['discord_member_id']

            try:
                user = await cls._bot.fetch_user(member_id)
                if user:
                    view = MatchFeedbackView(match_id, match_code)
                    await user.send(embed=embed, view=view)
                    sent_count += 1
                    logger.debug(f"Feedback envoyé à {member_id} pour match {match_id}")
            except discord.Forbidden:
                logger.warning(f"DMs désactivés pour {member_id}, feedback non envoyé")
                failed_count += 1
            except discord.HTTPException as e:
                logger.warning(f"Erreur HTTP envoi feedback à {member_id}: {e}")
                failed_count += 1
            except Exception as e:
                logger.error(f"Erreur inattendue envoi feedback à {member_id}: {e}")
                failed_count += 1

        logger.info(
            f"Feedback pour match {match_id}: {sent_count} envoyés, {failed_count} échecs"
        )

    @classmethod
    def cancel_pending_feedback(cls, match_id: int) -> bool:
        """
        Annule une demande de feedback en attente.

        Returns:
            True si une tâche a été annulée
        """
        task = cls._pending_feedback_tasks.pop(match_id, None)
        if task:
            task.cancel()
            return True
        return False

    @classmethod
    async def get_match_details(cls, match_id: int) -> Optional[Dict[str, Any]]:
        """
        Récupère les détails complets d'un match.
        """
        return await MatchmakingService.get_match_by_id(match_id)

    @classmethod
    async def cleanup_old_feedback_tasks(cls) -> int:
        """
        Nettoie les tâches de feedback qui auraient dû être terminées.

        Returns:
            Nombre de tâches nettoyées
        """
        cleaned = 0
        for match_id, task in list(cls._pending_feedback_tasks.items()):
            if task.done():
                cls._pending_feedback_tasks.pop(match_id, None)
                cleaned += 1
        return cleaned
