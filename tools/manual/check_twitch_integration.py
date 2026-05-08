from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

from integrations.exceptions import ApiError, NetworkError, RateLimitError
from integrations.http_client import HTTPClient
from integrations.twitch.service import TwitchService

load_dotenv()


async def main() -> None:
    client_id = os.getenv("TWITCH_CLIENT_ID")
    client_secret = os.getenv("TWITCH_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("Missing TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET.")
        return

    async with HTTPClient() as client:
        twitch = TwitchService(client, client_id, client_secret)

        try:
            print("Authenticating Twitch client...")
            await twitch._ensure_token()
            print("Token OK.")

            print("Checking /users...")
            users = await twitch.get_users_by_logins(["Anyme023"])
            if not users.data:
                print("No user found.")
                return

            user = users.data[0]
            print(f"User: {user.display_name} (id={user.id})")

            print("Checking /streams...")
            streams = await twitch.get_streams_by_logins(["Anyme023"])
            if streams.data:
                stream = streams.data[0]
                print(f"Live: {stream.user_name}")
                print(f"Title: {stream.title}")
                print(f"Viewers: {stream.viewer_count}")
                print(f"Game: {stream.game_name}")
                game_id = stream.game_id
            else:
                print("Channel is not live.")
                game_id = None

            print("Checking /followers...")
            followers = await twitch.get_followers_total(user.id)
            print(f"Followers: {followers}")

            if game_id:
                print("Checking /games...")
                games = await twitch.get_games_by_ids([game_id])
                if games.data:
                    print(f"Game: {games.data[0].name}")
                else:
                    print("Game not found.")

            print("Twitch manual check completed.")

        except RateLimitError as exc:
            print("Rate limit:", exc)
        except ApiError as exc:
            print("API error:", exc)
        except NetworkError as exc:
            print("Network error:", exc)


if __name__ == "__main__":
    asyncio.run(main())
