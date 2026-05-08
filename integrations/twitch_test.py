import os
import asyncio
from dotenv import load_dotenv

from integrations.http_client import HTTPClient
from integrations.twitch.service import TwitchService
from integrations.exceptions import ApiError, NetworkError, RateLimitError


load_dotenv()


async def main():

    client_id = os.getenv("TWITCH_CLIENT_ID")
    client_secret = os.getenv("TWITCH_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("❌ TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET manquants")
        return

    async with HTTPClient() as client:
        twitch = TwitchService(client, client_id, client_secret)

        try:
            print("🔐 Authentification Twitch...")
            token = await twitch._ensure_token()
            print("✅ Token OK")

            # ===== TEST USERS =====
            print("\n👤 Test /users ...")
            users = await twitch.get_users_by_logins(["Anyme023"])
            if not users.data:
                print("❌ Aucun user trouvé")
                return

            user = users.data[0]
            print(f"✅ User: {user.display_name} (id={user.id})")

            # ===== TEST STREAMS =====
            print("\n📺 Test /streams ...")
            streams = await twitch.get_streams_by_logins(["Anyme023"])

            if streams.data:
                s = streams.data[0]
                print(f"✅ Live: {s.user_name}")
                print(f"   Titre : {s.title}")
                print(f"   Viewers : {s.viewer_count}")
                print(f"   Jeu : {s.game_name}")
                game_id = s.game_id
            else:
                print("⚠️ Pas en live actuellement")
                game_id = None

            # ===== TEST FOLLOWERS =====
            print("\n👥 Test /followers ...")
            followers = await twitch.get_followers_total(user.id)
            print(f"✅ Followers: {followers}")

            # ===== TEST GAMES =====
            if game_id:
                print("\n🎮 Test /games ...")
                games = await twitch.get_games_by_ids([game_id])

                if games.data:
                    g = games.data[0]
                    print(f"✅ Game: {g.name}")
                else:
                    print("⚠️ Game non trouvé")

            print("\n🎉 Tous les tests Twitch sont OK")

        except RateLimitError as e:
            print("⛔ Rate limit:", e)

        except ApiError as e:
            print("⛔ API error:", e)

        except NetworkError as e:
            print("⛔ Network error:", e)

        except Exception as e:
            print("💥 Erreur inattendue:", repr(e))


if __name__ == "__main__":
    asyncio.run(main())
