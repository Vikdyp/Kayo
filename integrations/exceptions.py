# integrations\exceptions.py

class IntegrationError(Exception):
    """
    Erreur de base pour tout se qui concerne l'api Hendrik
    """
    pass

class NetworkError(IntegrationError):
    """
    Timeout, DNS, connexion perdu ou tout autre erreur reseau
    """
    pass

class ApiError(IntegrationError):
    """
    Le serveur repond avec une erreur
    """
    pass

class RateLimitError(ApiError):
    """
    Rate limit atteint
    """
    pass
