import requests
import _VAPI from "unofficial-valorant-api"

class ValorantAPI:
    def __init__(self, token=None):
        self.base_url = "https://api.henrikdev.xyz/valorant"
        self.token = token

    def get_mmr_by_puuid(self, region, puuid):
        """Obtenir les informations de MMR d'un joueur à partir de son PUUID"""
        url = f"{self.base_url}/v1/by-puuid/mmr/{region}/{puuid}"
        headers = {
            "Authorization": f"Bearer {self.token}"
        }
        
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                return {"error": "Unauthorized - Invalid API key"}
            elif response.status_code == 404:
                return {"error": "Player not found"}
            else:
                return {"error": f"Unexpected error: {response.status_code}", "details": response.text}
        except Exception as e:
            return {"error": "Request failed", "details": str(e)}

# Exemple d'utilisation
if __name__ == "__main__":
    # Initialisez l'API avec votre clé
    api_key = "HDEV-b8b49b92-9f80-4849-a715-81fcc325592c"
    puuid = "VpZNvK-e4M-cXX_oSx4u5pyjCGy6vPjr061Yuuip7PTkEpbfD86C4Qx7fHz5OZHSGDTrBYiWVWCGQg"
    region = "europe"

    valorant_api = ValorantAPI(token=api_key)
    
    # Appeler l'API pour obtenir les informations MMR
    mmr_data = valorant_api.get_mmr_by_puuid(region, puuid)
    
    # Afficher les données
    print(mmr_data)
