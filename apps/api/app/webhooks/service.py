from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.enums import WebhookEventStatus
from app.integrations.payment_gateway import PaymentGateway
from app.recovery.engine import RecoveryCaseEngine
from app.webhooks.models import RazorpayWebhookEnvelope, WebhookIngestionResult
from app.webhooks.reconciliation import (
    SUPPORTED_EVENTS,
    RazorpayWebhookReconciler,
)
from app.webhooks.repository import WebhookEventRepository

logger = get_logger(__name__)


class WebhookProcessingError(RuntimeError):
    pass


class WebhookIngestionService:
    def __init__(
        self,
        session: Session,
        gateway_factory: Callable[[], PaymentGateway],
        *,
        recovery_window_days: int,
    ) -> None:
        self.repository = WebhookEventRepository(session)
        self.session = session
        self.gateway_factory = gateway_factory
        self.recovery_window_days = recovery_window_days

    def ingest(
        self,
        event_id: str,
        envelope: RazorpayWebhookEnvelope,
    ) -> WebhookIngestionResult:
        event, created = self.repository.record(event_id, envelope)
        if not created and event.status in {
            WebhookEventStatus.PROCESSING,
            WebhookEventStatus.PROCESSED,
            WebhookEventStatus.IGNORED,
        }:
            logger.info(
                "webhook_duplicate_ignored",
                extra={
                    "webhook_event_id": event.event_id,
                    "webhook_event_type": event.event_type,
                },
            )
            return WebhookIngestionResult(
                event_id=event.event_id,
                status=event.status,
                duplicate=True,
            )

        if envelope.event not in SUPPORTED_EVENTS:
            self.repository.mark_ignored(event)
            logger.info(
                "webhook_event_type_ignored",
                extra={
                    "webhook_event_id": event.event_id,
                    "webhook_event_type": event.event_type,
                },
            )
            return WebhookIngestionResult(
                event_id=event.event_id,
                status=WebhookEventStatus.IGNORED,
                duplicate=not created,
            )

        self.repository.mark_processing(event)
        gateway = None
        try:
            gateway = self.gateway_factory()
            result = RazorpayWebhookReconciler(self.session, gateway).reconcile(envelope)
            recovery_case = RecoveryCaseEngine(
                self.session, recovery_window_days=self.recovery_window_days
            ).handle_webhook(
                envelope,
                result,
                event_id=event.event_id,
            )
            recovery_case_id = (
                recovery_case.id
                if recovery_case is not None
                else result.recovery_case_id
            )
            self.repository.mark_processed(
                event,
                recovery_case_id=recovery_case_id,
                resource_id=result.resource_id,
                reconciliation_snapshot=result.snapshot,
            )
            logger.info(
                "webhook_reconciled",
                extra={
                    "webhook_event_id": event.event_id,
                    "webhook_event_type": event.event_type,
                    "case_id": (
                        str(recovery_case_id)
                        if recovery_case_id is not None
                        else None
                    ),
                    "razorpay_resource_id": result.resource_id,
                },
            )
        except Exception as exc:
            self.session.rollback()
            event = self.repository.get(event_id)
            if event is not None:
                self.repository.mark_failed(event, type(exc).__name__)
            logger.warning(
                "webhook_reconciliation_failed",
                extra={
                    "webhook_event_id": event_id,
                    "webhook_event_type": envelope.event,
                },
            )
            raise WebhookProcessingError(
                "Webhook reconciliation failed and can be retried."
            ) from exc
        finally:
            if gateway is not None:
                gateway.close()

        return WebhookIngestionResult(
            event_id=event.event_id,
            status=WebhookEventStatus.PROCESSED,
            duplicate=not created,
        )
