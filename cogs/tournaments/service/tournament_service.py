import logging
from datetime import datetime
from typing import Optional
from utils.database import database  # Module d'accès à la BDD

logger = logging.getLogger("tournament.service")

async def create_tournament(tournament_name: str, max_teams: int, registration_start: datetime, registration_end: datetime, tournament_date: datetime) -> Optional[int]:
    """
    Crée un tournoi dans la BDD et retourne son ID.
    Avant insertion, vérifie qu'il n'existe pas déjà un tournoi actif.
    Le tournoi est créé avec le status 'active'.
    """
    # Vérifier s'il existe déjà un tournoi actif
    query_check = "SELECT id FROM tournaments WHERE status = 'active';"
    try:
        existing = await database.fetchval(query_check)
        logger.debug(f"Résultat vérification tournoi actif: {existing}")
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du tournoi actif: {e}")
        existing = None

    if existing:
        logger.error("Un tournoi actif existe déjà.")
        return None

    query = """
    INSERT INTO tournaments (tournament_name, max_teams, registration_start, registration_end, tournament_date, status)
    VALUES ($1, $2, $3, $4, $5, 'active')
    RETURNING id;
    """
    try:
        tournament_id = await database.fetchval(query, tournament_name, max_teams, registration_start, registration_end, tournament_date)
        logger.info(f"Tournoi créé avec ID: {tournament_id}")
        return tournament_id
    except Exception as e:
        logger.error(f"Erreur lors de la création du tournoi: {e}")
        return None

async def get_active_tournament() -> Optional[int]:
    """
    Retourne l'ID du tournoi actif s'il existe, sinon None.
    """
    query = "SELECT id FROM tournaments WHERE status = 'active';"
    try:
        active_id = await database.fetchval(query)
        logger.debug(f"Tournoi actif trouvé: {active_id}")
        return active_id
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du tournoi actif: {e}")
        return None

async def persist_registration_message(channel_id: int, message_id: int, tournament_id: int, guild_id: int) -> None:
    """
    Stocke le message contenant le bouton d'inscription dans la table persistent_messages.
    """
    query = """
    INSERT INTO persistent_messages (channel_id, message_id, message_type, guild_id, requester_id)
    VALUES ($1, $2, 'tournament_registration', $3, NULL)
    ON CONFLICT (guild_id, message_type)
    DO UPDATE SET channel_id = $1, message_id = $2, requester_id = NULL, created_at = NOW();
    """
    try:
        await database.execute(query, channel_id, message_id, guild_id)
        logger.info("Message d'inscription persistant enregistré.")
    except Exception as e:
        logger.error(f"Erreur lors de la persistance du message: {e}")

async def register_team(tournament_id: int, team_info: dict) -> Optional[int]:
    """
    Enregistre une équipe dans la BDD et retourne son ID.
    """
    query = """
    INSERT INTO team_registrations (tournament_id, team_name, players, substitutes, coach)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING id;
    """
    try:
        team_id = await database.fetchval(query, tournament_id, team_info["team_name"], team_info["players"], team_info["substitutes"], team_info["coach"])
        logger.info(f"Équipe enregistrée avec ID: {team_id}")
        return team_id
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement de l'équipe: {e}")
        return None

async def create_forum_post(tournament_id: int, team_info: dict) -> None:
    """
    Crée un post dans le forum avec les informations de l'équipe (sans Discord IDs ni pseudos Valorant).
    Le forum ID est fixé à 1236736105106116668.
    """
    forum_channel_id = 1236736105106116668
    content = f"**Équipe:** {team_info['team_name']}\n"
    content += "**Joueurs:**\n"
    for i in range(1, 6):
        content += f"- Joueur {i}: en attente\n"
    if team_info["substitutes"]:
        content += "**Remplaçants:**\n"
        for i in range(1, len(team_info["substitutes"]) + 1):
            content += f"- Remplaçant {i}: en attente\n"
    if team_info["coach"]:
        content += "**Coach:** en attente\n"
    
    try:
        # La méthode pour obtenir le channel dépend de votre configuration.
        # Assurez-vous d'avoir accès à l'objet bot via votre environnement.
        from discord.ext import commands
        bot = commands.Bot(command_prefix="!")
        channel = bot.get_channel(forum_channel_id)
        if channel:
            await channel.send(content)
            logger.info("Post créé dans le forum.")
        else:
            logger.error("Channel forum introuvable.")
    except Exception as e:
        logger.error(f"Erreur lors de la création du post dans le forum: {e}")

async def close_tournament() -> bool:
    """
    Ferme le tournoi actif en mettant à jour son status en 'closed'
    et supprime toutes les inscriptions d'équipe dans la BDD.
    Vous pouvez également ajouter ici la logique pour supprimer ou archiver les posts du forum.
    """
    try:
        # Mettre à jour le tournoi actif en 'closed'
        query_update = "UPDATE tournaments SET status = 'closed' WHERE status = 'active';"
        await database.execute(query_update)
        logger.info("Tournoi fermé (status mis à 'closed').")
        # Supprimer toutes les inscriptions d'équipe
        query_delete = "DELETE FROM team_registrations;"
        await database.execute(query_delete)
        logger.info("Toutes les inscriptions d'équipe supprimées.")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la fermeture du tournoi: {e}")
        return False
