# config_log.py

# Activer ou désactiver les logs pour chaque module
LOGGING_ENABLED = {
    "bot": True,
    "request_manager": True,
    "configuration.channels": True,  # Exemple pour un cog
    "ranking.assign_rank_role": True,  # Ajoutez d'autres modules ou cogs ici
    "ranking.link_valorant": True,
    # Continuez à ajouter les autres modules ou cogs
}

# Mode debug global
GLOBAL_DEBUG = True
