# integrations\valorant-api\service.py

import logging
from pydantic import ValidationError

from integrations.exceptions import ApiError
from integrations.http_client import HTTPClient
from integrations.valorant_api.models import CardResponseUuid, TitleResponseUuid

logger = logging.getLogger(__name__)

class ValorantApiService:

    BASE_URL = "https://valorant-api.com"

    def __init__(self, client: HTTPClient):
        self._client = client


    async def get_player_card_by_uuid(self, playercarduid: str):

        url = f"{self.BASE_URL}/v1/playercards/{playercarduid}"
        resp = await self._client.get(url)

        try:
            model = CardResponseUuid.model_validate(resp.payload)
        except ValidationError as e:
            logger.exception("Invalid payload for get_account_by_name (url=%s)", url)
            raise ApiError(f"Invalid API payload: {e}") from e
        
        return model
    
    async def get_player_title_by_uuid(self, playertitleUuid: str):

        url = f"{self.BASE_URL}/v1/playertitles/{playertitleUuid}"
        resp = await self._client.get(url)

        try:
            model = TitleResponseUuid.model_validate(resp.payload)
        except ValidationError as e:
            logger.exception("Invalid payload for get_account_by_name (url=%s)", url)
            raise ApiError(f"Invalid API payload: {e}") from e
        
        return model