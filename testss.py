import requests
import os
import argparse
import logging
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

# Configuration des logs
logging.basicConfig(
    filename='get_puuid_et_rang.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger()

def definir_configuration(player_name, player_tag):
    """
    Définit la configuration nécessaire pour la requête API.

    Args:
        player_name (str): Le nom de l'utilisateur.
        player_tag (str): Le tag de l'utilisateur.

    Returns:
        dict: Un dictionnaire contenant la clé API, le nom, le tag et les en-têtes.
    """
    # Récupère la clé API depuis une variable d'environnement
    api_key = os.getenv("HENRIK_VALO_KEY")
    
    # URL de l'API avec les paramètres nom et tag
    url = f"https://api.henrikdev.xyz/valorant/v2/account/{player_name}/{player_tag}"
    
    # Configuration des en-têtes pour l'authentification
    headers = {}
    if api_key:
        headers["Authorization"] = api_key
    
    logger.info(f"Configuration définie pour {player_name}#{player_tag}")
    
    return {
        "api_key": api_key,
        "player_name": player_name,
        "player_tag": player_tag,
        "url": url,
        "headers": headers
    }

def envoyer_requete(url, headers):
    """
    Envoie une requête GET à l'API.

    Args:
        url (str): L'URL complète de l'API.
        headers (dict): Les en-têtes de la requête.

    Returns:
        dict: La réponse JSON si la requête est réussie, sinon None.
    """
    try:
        logger.info(f"Envoi de la requête à l'URL: {url}")
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Lève une exception pour les erreurs HTTP
        logger.info("Requête réussie.")
        return response.json()
    except requests.exceptions.HTTPError as errh:
        logger.error(f"Erreur HTTP: {errh}")
        print(f"Erreur HTTP: {errh}")
    except requests.exceptions.ConnectionError as errc:
        logger.error(f"Erreur de connexion: {errc}")
        print(f"Erreur de connexion: {errc}")
    except requests.exceptions.Timeout as errt:
        logger.error(f"Timeout: {errt}")
        print(f"Timeout: {errt}")
    except requests.exceptions.RequestException as err:
        logger.error(f"Erreur: {err}")
        print(f"Erreur: {err}")
    return None

def extraire_informations(donnees):
    """
    Extrait le nom, le tag, la région et le puuid des données de la réponse.

    Args:
        donnees (dict): Les données JSON de la réponse de l'API.

    Returns:
        tuple: (nom_tag, region, puuid) si disponibles, sinon (None, None, None).
    """
    try:
        data = donnees['data']
        nom = data['name']
        tag = data['tag']
        region = data['region']
        puuid = data['puuid']
        nom_tag = f"{nom}#{tag}"
        logger.info(f"Informations extraites pour {nom_tag}")
        return nom_tag, region, puuid
    except KeyError as e:
        logger.error(f"Clé manquante dans les données de la réponse : {e}")
        print(f"Clé manquante dans les données de la réponse : {e}")
    return None, None, None

def obtenir_rang(region, puuid, headers):
    """
    Obtient les informations de rang (MMR) en utilisant le puuid et la région.

    Args:
        region (str): La région de l'utilisateur.
        puuid (str): Le puuid de l'utilisateur.
        headers (dict): Les en-têtes de la requête, incluant l'API key.

    Returns:
        dict: La réponse JSON contenant les informations de rang si réussie, sinon None.
    """
    url_rang = f"https://api.henrikdev.xyz/valorant/v2/by-puuid/mmr/{region}/{puuid}"
                
    
    try:
        logger.info(f"Envoi de la requête de rang à l'URL: {url_rang}")
        response = requests.get(url_rang, headers=headers)
        response.raise_for_status()
        logger.info("Requête de rang réussie.")
        return response.json()
    except requests.exceptions.HTTPError as errh:
        logger.error(f"Erreur HTTP lors de la récupération du rang: {errh}")
        print(f"Erreur HTTP lors de la récupération du rang: {errh}")
    except requests.exceptions.ConnectionError as errc:
        logger.error(f"Erreur de connexion lors de la récupération du rang: {errc}")
        print(f"Erreur de connexion lors de la récupération du rang: {errc}")
    except requests.exceptions.Timeout as errt:
        logger.error(f"Timeout lors de la récupération du rang: {errt}")
        print(f"Timeout lors de la récupération du rang: {errt}")
    except requests.exceptions.RequestException as err:
        logger.error(f"Erreur lors de la récupération du rang: {err}")
        print(f"Erreur lors de la récupération du rang: {err}")
    return None

def extraire_rang(donnees_rang):
    """
    Extrait le tier et l'elo des données de rang.

    Args:
        donnees_rang (dict): Les données JSON de la réponse de l'API de rang.

    Returns:
        tuple: (tier_patched, elo) si disponibles, sinon (None, None).
    """
    try:
        current_data = donnees_rang['data']['current_data']
        tier_patched = current_data['currenttierpatched']
        elo = current_data['elo']
        return tier_patched, elo
    except KeyError as e:
        logger.error(f"Clé manquante dans les données de rang : {e}")
        print(f"Clé manquante dans les données de rang : {e}")
    return None, None

def main():
    # Configuration des arguments de la ligne de commande
    parser = argparse.ArgumentParser(description="Obtenir le puuid et le rang d'un compte Valorant.")
    parser.add_argument('player_name', type=str, help="Le nom de l'utilisateur.")
    parser.add_argument('player_tag', type=str, help="Le tag de l'utilisateur.")
    args = parser.parse_args()
    
    # Définir la configuration
    config = definir_configuration(args.player_name, args.player_tag)
    
    # Envoyer la requête à l'API pour obtenir le puuid
    donnees_reponse = envoyer_requete(config['url'], config['headers'])
    
    if donnees_reponse:
        # Vérifier le statut de la réponse
        status = donnees_reponse.get('status')
        if status == 0 or status == 200:  # Ajusté pour inclure 200 comme succès
            # Extraire les informations nécessaires
            nom_tag, region, puuid = extraire_informations(donnees_reponse)
            if nom_tag and region and puuid:
                print(f"Nom : {nom_tag}")
                print(f"Région : {region}")
                print(f"Puuid : {puuid}")
                
                # Obtenir le rang en utilisant puuid et region
                donnees_rang = obtenir_rang(region, puuid, config['headers'])
                if donnees_rang:
                    # Extraire les informations de rang
                    tier_patched, elo = extraire_rang(donnees_rang)
                    if tier_patched and elo is not None:
                        print(f"Rang : {tier_patched}")
                        print(f"Elo : {elo}")
                    else:
                        print("Impossible d'extraire les informations de rang.")
                else:
                    print("Impossible d'obtenir les informations de rang.")
            else:
                print("Impossible d'extraire toutes les informations nécessaires.")
        else:
            # Gérer les cas où le statut n'est pas 0 ou 200 (succès)
            message = donnees_reponse.get('message', 'Erreur inconnue.')
            logger.error(f"Erreur de l'API. Statut: {status}, Message: {message}")
            print(f"Erreur de l'API. Statut: {status}, Message: {message}")
    else:
        print("La requête à l'API a échoué.")

if __name__ == "__main__":
    main()
