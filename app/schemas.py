from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EventCreate(BaseModel):
    type: str
    payload: dict[str, Any]
    webhook_url: str


class AttemptResponse(BaseModel):
    attempted_at: datetime
    http_status: int | None
    outcome: str


class EventResponse(BaseModel):
    id: int
    type: str
    payload: dict[str, Any]
    webhook_url: str
    status: str
    created_at: datetime
    attempts: list[AttemptResponse] = []