from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    message: str


class AIConfigResponse(BaseModel):
    module: str
    kill_switch: bool
    confidence_threshold: float | None = None


class AIConfigUpdate(BaseModel):
    kill_switch: bool | None = None
    confidence_threshold: float | None = None
