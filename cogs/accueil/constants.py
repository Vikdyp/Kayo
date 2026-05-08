# cogs/accueil/constants.py
"""Constantes pour le domaine accueil."""

# Types de messages persistants (namespacés pour éviter collisions)
ACCUEIL_STATS_EMBED = "accueil:stats_embed"
ACCUEIL_STATS_THREAD = "accueil:stats_thread"

# Clés de channels (canoniques)
CHANNEL_WELCOME = "welcome"
CHANNEL_RULES = "rules"
CHANNEL_INTRODUCTIONS = "introductions"
CHANNEL_STATS_EMBED = "stats_embed"

# Alias pour compatibilité (géré uniquement dans le service métier)
_CHANNEL_STATS_EMBED_ALIASES = ("stat_embed",)
