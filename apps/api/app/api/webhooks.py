from collections.abc import Callable
from functools import partial

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.integrations.payment_gateway import PaymentGateway
from app.integrations.razorpay import create_razorpay_gateway
from app.webhooks.models import RazorpayWebhookEnvelope, WebhookIngestionResult
from app.webhooks.security import verify_razorpay_signature
from app.webhooks.service import WebhookIngestionService, WebhookProcessingError

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
GatewayFactory = Callable[[], PaymentGateway]


def get_gateway_factory(
    settings: Settings = Depends(get_settings),
) -> GatewayFactory:
    return partial(create_razorpay_gateway, settings)


@router.post("/razorpay", response_model=WebhookIngestionResult)
async def ingest_razorpay_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(
        default=None, alias="X-Razorpay-Signature"
    ),
    x_razorpay_event_id: str | None = Header(
        default=None, alias="x-razorpay-event-id"
    ),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    gateway_factory: GatewayFactory = Depends(get_gateway_factory),
) -> WebhookIngestionResult:
    current_secret = settings.razorpay_webhook_secret
    if current_secret is None or not current_secret.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay webhook ingestion is not configured.",
        )
    if not x_razorpay_event_id or len(x_razorpay_event_id.strip()) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid x-razorpay-event-id header is required.",
        )

    raw_body = await request.body()
    if len(raw_body) > settings.razorpay_webhook_max_body_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Webhook payload exceeds the configured size limit.",
        )

    secrets = [current_secret.get_secret_value()]
    if settings.razorpay_webhook_previous_secret is not None:
        secrets.append(settings.razorpay_webhook_previous_secret.get_secret_value())
    if not verify_razorpay_signature(
        raw_body, x_razorpay_signature or "", secrets
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Razorpay webhook signature.",
        )

    try:
        envelope = RazorpayWebhookEnvelope.model_validate_json(raw_body)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Razorpay webhook payload.",
        ) from exc

    try:
        return WebhookIngestionService(
            session,
            gateway_factory,
            recovery_window_days=settings.recovery_window_days,
        ).ingest(x_razorpay_event_id.strip(), envelope)
    except WebhookProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
