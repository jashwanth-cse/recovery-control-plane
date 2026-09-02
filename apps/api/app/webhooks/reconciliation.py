from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Order, Payment, PaymentLink, RecoveryCase
from app.domain.enums import SourceType
from app.integrations.payment_gateway import PaymentGateway
from app.integrations.types import OrderDetails, PaymentDetails, PaymentLinkDetails
from app.webhooks.models import RazorpayWebhookEnvelope

PAYMENT_EVENTS = frozenset(
    {"payment.failed", "payment.authorized", "payment.captured"}
)
PAYMENT_LINK_EVENTS = frozenset(
    {
        "payment_link.paid",
        "payment_link.partially_paid",
        "payment_link.cancelled",
        "payment_link.expired",
    }
)
SUPPORTED_EVENTS = PAYMENT_EVENTS | PAYMENT_LINK_EVENTS


class WebhookRoutingError(ValueError):
    pass


@dataclass(frozen=True)
class ReconciliationResult:
    resource_id: str
    recovery_case_id: UUID | None
    snapshot: dict[str, Any]


def _entity(envelope: RazorpayWebhookEnvelope, name: str) -> dict[str, Any] | None:
    container = envelope.payload.get(name)
    return container.entity if container is not None else None


def _required_id(entity: dict[str, Any] | None, entity_name: str) -> str:
    resource_id = entity.get("id") if entity else None
    if not isinstance(resource_id, str) or not resource_id:
        raise WebhookRoutingError(
            f"Supported webhook is missing its {entity_name} id."
        )
    return resource_id


class RazorpayWebhookReconciler:
    def __init__(self, session: Session, gateway: PaymentGateway) -> None:
        self.session = session
        self.gateway = gateway

    def reconcile(self, envelope: RazorpayWebhookEnvelope) -> ReconciliationResult:
        if envelope.event in PAYMENT_EVENTS:
            return self._reconcile_payment_event(envelope)
        if envelope.event in PAYMENT_LINK_EVENTS:
            return self._reconcile_payment_link_event(envelope)
        raise WebhookRoutingError(f"Unsupported webhook event: {envelope.event}")

    def _reconcile_payment_event(
        self, envelope: RazorpayWebhookEnvelope
    ) -> ReconciliationResult:
        payment_id = _required_id(_entity(envelope, "payment"), "payment")
        payment = self.gateway.get_payment(payment_id)
        self._sync_payment(payment)

        order = self.gateway.get_order(payment.order_id) if payment.order_id else None
        if order is not None:
            self._sync_order(order)

        recovery_case = self._find_case(SourceType.PAYMENT, payment.id)
        if recovery_case is None and order is not None:
            recovery_case = self._find_case(SourceType.ORDER, order.id)

        return ReconciliationResult(
            resource_id=payment.id,
            recovery_case_id=recovery_case.id if recovery_case else None,
            snapshot=self._snapshot(payment=payment, order=order),
        )

    def _reconcile_payment_link_event(
        self, envelope: RazorpayWebhookEnvelope
    ) -> ReconciliationResult:
        link_id = _required_id(_entity(envelope, "payment_link"), "payment link")
        payment_link = self.gateway.get_payment_link(link_id)
        local_link = self._sync_payment_link(payment_link)

        payment_entity = _entity(envelope, "payment")
        payment_id = payment_entity.get("id") if payment_entity else None
        payment = (
            self.gateway.get_payment(payment_id)
            if isinstance(payment_id, str) and payment_id
            else None
        )
        if payment is not None:
            self._sync_payment(payment)

        order_entity = _entity(envelope, "order")
        order_id = order_entity.get("id") if order_entity else None
        if not order_id and payment is not None:
            order_id = payment.order_id
        order = (
            self.gateway.get_order(order_id)
            if isinstance(order_id, str) and order_id
            else None
        )
        if order is not None:
            self._sync_order(order)

        recovery_case = None
        if local_link is not None and local_link.recovery_case_id is not None:
            recovery_case = self.session.get(RecoveryCase, local_link.recovery_case_id)
        if recovery_case is None:
            recovery_case = self._find_case(SourceType.PAYMENT_LINK, payment_link.id)
        if recovery_case is None and payment is not None:
            recovery_case = self._find_case(SourceType.PAYMENT, payment.id)
        if recovery_case is None and order is not None:
            recovery_case = self._find_case(SourceType.ORDER, order.id)

        return ReconciliationResult(
            resource_id=payment_link.id,
            recovery_case_id=recovery_case.id if recovery_case else None,
            snapshot=self._snapshot(
                payment_link=payment_link, payment=payment, order=order
            ),
        )

    def _find_case(
        self, source_type: SourceType, source_id: str
    ) -> RecoveryCase | None:
        statement = select(RecoveryCase).where(
            RecoveryCase.source_type == source_type,
            RecoveryCase.source_id == source_id,
        )
        return self.session.scalar(statement)

    def _sync_payment(self, details: PaymentDetails) -> Payment | None:
        payment = self.session.scalar(
            select(Payment).where(Payment.razorpay_payment_id == details.id)
        )
        if payment is None:
            return None
        payment.razorpay_order_id = details.order_id
        payment.amount = details.amount
        payment.currency = details.currency
        payment.status = details.status.value
        payment.method = details.method
        payment.error_code = details.error_code
        payment.error_description = details.error_description
        payment.error_reason = details.error_reason
        payment.error_source = details.error_source
        payment.error_step = details.error_step
        payment.bank = details.bank
        payment.vpa = details.vpa
        payment.invoice_id = details.invoice_id
        return payment

    def _sync_order(self, details: OrderDetails) -> Order | None:
        order = self.session.scalar(
            select(Order).where(Order.razorpay_order_id == details.id)
        )
        if order is None:
            return None
        order.amount = details.amount
        order.amount_paid = details.amount_paid
        order.amount_due = details.amount_due
        order.currency = details.currency
        order.status = details.status.value
        order.attempts = details.attempts
        return order

    def _sync_payment_link(
        self, details: PaymentLinkDetails
    ) -> PaymentLink | None:
        payment_link = self.session.scalar(
            select(PaymentLink).where(
                PaymentLink.razorpay_payment_link_id == details.id
            )
        )
        if payment_link is None:
            return None
        payment_link.amount = details.amount
        payment_link.amount_paid = details.amount_paid
        payment_link.currency = details.currency
        payment_link.status = details.status.value
        payment_link.short_url = details.short_url
        payment_link.expire_by = (
            datetime.fromtimestamp(details.expire_by, tz=timezone.utc)
            if details.expire_by
            else None
        )
        return payment_link

    @staticmethod
    def _snapshot(
        *,
        payment_link: PaymentLinkDetails | None = None,
        payment: PaymentDetails | None = None,
        order: OrderDetails | None = None,
    ) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        if payment_link is not None:
            snapshot["payment_link"] = {
                "id": payment_link.id,
                "status": payment_link.status.value,
                "amount": payment_link.amount,
                "amount_paid": payment_link.amount_paid,
                "currency": payment_link.currency,
            }
        if payment is not None:
            snapshot["payment"] = {
                "id": payment.id,
                "status": payment.status.value,
                "amount": payment.amount,
                "currency": payment.currency,
                "captured": payment.captured,
                "order_id": payment.order_id,
                "method": payment.method,
                "error_code": payment.error_code,
                "error_reason": payment.error_reason,
                "error_source": payment.error_source,
                "error_step": payment.error_step,
            }
        if order is not None:
            snapshot["order"] = {
                "id": order.id,
                "status": order.status.value,
                "amount": order.amount,
                "amount_paid": order.amount_paid,
                "amount_due": order.amount_due,
                "currency": order.currency,
                "attempts": order.attempts,
            }
        return snapshot
