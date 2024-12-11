# config.py

# Mode global pour activer/désactiver tous les logs
GLOBAL_DEBUG = False  # Si False, désactive tous les logs

# Activer/désactiver les logs pour chaque fichier
LOGGING_CONFIG = {
    "bot": True,
    "request_manager": True,
    "other_module": False,  # Ajoutez d'autres modules ici
}
