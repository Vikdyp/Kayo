from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

from integrations.exceptions import ApiError, NetworkError, RateLimitError
from integrations.henrikdev.service import HenrikDevService
from integrations.http_client import HTTPClient
from integrations.valorant_api.service import ValorantApiService

load_dotenv()


async def main() -> None:
    api_key = os.getenv("HENRIK_VALO_KEY")
    if not api_key:
        print("Missing HENRIK_VALO_KEY.")
        return

    async with HTTPClient() as client:
        henrik = HenrikDevService(client, api_key=api_key)
        valorant_api = ValorantApiService(client)

        try:
            account, rate_limit = await henrik.get_account_by_name("TRG Max", "7641")
            card_uuid = account.data.card
            puuid = account.data.puuid
            region = account.data.region
            title_uuid = account.data.title

            print(f"Account: {account.data.name}#{account.data.tag}, card={card_uuid}")
            print(f"Rate limit: remaining={rate_limit.remaining}, reset={rate_limit.reset_seconds}s")

            matchlist, rate_limit = await henrik.get_matchlist_by_puuid(
                region=region,
                puuid=puuid,
                platform="pc",
                size=2,
                start=0,
                mode="competitive",
            )
            platform = matchlist.data[0].metadata.platform
            print(f"Matchlist: platform={platform}, sample_map={matchlist.data[1].metadata.map}")
            print(f"Rate limit: remaining={rate_limit.remaining}, reset={rate_limit.reset_seconds}s")

            mmr, _ = await henrik.get_mmr_by_puuid(region=region, platform=platform, puuid=puuid)
            print(f"MMR: current_rank={mmr.data.current.tier}")

            card = await valorant_api.get_player_card_by_uuid(card_uuid)
            print(f"Card: {card.data.largeArt}")

            title = await valorant_api.get_player_title_by_uuid(title_uuid)
            print(f"Title: {title.data.displayName}, text={title.data.titleText}")

            stored_history, _ = await henrik.get_stored_mmr_history_by_puuid(
                region=region,
                platform=platform,
                puuid=puuid,
            )
            print(
                "Stored MMR:",
                stored_history.data[0].tier.name,
                stored_history.data[0].rr,
                stored_history.data[0].date,
            )

            live_history, _ = await henrik.get_mmr_history_by_puuid(
                region=region,
                platform=platform,
                puuid=puuid,
            )
            print(
                "Live MMR:",
                live_history.data.account.name,
                live_history.data.history[0].tier.name,
                live_history.data.history[0].rr,
                live_history.data.history[0].date,
            )

        except RateLimitError as exc:
            print("Rate limit:", exc)
        except ApiError as exc:
            print("API error:", exc)
        except NetworkError as exc:
            print("Network error:", exc)


if __name__ == "__main__":
    asyncio.run(main())
