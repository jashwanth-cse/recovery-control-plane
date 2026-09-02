from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditEvent,
    Customer,
    Merchant,
    Order,
    Payment,
    PaymentLink,
    RecoveryCase,
)
from app.domain.enums import (
    AuditActorType,
    CustomerConsentStatus,
    RecoveryCaseStatus,
    SourceType,
)
from app.domain.recovery_case import TERMINAL_STATUSES
from app.webhooks.models import RazorpayWebhookEnvelope
from app.webhooks.reconciliation import ReconciliationResult

ACTIVE_ORDER_STATUSES = frozenset({"created", "attempted"})


class RecoveryCaseEngineError(RuntimeError):
    pass


class RecoveryCaseOwnershipError(RecoveryCaseEngineError):
    pass


class RecoveryCaseEngine:
    def __init__(self, session: Session, *, recovery_window_days: int) -> None:
        self.session = session
        self.recovery_window = timedelta(days=recovery_window_days)

    def handle_webhook(
        self,
        envelope: RazorpayWebhookEnvelope,
        reconciliation: ReconciliationResult,
        *,
        event_id: str,
        now: datetime | None = None,
    ) -> RecoveryCase | None:
        observed_at = now or datetime.now(timezone.utc)
        merchant = self._resolve_merchant(envelope, reconciliation.snapshot)
        resources = self._ensure_resources(merchant, reconciliation.snapshot)
        recovery_case = self._find_correlated_case(reconciliation, resources)

        if envelope.event.startswith("payment."):
            recovery_case = self._handle_payment(
                envelope,
                resources,
                recovery_case,
                merchant,
                event_id,
                observed_at,
            )
        elif envelope.event.startswith("payment_link."):
            recovery_case = self._handle_payment_link(
                resources,
                recovery_case,
                merchant,
                event_id,
                observed_at,
            )

        if recovery_case is not None and recovery_case.status not in TERMINAL_STATUSES:
            if observed_at >= recovery_case.recovery_window_end:
                self._transition(
                    recovery_case,
                    RecoveryCaseStatus.EXPIRED,
                    reason="RECOVERY_WINDOW_EXPIRED",
                    actor=AuditActorType.SYSTEM,
                    reference_id=event_id,
                )
        return recovery_case

    def scan_unpaid_orders(
        self,
        *,
        now: datetime | None = None,
        minimum_age: timedelta,
        merchant_id: UUID | None = None,
    ) -> list[RecoveryCase]:
        observed_at = now or datetime.now(timezone.utc)
        cutoff = observed_at - minimum_age
        statement = (
            select(Order)
            .where(
                Order.status.in_(ACTIVE_ORDER_STATUSES),
                Order.amount_due > 0,
                Order.created_at <= cutoff,
            )
            .order_by(Order.created_at)
        )
        if merchant_id is not None:
            statement = statement.where(Order.merchant_id == merchant_id)

        cases: list[RecoveryCase] = []
        for order in self.session.scalars(statement):
            merchant = self.session.get(Merchant, order.merchant_id)
            if merchant is None:
                continue
            recovery_case = self._get_or_create_case(
                merchant=merchant,
                customer_id=order.customer_id,
                source_type=SourceType.ORDER,
                source_id=order.razorpay_order_id,
                amount_at_risk=order.amount_due,
                currency=order.currency,
                risk_started_at=observed_at,
                trigger="UNPAID_ORDER_SCAN",
                reference_id=order.razorpay_order_id,
            )
            self._apply_initial_stop_conditions(
                recovery_case, merchant, order.customer_id, order.razorpay_order_id
            )
            cases.append(recovery_case)
        return cases

    def expire_due_cases(
        self,
        *,
        now: datetime | None = None,
        merchant_id: UUID | None = None,
    ) -> list[RecoveryCase]:
        observed_at = now or datetime.now(timezone.utc)
        statement = select(RecoveryCase).where(
            RecoveryCase.status.not_in(TERMINAL_STATUSES),
            RecoveryCase.recovery_window_end <= observed_at,
        )
        if merchant_id is not None:
            statement = statement.where(RecoveryCase.merchant_id == merchant_id)
        expired = list(self.session.scalars(statement))
        for recovery_case in expired:
            self._transition(
                recovery_case,
                RecoveryCaseStatus.EXPIRED,
                reason="RECOVERY_WINDOW_EXPIRED",
                actor=AuditActorType.SYSTEM,
                reference_id=None,
            )
        return expired

    def _handle_payment(
        self,
        envelope: RazorpayWebhookEnvelope,
        resources: dict[str, Any],
        recovery_case: RecoveryCase | None,
        merchant: Merchant | None,
        event_id: str,
        observed_at: datetime,
    ) -> RecoveryCase | None:
        payment = resources.get("payment")
        order = resources.get("order")
        if payment is None:
            return recovery_case

        if payment.status == "captured":
            if recovery_case is not None:
                self._transition(
                    recovery_case,
                    RecoveryCaseStatus.RECOVERED,
                    reason="PAYMENT_CAPTURED",
                    actor=AuditActorType.RAZORPAY,
                    reference_id=event_id,
                )
            return recovery_case

        if envelope.event != "payment.failed" or payment.status != "failed":
            return recovery_case
        if order is not None and (order.status == "paid" or order.amount_due <= 0):
            if recovery_case is not None:
                self._transition(
                    recovery_case,
                    RecoveryCaseStatus.RECOVERED,
                    reason="ORDER_ALREADY_PAID",
                    actor=AuditActorType.RAZORPAY,
                    reference_id=event_id,
                )
            return recovery_case
        if merchant is None:
            raise RecoveryCaseOwnershipError(
                "Cannot create a payment Recovery Case without merchant ownership."
            )

        amount_at_risk = payment.amount
        if order is not None and order.amount_due > 0:
            amount_at_risk = min(payment.amount, order.amount_due)
        recovery_case = recovery_case or self._get_or_create_case(
            merchant=merchant,
            customer_id=order.customer_id if order is not None else None,
            source_type=SourceType.PAYMENT,
            source_id=payment.razorpay_payment_id,
            amount_at_risk=amount_at_risk,
            currency=payment.currency,
            risk_started_at=datetime.fromtimestamp(
                envelope.created_at, tz=timezone.utc
            ),
            trigger="PAYMENT_FAILED",
            reference_id=event_id,
        )
        if recovery_case.status not in TERMINAL_STATUSES:
            recovery_case.amount_at_risk = amount_at_risk
        self._apply_initial_stop_conditions(
            recovery_case,
            merchant,
            recovery_case.customer_id,
            event_id,
        )
        return recovery_case

    def _handle_payment_link(
        self,
        resources: dict[str, Any],
        recovery_case: RecoveryCase | None,
        merchant: Merchant | None,
        event_id: str,
        observed_at: datetime,
    ) -> RecoveryCase | None:
        payment_link = resources.get("payment_link")
        payment = resources.get("payment")
        order = resources.get("order")
        if payment_link is None:
            return recovery_case

        if payment_link.status == "paid":
            payment_captured = payment is not None and payment.status == "captured"
            order_paid = order is not None and order.status == "paid"
            if not payment_captured or not order_paid:
                raise RecoveryCaseEngineError(
                    "Paid Payment Link is missing captured payment/order evidence."
                )
            if recovery_case is not None:
                self._transition(
                    recovery_case,
                    RecoveryCaseStatus.RECOVERED,
                    reason="PAYMENT_LINK_PAID_RECONCILED",
                    actor=AuditActorType.RAZORPAY,
                    reference_id=event_id,
                )
            return recovery_case

        if payment_link.status == "cancelled":
            if recovery_case is not None:
                self._transition(
                    recovery_case,
                    RecoveryCaseStatus.STOPPED,
                    reason="PAYMENT_LINK_CANCELLED",
                    actor=AuditActorType.RAZORPAY,
                    reference_id=event_id,
                )
            return recovery_case

        remaining = max(payment_link.amount - payment_link.amount_paid, 0)
        if payment_link.status == "expired" and recovery_case is not None:
            self._transition(
                recovery_case,
                RecoveryCaseStatus.EXPIRED,
                reason="RECOVERY_LINK_EXPIRED",
                actor=AuditActorType.RAZORPAY,
                reference_id=event_id,
            )
            return recovery_case
        if remaining <= 0:
            return recovery_case
        if payment_link.status not in {"partially_paid", "expired"}:
            return recovery_case
        if merchant is None:
            raise RecoveryCaseOwnershipError(
                "Cannot create a Payment Link Recovery Case without merchant ownership."
            )

        recovery_case = self._get_or_create_case(
            merchant=merchant,
            customer_id=order.customer_id if order is not None else None,
            source_type=SourceType.PAYMENT_LINK,
            source_id=payment_link.razorpay_payment_link_id,
            amount_at_risk=remaining,
            currency=payment_link.currency,
            risk_started_at=observed_at,
            trigger="UNPAID_PAYMENT_LINK",
            reference_id=event_id,
        )
        if recovery_case.status not in TERMINAL_STATUSES:
            recovery_case.amount_at_risk = remaining
        payment_link.recovery_case_id = recovery_case.id
        self._apply_initial_stop_conditions(
            recovery_case,
            merchant,
            recovery_case.customer_id,
            event_id,
        )
        return recovery_case

    def _resolve_merchant(
        self,
        envelope: RazorpayWebhookEnvelope,
        snapshot: dict[str, Any],
    ) -> Merchant | None:
        merchants: dict[UUID, Merchant] = {}
        account_merchant = None
        if envelope.account_id:
            account_merchant = self.session.scalar(
                select(Merchant).where(
                    Merchant.razorpay_account_id == envelope.account_id
                )
            )
            if account_merchant is not None:
                merchants[account_merchant.id] = account_merchant

        resource_queries = (
            (Payment, "razorpay_payment_id", snapshot.get("payment")),
            (Order, "razorpay_order_id", snapshot.get("order")),
            (
                PaymentLink,
                "razorpay_payment_link_id",
                snapshot.get("payment_link"),
            ),
        )
        for model, id_field, resource in resource_queries:
            if not resource:
                continue
            local = self.session.scalar(
                select(model).where(getattr(model, id_field) == resource.get("id"))
            )
            if local is not None:
                merchant = self.session.get(Merchant, local.merchant_id)
                if merchant is not None:
                    merchants[merchant.id] = merchant

        if envelope.account_id and account_merchant is None:
            mapped_owners = [
                merchant
                for merchant in merchants.values()
                if merchant.razorpay_account_id is not None
            ]
            if mapped_owners:
                raise RecoveryCaseOwnershipError(
                    "Webhook account does not match local resource ownership."
                )
        if len(merchants) > 1:
            raise RecoveryCaseOwnershipError(
                "Webhook account and local resource ownership do not match."
            )
        return next(iter(merchants.values()), None)

    def _ensure_resources(
        self,
        merchant: Merchant | None,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        resources: dict[str, Any] = {}
        order_data = snapshot.get("order")
        if order_data:
            order = self.session.scalar(
                select(Order).where(Order.razorpay_order_id == order_data["id"])
            )
            if order is None and merchant is not None:
                order = Order(
                    merchant_id=merchant.id,
                    razorpay_order_id=order_data["id"],
                    amount=order_data["amount"],
                    amount_paid=order_data["amount_paid"],
                    amount_due=order_data["amount_due"],
                    currency=order_data["currency"],
                    status=order_data["status"],
                    attempts=order_data.get("attempts", 0),
                )
                self.session.add(order)
                self.session.flush()
            resources["order"] = order

        payment_data = snapshot.get("payment")
        if payment_data:
            payment = self.session.scalar(
                select(Payment).where(
                    Payment.razorpay_payment_id == payment_data["id"]
                )
            )
            if payment is None and merchant is not None:
                payment = Payment(
                    merchant_id=merchant.id,
                    razorpay_payment_id=payment_data["id"],
                    razorpay_order_id=payment_data.get("order_id"),
                    amount=payment_data["amount"],
                    currency=payment_data["currency"],
                    status=payment_data["status"],
                    method=payment_data.get("method"),
                    error_code=payment_data.get("error_code"),
                    error_reason=payment_data.get("error_reason"),
                    error_source=payment_data.get("error_source"),
                    error_step=payment_data.get("error_step"),
                )
                self.session.add(payment)
                self.session.flush()
            resources["payment"] = payment

        link_data = snapshot.get("payment_link")
        if link_data:
            payment_link = self.session.scalar(
                select(PaymentLink).where(
                    PaymentLink.razorpay_payment_link_id == link_data["id"]
                )
            )
            if payment_link is None and merchant is not None:
                order = resources.get("order")
                payment_link = PaymentLink(
                    merchant_id=merchant.id,
                    razorpay_payment_link_id=link_data["id"],
                    order_id=order.id if order is not None else None,
                    amount=link_data["amount"],
                    amount_paid=link_data["amount_paid"],
                    currency=link_data["currency"],
                    status=link_data["status"],
                )
                self.session.add(payment_link)
                self.session.flush()
            resources["payment_link"] = payment_link
        return resources

    def _find_correlated_case(
        self,
        reconciliation: ReconciliationResult,
        resources: dict[str, Any],
    ) -> RecoveryCase | None:
        if reconciliation.recovery_case_id is not None:
            recovery_case = self.session.get(
                RecoveryCase, reconciliation.recovery_case_id
            )
            if recovery_case is not None:
                return recovery_case
        for source_type, key, id_field in (
            (SourceType.PAYMENT_LINK, "payment_link", "razorpay_payment_link_id"),
            (SourceType.PAYMENT, "payment", "razorpay_payment_id"),
            (SourceType.ORDER, "order", "razorpay_order_id"),
        ):
            resource = resources.get(key)
            if resource is None:
                continue
            recovery_case = self.session.scalar(
                select(RecoveryCase).where(
                    RecoveryCase.source_type == source_type,
                    RecoveryCase.source_id == getattr(resource, id_field),
                )
            )
            if recovery_case is not None:
                return recovery_case
        return None

    def _get_or_create_case(
        self,
        *,
        merchant: Merchant,
        customer_id: UUID | None,
        source_type: SourceType,
        source_id: str,
        amount_at_risk: int,
        currency: str,
        risk_started_at: datetime,
        trigger: str,
        reference_id: str,
    ) -> RecoveryCase:
        existing = self.session.scalar(
            select(RecoveryCase).where(
                RecoveryCase.merchant_id == merchant.id,
                RecoveryCase.source_type == source_type,
                RecoveryCase.source_id == source_id,
            )
        )
        if existing is not None:
            return existing

        recovery_case = RecoveryCase(
            merchant_id=merchant.id,
            customer_id=customer_id,
            source_type=source_type,
            source_id=source_id,
            amount_at_risk=amount_at_risk,
            currency=currency,
            status=RecoveryCaseStatus.AT_RISK,
            recovery_window_start=risk_started_at,
            recovery_window_end=risk_started_at + self.recovery_window,
            attempt_count=0,
            contact_count=0,
        )
        recovery_case.validate()
        self.session.add(recovery_case)
        self.session.flush()
        self._audit(
            recovery_case,
            "RECOVERY_CASE_CREATED",
            actor=AuditActorType.SYSTEM,
            snapshot={
                "trigger": trigger,
                "reference_id": reference_id,
                "source_type": source_type.value,
                "source_id": source_id,
                "amount_at_risk": amount_at_risk,
                "currency": currency,
                "recovery_window_end": recovery_case.recovery_window_end.isoformat(),
            },
        )
        return recovery_case

    def _apply_initial_stop_conditions(
        self,
        recovery_case: RecoveryCase,
        merchant: Merchant,
        customer_id: UUID | None,
        reference_id: str,
    ) -> None:
        if recovery_case.status in TERMINAL_STATUSES:
            return
        if merchant.status != "ACTIVE":
            self._transition(
                recovery_case,
                RecoveryCaseStatus.STOPPED,
                reason="MERCHANT_INACTIVE",
                actor=AuditActorType.SYSTEM,
                reference_id=reference_id,
            )
            return
        customer = self.session.get(Customer, customer_id) if customer_id else None
        if customer is not None and customer.consent_status == CustomerConsentStatus.OPTED_OUT:
            self._transition(
                recovery_case,
                RecoveryCaseStatus.STOPPED,
                reason="CUSTOMER_OPTED_OUT",
                actor=AuditActorType.SYSTEM,
                reference_id=reference_id,
            )

    def _transition(
        self,
        recovery_case: RecoveryCase,
        target: RecoveryCaseStatus,
        *,
        reason: str,
        actor: AuditActorType,
        reference_id: str | None,
    ) -> None:
        if recovery_case.status in TERMINAL_STATUSES:
            return
        previous = recovery_case.status
        recovery_case.transition_to(target)
        self._audit(
            recovery_case,
            "RECOVERY_CASE_STATUS_CHANGED",
            actor=actor,
            snapshot={
                "from": previous.value,
                "to": target.value,
                "reason": reason,
                "reference_id": reference_id,
            },
        )

    def _audit(
        self,
        recovery_case: RecoveryCase,
        event_type: str,
        *,
        actor: AuditActorType,
        snapshot: dict[str, Any],
    ) -> None:
        self.session.add(
            AuditEvent(
                recovery_case_id=recovery_case.id,
                event_type=event_type,
                actor_type=actor,
                input_snapshot=snapshot,
            )
        )
