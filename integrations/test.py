# integrations\test.py

import os
import asyncio
from dotenv import load_dotenv

from integrations.http_client import HTTPClient
from integrations.henrikdev.service import HenrikDevService
from integrations.valorant_api.service import ValorantApiService
from integrations.exceptions import RateLimitError, ApiError, NetworkError

load_dotenv()

async def main():
    
    api_key = os.getenv("HENRIK_VALO_KEY")
    if not api_key:
        print("La cle API n'est pas defini")
        return

    async with HTTPClient() as client:
        svc = HenrikDevService(client, api_key=api_key)
        svc2 = ValorantApiService(client)

        try:
            resp, rl = await svc.get_account_by_name("TRG Max", "7641")

            card_uuid = resp.data.card
            puuid = resp.data.puuid
            region = resp.data.region
            title = resp.data.title

            print(f"\nResult: {card_uuid}, {resp.data.title}\n")
            print(f"Rate limit restant: {rl.remaining}\nReset: {rl.reset_seconds}")

            resp, rl = await svc.get_matchlist_by_puuid(region=region, puuid=puuid, platform="pc", size=2, start=0, mode="competitive")

            platform = resp.data[0].metadata.platform

            print(f"\nResult: {platform, resp.data[1].metadata.map}\n")
            print(f"Rate limit restant: {rl.remaining}\nReset: {rl.reset_seconds}")

            resp, rl = await svc.get_mmr_by_puuid(region=region, platform=platform, puuid=puuid)
            print(f"Rank: {resp.data.current.tier}")

            resp = await svc2.get_player_card_by_uuid(card_uuid)
            print(f"Card: {resp.data.largeArt}")

            resp = await svc2.get_player_title_by_uuid(title)
            print(f"Title: {resp.data.displayName}, {resp.data.titleText}")

            resp, rl = await svc.get_stored_mmr_history_by_puuid(region=region, platform=platform, puuid=puuid)
            print(f"Stored MMR: {resp.data[0].tier.name}, {resp.data[0].rr}, Date: {resp.data[0].date}")
 
            resp, rl = await svc.get_mmr_history_by_puuid(region=region, platform=platform, puuid=puuid)
            print(f"Live MMR History for {resp.data.account.name}: Rank={resp.data.history[0].tier.name}, RR={resp.data.history[0].rr}, Date={resp.data.history[0].date}")
        
        except RateLimitError as e:
            print("Rate Limit:", e)
        
        except ApiError as e:
            print("Api Error:", e)


        except NetworkError as e:
            print("Network Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
