import time
import logging
from pydantic import ValidationError

from integrations.exceptions import ApiError
from integrations.http_client import HTTPClient
from integrations.twitch.models import (
    TwitchTokenResponse,
    TwitchUsersResponse,
    TwitchStreamsResponse,
    TwitchGamesResponse,
    TwitchFollowersResponse,
)

logger = logging.getLogger(__name__)


class TwitchService:
    OAUTH_URL = "https://id.twitch.tv/oauth2"
    HELIX_URL = "https://api.twitch.tv/helix"

    def __init__(self, client: HTTPClient, client_id: str, client_secret: str):
        self._client = client
        self._client_id = client_id
        self._client_secret = client_secret

        self._token: str | None = None
        self._token_expire_at: float = 0.0  # epoch seconds

    async def _ensure_token(self) -> str:
        # token encore valide ?
        if self._token and time.time() < (self._token_expire_at - 30):
            return self._token

        url = f"{self.OAUTH_URL}/token"
        # Twitch accepte params ou form-data, on envoie en form-data (data=)
        data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "client_credentials",
        }

        resp = await self._client.post(url, data=data)

        try:
            token = TwitchTokenResponse.model_validate(resp.payload)
        except ValidationError as e:
            logger.exception("Invalid payload for twitch token (url=%s)", url)
            raise ApiError(f"Invalid API payload: {e}") from e

        self._token = token.access_token
        self._token_expire_at = time.time() + int(token.expires_in)
        return self._token

    async def _headers(self) -> dict[str, str]:
        token = await self._ensure_token()
        return {
            "Client-Id": self._client_id,
            "Authorization": f"Bearer {token}",
        }

    async def get_streams_by_logins(self, logins: list[str]) -> TwitchStreamsResponse:
        url = f"{self.HELIX_URL}/streams"
        params = [("user_login", login) for login in logins]  # params répétés
        resp = await self._client.get(url, params=params, headers=await self._headers())

        try:
            return TwitchStreamsResponse.model_validate(resp.payload)
        except ValidationError as e:
            logger.exception("Invalid payload for get_streams_by_logins (url=%s)", url)
            raise ApiError(f"Invalid API payload: {e}") from e

    async def get_users_by_logins(self, logins: list[str]) -> TwitchUsersResponse:
        url = f"{self.HELIX_URL}/users"
        params = [("login", login) for login in logins]  # params répétés
        resp = await self._client.get(url, params=params, headers=await self._headers())

        try:
            return TwitchUsersResponse.model_validate(resp.payload)
        except ValidationError as e:
            logger.exception("Invalid payload for get_users_by_logins (url=%s)", url)
            raise ApiError(f"Invalid API payload: {e}") from e

    async def get_followers_total(self, broadcaster_id: str) -> int:
        url = f"{self.HELIX_URL}/channels/followers"
        resp = await self._client.get(
            url,
            params={"broadcaster_id": broadcaster_id, "first": 1},
            headers=await self._headers(),
        )

        try:
            model = TwitchFollowersResponse.model_validate(resp.payload)
        except ValidationError as e:
            logger.exception("Invalid payload for get_followers_total (url=%s)", url)
            raise ApiError(f"Invalid API payload: {e}") from e

        return model.total

    async def get_games_by_ids(self, game_ids: list[str]) -> TwitchGamesResponse:
        url = f"{self.HELIX_URL}/games"
        params = [("id", gid) for gid in game_ids]  # params répétés
        resp = await self._client.get(url, params=params, headers=await self._headers())

        try:
            return TwitchGamesResponse.model_validate(resp.payload)
        except ValidationError as e:
            logger.exception("Invalid payload for get_games_by_ids (url=%s)", url)
            raise ApiError(f"Invalid API payload: {e}") from e
