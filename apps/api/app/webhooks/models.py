from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import WebhookEventStatus


class WebhookEntityContainer(BaseModel):
    entity: dict[str, Any]

    model_config = ConfigDict(extra="ignore")


class RazorpayWebhookEnvelope(BaseModel):
    entity: Literal["event"]
    account_id: str | None = Field(default=None, max_length=255)
    event: str = Field(min_length=1, max_length=128)
    contains: list[str] = Field(default_factory=list)
    payload: dict[str, WebhookEntityContainer]
    created_at: int = Field(ge=0)

    model_config = ConfigDict(extra="ignore")


class WebhookIngestionResult(BaseModel):
    event_id: str
    status: WebhookEventStatus
    duplicate: bool
