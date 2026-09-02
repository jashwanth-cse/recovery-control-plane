from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import WebhookEvent
from app.domain.enums import WebhookEventStatus
from app.webhooks.models import RazorpayWebhookEnvelope

RAZORPAY_PROVIDER = "RAZORPAY"


class WebhookEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, event_id: str) -> WebhookEvent | None:
        statement = select(WebhookEvent).where(
            WebhookEvent.provider == RAZORPAY_PROVIDER,
            WebhookEvent.event_id == event_id,
        )
        return self.session.scalar(statement)

    def record(
        self,
        event_id: str,
        envelope: RazorpayWebhookEnvelope,
    ) -> tuple[WebhookEvent, bool]:
        existing = self.get(event_id)
        if existing is not None:
            return existing, False

        event = WebhookEvent(
            provider=RAZORPAY_PROVIDER,
            event_id=event_id,
            event_type=envelope.event,
            account_id=envelope.account_id,
            event_created_at=datetime.fromtimestamp(
                envelope.created_at, tz=timezone.utc
            ),
            payload=envelope.model_dump(mode="json"),
            status=WebhookEventStatus.RECEIVED,
            processing_attempts=0,
        )
        self.session.add(event)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            duplicate = self.get(event_id)
            if duplicate is None:
                raise
            return duplicate, False
        self.session.refresh(event)
        return event, True

    def mark_processing(self, event: WebhookEvent) -> None:
        event.status = WebhookEventStatus.PROCESSING
        event.processing_attempts += 1
        event.last_error = None
        self.session.commit()

    def mark_ignored(self, event: WebhookEvent) -> None:
        event.status = WebhookEventStatus.IGNORED
        event.processed_at = datetime.now(timezone.utc)
        self.session.commit()

    def mark_processed(
        self,
        event: WebhookEvent,
        *,
        recovery_case_id: UUID | None,
        resource_id: str,
        reconciliation_snapshot: dict,
    ) -> None:
        event.status = WebhookEventStatus.PROCESSED
        event.recovery_case_id = recovery_case_id
        event.resource_id = resource_id
        event.reconciliation_snapshot = reconciliation_snapshot
        event.last_error = None
        event.processed_at = datetime.now(timezone.utc)
        self.session.commit()

    def mark_failed(self, event: WebhookEvent, error_code: str) -> None:
        event.status = WebhookEventStatus.FAILED
        event.last_error = error_code[:255]
        event.processed_at = datetime.now(timezone.utc)
        self.session.commit()
