# integrations\valorant-api\models.py
from __future__ import annotations

from typing import Any, Mapping, Optional, List, Sequence
from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------------------------------------------------------
# Model pour Card avec UUID https://valorant-api.com/v1/playercards/{playercardUuid}                                       |
# --------------------------------------------------------------------------------------------------------------------------

class CardDataUuid(BaseModel):
    model_config = ConfigDict(extra="ignore")

    uuid : str
    displayName : str
    isHiddenIfNotOwned : bool
    themeUuid : str | None = None
    displayIcon : str
    smallArt : str
    wideArt : str
    largeArt : str
    assetPath : str


class CardResponseUuid(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status : int
    data : CardDataUuid


# --------------------------------------------------------------------------------------------------------------------------
# Model pour Card avec UUID https://valorant-api.com/v1/playercards/{playercardUuid}                                       |
# --------------------------------------------------------------------------------------------------------------------------

class TitleDataUuid(BaseModel):
    model_config = ConfigDict(extra="ignore")

    uuid : str
    displayName : str
    titleText : str
    isHiddenIfNotOwned : bool
    assetPath : str

class TitleResponseUuid(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status : int
    data : TitleDataUuid