from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class TwitchTokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    access_token: str
    expires_in: int
    token_type: str


class TwitchUser(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    login: str
    display_name: str
    profile_image_url: Optional[str] = None


class TwitchUsersResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    data: List[TwitchUser] = []


class TwitchStream(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    user_id: str
    user_login: str
    user_name: str
    game_id: Optional[str] = None
    game_name: Optional[str] = None
    title: str
    viewer_count: int
    started_at: str
    thumbnail_url: Optional[str] = None


class TwitchStreamsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    data: List[TwitchStream] = []


class TwitchGame(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    box_art_url: Optional[str] = None


class TwitchGamesResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    data: List[TwitchGame] = []


class TwitchFollowersResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    total: int = 0
