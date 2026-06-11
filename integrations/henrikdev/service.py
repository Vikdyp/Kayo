# integrations\henrikdev\service.py

import logging
from pydantic import ValidationError

from integrations.exceptions import ApiError
from integrations.http_client import HTTPClient
from integrations.henrikdev.models import (
    AccountResponseName,
    AccountResponsePuuid,
    MatchlistResponse,
    MmrHistoryV2Response,
    MmrResponse,
    RateLimit,
    StoreFeaturedResponse,
    StoredMmrHistoryV2Response,
)

logger = logging.getLogger(__name__)

class HenrikDevService:

    BASE_URL = "https://api.henrikdev.xyz/valorant"

    def __init__(self, client: HTTPClient, api_key: str, header_name: str = "Authorization"):
        self._client = client
        self._api_key = api_key.strip()
        self._header = {header_name: self._api_key} if self._api_key else {}

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)


    async def get_account_by_name(self, name: str, tag: str) -> tuple[AccountResponseName, RateLimit]:
        """
    Get Valorant account info from HenrikDev using Name + Tag.

    Retourne:
      AccountResponsePuuid, with:
        - :data.puuid: str
        - :data.region: str
        - :data.account_level: int
        - :data.name: str
        - :data.tag: str
        - :data.card: str
        - :data.title: str
        - :data.platforms: Sequence[str]
        - :data.updated_at: str
        """

        url = f"{self.BASE_URL}/v2/account/{name}/{tag}"
        resp = await self._client.get(url, headers=self._header)

        rl = resp.ratelimit()
        logger.debug("RateLimit: remaining=%s/%s reset=%ss bucket=%s version=%s",
            rl.remaining, rl.limit, rl.reset_seconds, rl.bucket, rl.version)
        
        try:
            model = AccountResponseName.model_validate(resp.payload)
        except ValidationError as e:
            logger.exception("Invalid payload for get_account_by_name (url=%s)", url)
            raise ApiError(f"Invalid API payload: {e}") from e
        
        return model, rl
    
    
    async def get_account_by_puuid(self, puuid: str) -> tuple[AccountResponsePuuid, RateLimit]:
        """
    Get Valorant account info from HenrikDev using a PUUID.

    Retourne:
      AccountResponsePuuid, with:
        - :data.puuid: str
        - :data.region: str
        - :data.account_level: int
        - :data.name: str
        - :data.tag: str
        - :data.card.small: str
        - :data.card.large: str
        - :data.card.wide: str
        - :data.card.id: str
        - :data.last_update: str
        - :data.last_update_raw: str
        """

        url = f"{self.BASE_URL}/v1/by-puuid/account/{puuid}"
        resp = await self._client.get(url, headers=self._header)

        rl = resp.ratelimit()
        logger.debug("RateLimit: remaining=%s/%s reset=%ss bucket=%s version=%s",
            rl.remaining, rl.limit, rl.reset_seconds, rl.bucket, rl.version)
        
        try:
            model = AccountResponsePuuid.model_validate(resp.payload)
        except ValidationError as e:
            logger.exception("Invalid payload for get_account_by_puuid (url=%s)", url)
            raise ApiError(f"Invalid API payload: {e}") from e
        
        return model, rl

    
    async def get_mmr_by_puuid(self, region: str, platform: str, puuid: str):

        url = f"{self.BASE_URL}/v3/by-puuid/mmr/{region}/{platform}/{puuid}"
        resp = await self._client.get(url, headers=self._header)

        rl = resp.ratelimit()
        logger.debug("RateLimit: remaining=%s/%s reset=%ss bucket=%s version=%s",
            rl.remaining, rl.limit, rl.reset_seconds, rl.bucket, rl.version)
        
        try:
            model = MmrResponse.model_validate(resp.payload)
        except ValidationError as e:
            logger.exception("Invalid payload for get_mmr_by_puuid (url=%s)", url)
            raise ApiError(f"Invalid API payload: {e}") from e
        
        return model, rl
    

    async def get_matchlist_by_puuid(self, region: str, platform: str, puuid: str, *, mode: str | None = None,
                                     map: str | None = None, size: int | None = 10, start: int | None = None):
        
        params: dict[str, object] = {"size": size}
        if start is not None:
            params["start"] = start
        if mode is not None:
            params["mode"] = mode
        if map is not None:
            params["map"] = map
        
        url = f"{self.BASE_URL}/v4/by-puuid/matches/{region}/{platform}/{puuid}"
        resp = await self._client.get(url, params=params, headers=self._header)

        rl = resp.ratelimit()
        logger.debug("RateLimit: remaining=%s/%s reset=%ss bucket=%s version=%s",
            rl.remaining, rl.limit, rl.reset_seconds, rl.bucket, rl.version)
        
        try:
            model = MatchlistResponse.model_validate(resp.payload)
        except ValidationError as e:
            logger.exception("Invalid payload for get_matchlist_by_puuid (url=%s)", url)
            raise ApiError(f"Invalid API payload: {e}") from e
        
        return model, rl

    async def get_mmr_history_by_puuid(self, region: str, platform: str, puuid: str):
        
        url = f"{self.BASE_URL}/v2/by-puuid/mmr-history/{region}/{platform}/{puuid}"
        resp = await self._client.get(url, headers=self._header)

        rl = resp.ratelimit()
        logger.debug("RateLimit: remaining=%s/%s reset=%ss bucket=%s version=%s",
            rl.remaining, rl.limit, rl.reset_seconds, rl.bucket, rl.version)
        
        try:
            model = MmrHistoryV2Response.model_validate(resp.payload)
        except ValidationError as e:
            logger.exception("Invalid payload for get_mmr_history_by_puuid (url=%s)", url)
            raise ApiError(f"Invalid API payload: {e}") from e
        
        return model, rl

    async def get_stored_mmr_history_by_puuid(
        self,
        region: str,
        platform: str,
        puuid: str,
        *,
        size: int | None = None,
        start: int | None = None,
    ):
        
        url = f"{self.BASE_URL}/v2/by-puuid/stored-mmr-history/{region}/{platform}/{puuid}"
        params: dict[str, int] = {}
        if size is not None:
            params["size"] = size
        if start is not None:
            params["start"] = start
        resp = await self._client.get(
            url,
            params=params or None,
            headers=self._header,
        )

        rl = resp.ratelimit()
        logger.debug("RateLimit: remaining=%s/%s reset=%ss bucket=%s version=%s",
            rl.remaining, rl.limit, rl.reset_seconds, rl.bucket, rl.version)
        
        try:
            model = StoredMmrHistoryV2Response.model_validate(resp.payload)
        except ValidationError as e:
            logger.exception("Invalid payload for get_stored_mmr_history_by_puuid (url=%s)", url)
            raise ApiError(f"Invalid API payload: {e}") from e
        
        return model, rl

    async def get_featured_store(self) -> tuple[StoreFeaturedResponse, RateLimit]:
        url = f"{self.BASE_URL}/v2/store-featured"
        resp = await self._client.get(url, headers=self._header)

        rl = resp.ratelimit()
        logger.debug(
            "RateLimit: remaining=%s/%s reset=%ss bucket=%s version=%s",
            rl.remaining,
            rl.limit,
            rl.reset_seconds,
            rl.bucket,
            rl.version,
        )

        try:
            model = StoreFeaturedResponse.model_validate(resp.payload)
        except ValidationError as e:
            logger.exception("Invalid payload for get_featured_store (url=%s)", url)
            raise ApiError(f"Invalid API payload: {e}") from e

        return model, rl
