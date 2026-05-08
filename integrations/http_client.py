# integrations\http_client.py

import aiohttp
import asyncio
import json
import logging
from typing import Any, Mapping, Sequence

from integrations.exceptions import RateLimitError, ApiError, NetworkError
from integrations.henrikdev.models import HttpResponse

logger = logging.getLogger(__name__)

class HTTPClient:
    """
    Client HTTP qui utilise aiohttp.

    Role:
    - Ouvrir et Fermer une session aiohttp (via async with).
    - Faire des requetes GET et retourner du JSON.
    - Traduire les erreur reseau/HTTP/JSON vers des exeptions.
    """

    def __init__(self, timeout_seconds: float = 10.0):
        self._session = None
        self._timeout_seconds = timeout_seconds

    async def __aenter__(self):
        """
        Cree une session et le client
        
        return:

        self : self._session
        """

        logger.debug("Ouverture de la session (timeout %ss)", self._timeout_seconds)

        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        self._session = aiohttp.ClientSession(timeout=timeout)
        return self


    async def __aexit__(self, exc_type, exc, tb):
        logger.debug("Fermeture de la session")
        await self.close()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
            # aiohttp recommends a short delay for SSL transports to close cleanly.
            await asyncio.sleep(0.25)

    def _truncate(self, text: str, limit: int = 500) -> str:
        if len(text) <= limit:
            return text
        else:
            return text[:limit] + f"...(body tronquer max {limit} caractère)"
        
    ParamsType = Mapping[str, Any] | Sequence[tuple[str, Any]]

    async def get(self, url: str, *, params: ParamsType | None = None, headers: Mapping[str, str] | None = None) -> HttpResponse:
        if self._session is None:
            logger.error("HTTPClient used without session (use 'async with').")
            raise RuntimeError("HTTPClient must be used with 'async with'.")

        logger.debug("GET %s (params=%s)", url, params)

        try:
            async with self._session.get(url, params=params, headers=headers) as resp:
                status = resp.status

                # Copie headers en dict[str, str]
                resp_headers = {k: v for k, v in resp.headers.items()}

                if status >= 400:
                    body = self._truncate(await resp.text())
                    if status == 429:
                        logger.warning("HTTP 429 rate-limited on %s", url)
                        raise RateLimitError(f"HTTP {status}: {body}")
                    logger.error("HTTP %s on %s | body=%s", status, url, body)
                    raise ApiError(f"HTTP {status}: {body}")

                try:
                    data = await resp.json()
                except aiohttp.ContentTypeError:
                    body = self._truncate(await resp.text())
                    logger.error("Invalid JSON content-type on %s | body=%s", url, body)
                    raise ApiError(f"Invalid JSON (content-type). Body: {body}")
                
                except json.JSONDecodeError:
                    body = self._truncate(await resp.text())
                    logger.error("Invalid JSON decode on %s | body=%s", url, body)
                    raise ApiError(f"Invalid JSON (decode). Body: {body}")

                if not isinstance(data, dict):
                    logger.error("Unexpected JSON type from %s: %s", url, type(data).__name__)
                    raise ApiError(f"Unexpected JSON type: {type(data).__name__}")

                return HttpResponse(status=status, payload=data, headers=resp_headers)

        except asyncio.TimeoutError:
            logger.warning("Timeout after %ss on %s", self._timeout_seconds, url)
            raise NetworkError(f"Request timed out after {self._timeout_seconds}s")

        except aiohttp.ClientError as e:
            logger.exception("Network error on %s", url)
            raise NetworkError(str(e))
        

    async def post(self, url: str, *, params: ParamsType | None = None, headers: Mapping[str, str] | None = None, data: Mapping[str, Any] | None = None) -> HttpResponse:
        if self._session is None:
            logger.error("HTTPClient used without session (use 'async with').")
            raise RuntimeError("HTTPClient must be used with 'async with'.")

        logger.debug("POST %s (params=%s)", url, params)

        try:
            async with self._session.post(url, params=params, data=data, headers=headers) as resp:
                status = resp.status
                resp_headers = {k: v for k, v in resp.headers.items()}

                if status >= 400:
                    body = self._truncate(await resp.text())
                    if status == 429:
                        logger.warning("HTTP 429 rate-limited on %s", url)
                        raise RateLimitError(f"HTTP {status}: {body}")
                    logger.error("HTTP %s on %s | body=%s", status, url, body)
                    raise ApiError(f"HTTP {status}: {body}")

                try:
                    data_json = await resp.json()
                except aiohttp.ContentTypeError:
                    body = self._truncate(await resp.text())
                    logger.error("Invalid JSON content-type on %s | body=%s", url, body)
                    raise ApiError(f"Invalid JSON (content-type). Body: {body}")
                except json.JSONDecodeError:
                    body = self._truncate(await resp.text())
                    logger.error("Invalid JSON decode on %s | body=%s", url, body)
                    raise ApiError(f"Invalid JSON (decode). Body: {body}")

                if not isinstance(data_json, dict):
                    logger.error("Unexpected JSON type from %s: %s", url, type(data_json).__name__)
                    raise ApiError(f"Unexpected JSON type: {type(data_json).__name__}")

                return HttpResponse(status=status, payload=data_json, headers=resp_headers)

        except asyncio.TimeoutError:
            logger.warning("Timeout after %ss on %s", self._timeout_seconds, url)
            raise NetworkError(f"Request timed out after {self._timeout_seconds}s")
        except aiohttp.ClientError as e:
            logger.exception("Network error on %s", url)
            raise NetworkError(str(e))
