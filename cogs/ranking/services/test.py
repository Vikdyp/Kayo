# test.py

import sys
import asyncio

# Sur Windows, on force le SelectorEventLoop pour éviter l'erreur
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from valorant_service import (
    get_puuid,
    get_player_rank,
    get_stored_mmr_history,
    close_session,
    RateLimitException
)

async def main(pseudo: str, tag: str):
    try:
        # 1) Récupération du PUUID
        result = await get_puuid(pseudo, tag)
        if not result:
            print("Erreur : aucun compte trouvé ou réponse inattendue.")
            return

        nom_tag, region, puuid = result
        print(f"\nNom et tag : {nom_tag}\nRégion     : {region}\nPUUID      : {puuid}")

        # 2) Récupération du rang et de l'Elo
        rank_data = await get_player_rank(region, puuid)
        if rank_data:
            rank, elo = rank_data
            print(f"Rang : {rank}\nElo  : {elo}")
        else:
            print("Impossible de récupérer le rang pour ce joueur.")

        # 3) Récupération de l'historique complet de MMR
        print("\n→ Chargement de l'historique complet de MMR...")
        history = await get_stored_mmr_history(region, puuid)

        if not history:
            print("Aucun historique MMR stocké trouvé pour ce joueur.")
        else:
            print(f"{len(history)} entrées d'historique récupérées :")
            # Affiche par exemple les 5 dernières entrées
            for entry in history[-5:]:
                date = entry.get("date", "N/A")
                mmr_before = entry.get("oldmmr", "N/A")
                mmr_after  = entry.get("newmmr", "N/A")
                print(f"  • {date} → {mmr_before} ➞ {mmr_after}")

    except RateLimitException as e:
        print("Erreur de limitation de taux (429) :", e)
    except Exception as e:
        print("Une erreur est survenue :", e)
    finally:
        # 4) Fermeture propre de la session partagée
        await close_session()

if __name__ == "__main__":
    # Lecture de "pseudo#tag" en une seule saisie
    full_tag = input("Entrez le pseudo#tag : ").strip()

    if "#" not in full_tag:
        print("Format invalide : utilisez le caractère '#' pour séparer le pseudo et le tag.")
        sys.exit(1)

    pseudo, tag = full_tag.split("#", 1)
    pseudo = pseudo.strip()
    tag    = tag.strip()

    if not pseudo or not tag:
        print("Pseudo ou tag manquant après le '#'.")
        sys.exit(1)

    asyncio.run(main(pseudo, tag))
