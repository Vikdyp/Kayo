# test.py

import sys
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from valorant_service import (
    get_puuid,
    get_player_rank,
    get_stored_mmr_history,
    get_mmr_history,
    get_matchlists_by_puuid,    # ← nouveau
    close_session,
    RateLimitException
)

async def main(pseudo: str, tag: str):
    try:
        # --- Récupération du PUUID ---
        result = await get_puuid(pseudo, tag)
        if not result:
            print("Compte introuvable.")
            return
        nom_tag, region, puuid = result
        print(f"\nNom et tag : {nom_tag}\nRégion     : {region}\nPUUID      : {puuid}")

        # --- Rang & Elo ---
        rank_data = await get_player_rank(region, puuid)
        if rank_data:
            rank, elo = rank_data
            print(f"Rang : {rank}\nElo  : {elo}")
        else:
            print("Rang introuvable pour ce joueur.")

        # --- Historique stocké ou live ---
        print("\n→ Historique MMR stocké…")
        stored = await get_stored_mmr_history(region, puuid)
        if stored:
            print(f"{len(stored)} entrées stockées :")
            for e in stored[-5:]:
                date     = e.get("date","N/A")
                old, new = e.get("oldmmr","N/A"), e.get("newmmr","N/A")
                print(f"  • {date} : {old} → {new}")
        else:
            print("Aucun historique stocké, fallback sur live…")
            recent = await get_mmr_history(region, puuid)
            if recent:
                print(f"{len(recent)} entrées récentes :")
                for e in recent[-5:]:
                    date     = e.get("date","N/A")
                    old, new = e.get("oldMMR","N/A"), e.get("newMMR","N/A")
                    print(f"  • {date} : {old} → {new}")
            else:
                print("Pas d'historique live non plus.")

        # --- Nouvelle fonction : liste de matchs brute ---
        print("\n→ Liste brute des matchs (raw matchlists)…")
        matches = await get_matchlists_by_puuid(puuid)
        if matches is None:
            print("Erreur lors de la récupération des matchlists.")
        elif not matches:
            print("Aucun matchlist trouvé via raw endpoint.")
        else:
            print(f"{len(matches)} matchs trouvés :")
            # Affiche les 5 premiers
            for m in matches[:5]:
                game_id = m.get("gameId") or m.get("matchId") or "N/A"
                ts      = m.get("gameStartTime") or m.get("gameStartTimeMillis") or "N/A"
                print(f"  • {game_id} démarré à {ts}")

    except RateLimitException as e:
        print("Erreur 429, trop de requêtes :", e)
    except Exception as e:
        print("Erreur inattendue :", e)
    finally:
        await close_session()

if __name__ == "__main__":
    full = input("Entrez le pseudo#tag : ").strip()
    if "#" not in full:
        print("Format invalide, il faut un '#'."); sys.exit(1)
    pseudo, tag = (p.strip() for p in full.split("#", 1))
    asyncio.run(main(pseudo, tag))
