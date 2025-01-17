import asyncio
import logging
from datetime import datetime

# Importez la classe ScrimService depuis votre module
from cogs.scrims.service.scrims_services import ScrimService
from utils.database import database  # Le module gérant la connexion asynchrone à la BDD

# Configuration de logging au niveau DEBUG pour bien voir toutes les étapes
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("test_modal")

async def test_modal_simulation():
    logger.info("=== Début du test de simulation du modal ===")

    # Instanciation de la classe ScrimService
    service = ScrimService()

    # Simuler l'identifiant Discord du créateur (remplacez par une valeur existante dans la table user_id)
    discord_id = 812367371570118756
    logger.debug("Discord ID simulé : %s", discord_id)

    # Récupération de l'ID interne utilisateur depuis la table user_id
    internal_id = await service.get_internal_user_id(discord_id)
    if internal_id is None:
        logger.error("L'utilisateur avec discord_id %s n'est pas enregistré dans la BDD.", discord_id)
        return
    logger.info("ID interne récupéré pour discord_id %s : %s", discord_id, internal_id)

    # Simuler l'ID Discord du serveur, que vous devez convertir en ID interne
    discord_guild_id = 1120105855556272219  # Remplacez par un ID existant dans serveur_id (colonne guild_id)
    internal_guild_id = await service.get_internal_server_id(discord_guild_id)
    if internal_guild_id is None:
        logger.error("Aucun serveur interne trouvé pour discord_guild_id %s.", discord_guild_id)
        return
    logger.info("ID interne du serveur récupéré pour discord_guild_id %s : %s", discord_guild_id, internal_guild_id)

    # Préparation des données pour créer un scrim
    scrim_datetime = datetime.now()  # Pour le test, on utilise la date actuelle
    map_name = "TestMap"
    rang = "TestRang"
    autre = "Aucune précision"
    initial_participants = [internal_id]  # On passe l'ID interne récupéré
    message_id = 1329837428508327948  # Valeur provisoire
    channel_id = 1236430983201427476  # Simuler un channel ID existant
    guild_id = internal_guild_id  # On utilise l'ID interne du serveur

    logger.debug(
        "Création d'un scrim avec: datetime=%s, map=%s, rang=%s, autre=%s, participants=%s, message_id=%s, channel_id=%s, guild_id=%s",
        scrim_datetime, map_name, rang, autre, initial_participants, message_id, channel_id, guild_id
    )

    # Appel à la fonction de création de scrim
    scrim_id = await service.create_scrim(
        scrim_datetime=scrim_datetime,
        map_name=map_name,
        rang=rang,
        autre=autre,
        initial_participants=initial_participants,
        message_id=message_id,
        channel_id=channel_id,
        guild_id=guild_id
    )

    if scrim_id is None:
        logger.error("Échec de la création du scrim. Vérifiez les logs et la structure de la table scrims.")
        return
    logger.info("Scrim créé avec id : %s", scrim_id)

    # Récupération et affichage des informations du scrim créé
    scrim_info = await service.get_scrim_info(scrim_id)
    if scrim_info is None:
        logger.error("Impossible de récupérer les informations du scrim id : %s", scrim_id)
    else:
        logger.debug("Informations récupérées pour le scrim id %s : %s", scrim_id, scrim_info)

    # Mise à jour simulée du message (exemple : l'ID du message envoyé sur Discord)
    test_message_id = 987654321
    logger.debug("Mise à jour du message pour scrim id %s avec le message_id : %s", scrim_id, test_message_id)
    try:
        await service.update_scrim_message(scrim_id, test_message_id)
        logger.info("Le message du scrim id %s a été mis à jour avec le message id %s.", scrim_id, test_message_id)
    except Exception as e:
        logger.exception("Erreur lors de la mise à jour du message du scrim.")

    # Insertion d'un message persistant (champ requester_id sera NULL)
    logger.debug("Insertion du message persistant pour scrim_creation dans guild_id %s", guild_id)
    try:
        await service.persist_message(
            channel_id=channel_id,
            message_id=test_message_id,
            message_type="scrim_creation",
            guild_id=guild_id
        )
        logger.info("Message persistant inséré pour channel_id %s, message_id %s, guild_id %s.", channel_id, test_message_id, guild_id)
    except Exception as e:
        logger.exception("Erreur lors de la persistance du message.")

    logger.info("=== Fin du test de simulation du modal ===")

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_modal_simulation())
