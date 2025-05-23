import asyncio
from valorant_service import get_puuid, RateLimitException  # Assurez-vous que le nom du fichier de service est correct

async def main():
    pseudo = input("Entrez le pseudo : ")
    tag = input("Entrez le tag : ")

    try:
        result = await get_puuid(pseudo, tag)
        if result:
            nom_tag, region, puuid = result
            print(f"Nom et tag : {nom_tag}\nRégion : {region}\nPUUID : {puuid}")
        else:
            # Dans le cas où aucun résultat n'est retourné (ex : compte introuvable ou autre erreur non levée)
            print("Erreur : Aucun compte trouvé ou une erreur est survenue lors de la récupération des données.")
    except RateLimitException as e:
        # Affiche le message complet de l'erreur en cas de dépassement de quota (erreur 429)
        print("Erreur de limitation de taux (429) :")
        print(e)
    except Exception as e:
        # Capture toute autre exception et affiche son message
        print("Une erreur est survenue lors de la récupération du PUUID :")
        print(e)

if __name__ == "__main__":
    asyncio.run(main())
