from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.models import (
    AuditEvent,
    Customer,
    Merchant,
    Order,
    PaymentLink,
    RecoveryCase,
)
from app.db.session import get_session
from app.domain.enums import (
    CustomerConsentStatus,
    RecoveryCaseStatus,
    SourceType,
)
from app.main import create_app
from app.recovery.engine import RecoveryCaseEngine, RecoveryCaseOwnershipError
from app.repositories.recovery_cases import RecoveryCaseRepository
from app.webhooks.models import RazorpayWebhookEnvelope
from app.webhooks.reconciliation import ReconciliationResult


def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def merchant(session, *, status="ACTIVE", account_id="acc_case_engine"):
    value = Merchant(
        name=f"{status.title()} Merchant",
        status=status,
        razorpay_account_id=account_id,
    )
    session.add(value)
    session.flush()
    return value


def envelope(
    event: str,
    now: datetime,
    *,
    account_id: str = "acc_case_engine",
) -> RazorpayWebhookEnvelope:
    entity_name = "payment_link" if event.startswith("payment_link.") else "payment"
    resource_id = "plink_case123" if entity_name == "payment_link" else "pay_case123"
    return RazorpayWebhookEnvelope.model_validate(
        {
            "entity": "event",
            "account_id": account_id,
            "event": event,
            "contains": [entity_name],
            "payload": {entity_name: {"entity": {"id": resource_id}}},
            "created_at": int(now.timestamp()),
        }
    )


def failed_snapshot() -> dict:
    return {
        "payment": {
            "id": "pay_case123",
            "status": "failed",
            "amount": 5000,
            "currency": "INR",
            "captured": False,
            "order_id": "order_case123",
            "method": "card",
            "error_code": "BAD_REQUEST_ERROR",
            "error_reason": "payment_failed",
            "error_source": "bank",
            "error_step": "payment_authorization",
        },
        "order": {
            "id": "order_case123",
            "status": "attempted",
            "amount": 5000,
            "amount_paid": 1000,
            "amount_due": 4000,
            "currency": "INR",
            "attempts": 1,
        },
    }


def test_failed_payment_creates_idempotent_case_with_amount_due_and_audit():
    factory = session_factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        owner = merchant(session)
        result = ReconciliationResult(
            resource_id="pay_case123",
            recovery_case_id=None,
            snapshot=failed_snapshot(),
        )
        engine = RecoveryCaseEngine(session, recovery_window_days=14)

        first = engine.handle_webhook(
            envelope("payment.failed", now), result, event_id="event_case_1", now=now
        )
        second = engine.handle_webhook(
            envelope("payment.failed", now), result, event_id="event_case_2", now=now
        )
        session.commit()

        assert first.id == second.id
        assert first.merchant_id == owner.id
        assert first.source_type is SourceType.PAYMENT
        assert first.amount_at_risk == 4000
        assert first.status is RecoveryCaseStatus.AT_RISK
        assert first.recovery_window_end == first.recovery_window_start + timedelta(
            days=14
        )
        assert session.scalar(select(func.count()).select_from(RecoveryCase)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_opted_out_customer_creates_stopped_case():
    factory = session_factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        owner = merchant(session)
        customer = Customer(
            merchant_id=owner.id,
            consent_status=CustomerConsentStatus.OPTED_OUT,
        )
        session.add(customer)
        session.flush()
        session.add(
            Order(
                merchant_id=owner.id,
                customer_id=customer.id,
                razorpay_order_id="order_case123",
                amount=5000,
                amount_paid=1000,
                amount_due=4000,
                currency="INR",
                status="attempted",
                attempts=1,
            )
        )
        session.flush()
        result = ReconciliationResult(
            resource_id="pay_case123",
            recovery_case_id=None,
            snapshot=failed_snapshot(),
        )

        recovery_case = RecoveryCaseEngine(
            session, recovery_window_days=14
        ).handle_webhook(
            envelope("payment.failed", now),
            result,
            event_id="event_opted_out",
            now=now,
        )
        session.commit()

        assert recovery_case.status is RecoveryCaseStatus.STOPPED
        audits = list(
            session.scalars(select(AuditEvent).order_by(AuditEvent.timestamp))
        )
        assert [audit.event_type for audit in audits] == [
            "RECOVERY_CASE_CREATED",
            "RECOVERY_CASE_STATUS_CHANGED",
        ]
        assert audits[-1].input_snapshot["reason"] == "CUSTOMER_OPTED_OUT"


def test_conflicting_webhook_account_cannot_use_a_mapped_local_resource():
    factory = session_factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        owner = merchant(session)
        session.add(
            Order(
                merchant_id=owner.id,
                razorpay_order_id="order_case123",
                amount=5000,
                amount_paid=1000,
                amount_due=4000,
                currency="INR",
                status="attempted",
                attempts=1,
            )
        )
        session.flush()

        with pytest.raises(RecoveryCaseOwnershipError):
            RecoveryCaseEngine(
                session, recovery_window_days=14
            ).handle_webhook(
                envelope(
                    "payment.failed", now, account_id="acc_untrusted"
                ),
                ReconciliationResult(
                    resource_id="pay_case123",
                    recovery_case_id=None,
                    snapshot=failed_snapshot(),
                ),
                event_id="event_wrong_account",
                now=now,
            )

        assert session.scalar(select(func.count()).select_from(RecoveryCase)) == 0


def test_unpaid_order_scan_is_idempotent_and_skips_recent_or_paid_orders():
    factory = session_factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        owner = merchant(session)
        eligible = Order(
            merchant_id=owner.id,
            razorpay_order_id="order_abandoned",
            amount=7000,
            amount_paid=1000,
            amount_due=6000,
            currency="INR",
            status="created",
            attempts=0,
            created_at=now - timedelta(hours=2),
        )
        recent = Order(
            merchant_id=owner.id,
            razorpay_order_id="order_recent",
            amount=7000,
            amount_paid=0,
            amount_due=7000,
            currency="INR",
            status="created",
            attempts=0,
            created_at=now - timedelta(minutes=5),
        )
        paid = Order(
            merchant_id=owner.id,
            razorpay_order_id="order_paid",
            amount=7000,
            amount_paid=7000,
            amount_due=0,
            currency="INR",
            status="paid",
            attempts=1,
            created_at=now - timedelta(hours=2),
        )
        session.add_all([eligible, recent, paid])
        session.flush()
        engine = RecoveryCaseEngine(session, recovery_window_days=14)

        first = engine.scan_unpaid_orders(
            now=now, minimum_age=timedelta(minutes=30)
        )
        second = engine.scan_unpaid_orders(
            now=now, minimum_age=timedelta(minutes=30)
        )
        session.commit()

        assert [case.source_id for case in first] == ["order_abandoned"]
        assert first[0].amount_at_risk == 6000
        assert second[0].id == first[0].id
        assert session.scalar(select(func.count()).select_from(RecoveryCase)) == 1


def test_expiration_is_persisted_and_terminal():
    factory = session_factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        owner = merchant(session)
        recovery_case = RecoveryCase(
            merchant_id=owner.id,
            source_type=SourceType.ORDER,
            source_id="order_expired",
            amount_at_risk=2000,
            currency="INR",
            status=RecoveryCaseStatus.AT_RISK,
            recovery_window_start=now - timedelta(days=15),
            recovery_window_end=now - timedelta(days=1),
            attempt_count=0,
            contact_count=0,
        )
        session.add(recovery_case)
        session.flush()

        expired = RecoveryCaseEngine(
            session, recovery_window_days=14
        ).expire_due_cases(now=now)
        session.commit()

        assert expired == [recovery_case]
        assert recovery_case.status is RecoveryCaseStatus.EXPIRED
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_payment_link_outcomes_update_linked_case_without_reopening_terminal_case():
    factory = session_factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        owner = merchant(session)
        recovery_case = RecoveryCase(
            merchant_id=owner.id,
            source_type=SourceType.PAYMENT,
            source_id="pay_original",
            amount_at_risk=5000,
            currency="INR",
            status=RecoveryCaseStatus.EXECUTING,
            recovery_window_start=now,
            recovery_window_end=now + timedelta(days=14),
            attempt_count=1,
            contact_count=1,
        )
        session.add(recovery_case)
        session.flush()
        snapshot = {
            "payment_link": {
                "id": "plink_case123",
                "status": "paid",
                "amount": 5000,
                "amount_paid": 5000,
                "currency": "INR",
            },
            "payment": {
                "id": "pay_recovery",
                "status": "captured",
                "amount": 5000,
                "currency": "INR",
                "captured": True,
                "order_id": "order_recovery",
            },
            "order": {
                "id": "order_recovery",
                "status": "paid",
                "amount": 5000,
                "amount_paid": 5000,
                "amount_due": 0,
                "currency": "INR",
                "attempts": 1,
            },
        }
        result = ReconciliationResult(
            resource_id="plink_case123",
            recovery_case_id=recovery_case.id,
            snapshot=snapshot,
        )
        engine = RecoveryCaseEngine(session, recovery_window_days=14)

        paid_case = engine.handle_webhook(
            envelope("payment_link.paid", now),
            result,
            event_id="event_link_paid",
            now=now,
        )
        paid_case = engine.handle_webhook(
            envelope("payment_link.cancelled", now),
            result,
            event_id="event_link_cancelled_late",
            now=now,
        )
        session.commit()

        assert paid_case.status is RecoveryCaseStatus.RECOVERED


def test_partially_paid_payment_link_creates_case_for_remaining_amount():
    factory = session_factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        owner = merchant(session)
        result = ReconciliationResult(
            resource_id="plink_case123",
            recovery_case_id=None,
            snapshot={
                "payment_link": {
                    "id": "plink_case123",
                    "status": "partially_paid",
                    "amount": 9000,
                    "amount_paid": 3500,
                    "currency": "INR",
                }
            },
        )

        recovery_case = RecoveryCaseEngine(
            session, recovery_window_days=14
        ).handle_webhook(
            envelope("payment_link.partially_paid", now),
            result,
            event_id="event_link_partial",
            now=now,
        )
        session.commit()

        payment_link = session.scalar(
            select(PaymentLink).where(
                PaymentLink.razorpay_payment_link_id == "plink_case123"
            )
        )
        assert recovery_case.source_type is SourceType.PAYMENT_LINK
        assert recovery_case.amount_at_risk == 5500
        assert recovery_case.status is RecoveryCaseStatus.AT_RISK
        assert payment_link.recovery_case_id == recovery_case.id


def test_active_case_api_expires_overdue_cases_and_returns_only_active():
    factory = session_factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        owner = merchant(session)
        active = RecoveryCase(
            merchant_id=owner.id,
            source_type=SourceType.ORDER,
            source_id="order_active",
            amount_at_risk=1000,
            currency="INR",
            status=RecoveryCaseStatus.AT_RISK,
            recovery_window_start=now,
            recovery_window_end=now + timedelta(days=1),
            attempt_count=0,
            contact_count=0,
        )
        overdue = RecoveryCase(
            merchant_id=owner.id,
            source_type=SourceType.ORDER,
            source_id="order_overdue",
            amount_at_risk=1000,
            currency="INR",
            status=RecoveryCaseStatus.AT_RISK,
            recovery_window_start=now - timedelta(days=2),
            recovery_window_end=now - timedelta(days=1),
            attempt_count=0,
            contact_count=0,
        )
        session.add_all([active, overdue])
        session.commit()
        merchant_id = owner.id

    app = create_app()

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    with TestClient(app) as client:
        response = client.get(
            "/api/cases",
            params={"active_only": "true", "merchant_id": str(merchant_id)},
        )

    assert response.status_code == 200
    assert [item["source_id"] for item in response.json()] == ["order_active"]
    with factory() as session:
        overdue = session.scalar(
            select(RecoveryCase).where(
                RecoveryCase.source_id == "order_overdue"
            )
        )
        assert overdue.status is RecoveryCaseStatus.EXPIRED
        assert RecoveryCaseRepository(session).list_active(
            merchant_id=merchant_id
        )
