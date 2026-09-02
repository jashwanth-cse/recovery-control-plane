import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.webhooks import get_gateway_factory
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.models import (
    Merchant,
    Order,
    Payment,
    PaymentLink,
    RecoveryCase,
    WebhookEvent,
)
from app.db.session import get_session
from app.domain.enums import RecoveryCaseStatus, SourceType, WebhookEventStatus
from app.integrations.types import (
    OrderDetails,
    OrderStatus,
    PaymentDetails,
    PaymentLinkDetails,
    PaymentLinkStatus,
    PaymentStatus,
)
from app.main import create_app
from app.webhooks.security import verify_razorpay_signature

WEBHOOK_SECRET = "webhook-secret-for-tests"
PREVIOUS_SECRET = "previous-webhook-secret"


class FakeGateway:
    def __init__(self) -> None:
        self.payment_calls = 0
        self.order_calls = 0
        self.payment_link_calls = 0
        self.close_calls = 0
        self.fail_next_payment = False
        self.payment_status = PaymentStatus.CAPTURED
        self.order_status = OrderStatus.PAID
        self.order_amount_paid = 499900
        self.order_amount_due = 0

    def get_payment(self, payment_id: str) -> PaymentDetails:
        self.payment_calls += 1
        if self.fail_next_payment:
            self.fail_next_payment = False
            raise RuntimeError("simulated provider outage")
        return PaymentDetails(
            id=payment_id,
            entity="payment",
            amount=499900,
            currency="INR",
            status=self.payment_status,
            order_id="order_webhook123",
            method="card",
            captured=self.payment_status is PaymentStatus.CAPTURED,
        )

    def get_order(self, order_id: str) -> OrderDetails:
        self.order_calls += 1
        return OrderDetails(
            id=order_id,
            entity="order",
            amount=499900,
            amount_paid=self.order_amount_paid,
            amount_due=self.order_amount_due,
            currency="INR",
            status=self.order_status,
            attempts=2,
        )

    def get_payment_link(self, payment_link_id: str) -> PaymentLinkDetails:
        self.payment_link_calls += 1
        return PaymentLinkDetails(
            id=payment_link_id,
            entity="payment_link",
            amount=499900,
            amount_paid=499900,
            currency="INR",
            status=PaymentLinkStatus.PAID,
            short_url="https://rzp.io/i/test",
        )

    def create_payment_link(self, request):
        raise AssertionError("Webhook ingestion must not create Payment Links.")

    def notify_payment_link(self, payment_link_id, medium):
        raise AssertionError("Webhook ingestion must not send notifications.")

    def cancel_payment_link(self, payment_link_id):
        raise AssertionError("Webhook ingestion must not cancel Payment Links.")

    def close(self) -> None:
        self.close_calls += 1


@pytest.fixture()
def database():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return session_factory


@pytest.fixture()
def gateway():
    return FakeGateway()


@pytest.fixture()
def client(database, gateway):
    settings = Settings(
        _env_file=None,
        razorpay_webhook_secret=WEBHOOK_SECRET,
        razorpay_webhook_previous_secret=PREVIOUS_SECRET,
    )
    app = create_app()

    def session_override():
        with database() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_gateway_factory] = lambda: lambda: gateway
    with TestClient(app) as test_client:
        yield test_client


def seed_payment_case(database):
    now = datetime.now(timezone.utc)
    with database() as session:
        merchant = Merchant(name="Webhook Merchant", status="ACTIVE")
        session.add(merchant)
        session.flush()
        order = Order(
            merchant_id=merchant.id,
            razorpay_order_id="order_webhook123",
            amount=499900,
            currency="INR",
            amount_paid=0,
            amount_due=499900,
            status="attempted",
            attempts=1,
        )
        payment = Payment(
            merchant_id=merchant.id,
            razorpay_payment_id="pay_webhook123",
            razorpay_order_id=order.razorpay_order_id,
            amount=499900,
            currency="INR",
            status="failed",
            method="card",
        )
        recovery_case = RecoveryCase(
            merchant_id=merchant.id,
            source_type=SourceType.PAYMENT,
            source_id=payment.razorpay_payment_id,
            amount_at_risk=499900,
            currency="INR",
            status=RecoveryCaseStatus.AT_RISK,
            recovery_window_start=now,
            recovery_window_end=now + timedelta(days=14),
            attempt_count=0,
            contact_count=0,
        )
        session.add_all([order, payment, recovery_case])
        session.commit()
        return recovery_case.id


def seed_payment_link(database):
    case_id = seed_payment_case(database)
    with database() as session:
        recovery_case = session.get(RecoveryCase, case_id)
        order = session.scalar(
            select(Order).where(Order.razorpay_order_id == "order_webhook123")
        )
        payment_link = PaymentLink(
            merchant_id=recovery_case.merchant_id,
            razorpay_payment_link_id="plink_webhook123",
            order_id=order.id,
            recovery_case_id=case_id,
            amount=499900,
            currency="INR",
            status="created",
        )
        session.add(payment_link)
        session.commit()
    return case_id


def payload(event: str) -> bytes:
    entities = {}
    if event.startswith("payment_link."):
        entities["payment_link"] = {"entity": {"id": "plink_webhook123"}}
        if event in {"payment_link.paid", "payment_link.partially_paid"}:
            entities["payment"] = {"entity": {"id": "pay_webhook123"}}
            entities["order"] = {"entity": {"id": "order_webhook123"}}
    elif event.startswith("payment."):
        entities["payment"] = {"entity": {"id": "pay_webhook123"}}
    else:
        entities["unrelated"] = {"entity": {"id": "other_123"}}
    return json.dumps(
        {
            "entity": "event",
            "account_id": "acc_test123",
            "event": event,
            "contains": list(entities),
            "payload": entities,
            "created_at": int(datetime.now(timezone.utc).timestamp()),
        },
        separators=(",", ":"),
    ).encode()


def signature(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def deliver(client, body: bytes, event_id: str, secret: str = WEBHOOK_SECRET):
    return client.post(
        "/webhooks/razorpay",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature(body, secret),
            "x-razorpay-event-id": event_id,
        },
    )


def test_signature_verification_uses_raw_body_and_supports_rotated_secret():
    body = payload("payment.failed")

    assert verify_razorpay_signature(
        body, signature(body, PREVIOUS_SECRET), [WEBHOOK_SECRET, PREVIOUS_SECRET]
    )
    assert not verify_razorpay_signature(
        body + b" ", signature(body), [WEBHOOK_SECRET]
    )


def test_endpoint_accepts_previous_secret_during_rotation(client):
    response = deliver(
        client,
        payload("refund.processed"),
        "event_previous_secret",
        PREVIOUS_SECRET,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "IGNORED"


def test_invalid_signature_is_rejected_before_persistence(client, database, gateway):
    body = payload("payment.failed")
    response = client.post(
        "/webhooks/razorpay",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": "invalid",
            "x-razorpay-event-id": "event_invalid_signature",
        },
    )

    assert response.status_code == 401
    with database() as session:
        assert session.scalar(select(func.count()).select_from(WebhookEvent)) == 0
    assert gateway.payment_calls == 0


def test_duplicate_delivery_is_persisted_and_processed_once(client, database, gateway):
    case_id = seed_payment_case(database)
    body = payload("payment.failed")

    first = deliver(client, body, "event_duplicate123")
    second = deliver(client, body, "event_duplicate123")

    assert first.status_code == 200
    assert first.json() == {
        "event_id": "event_duplicate123",
        "status": "PROCESSED",
        "duplicate": False,
    }
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert gateway.payment_calls == 1
    assert gateway.order_calls == 1
    with database() as session:
        events = list(session.scalars(select(WebhookEvent)))
        assert len(events) == 1
        assert events[0].recovery_case_id == case_id
        assert events[0].processing_attempts == 1


def test_failed_payment_webhook_creates_persistent_recovery_case(
    client, database, gateway
):
    with database() as session:
        session.add(
            Merchant(
                name="Mapped Webhook Merchant",
                status="ACTIVE",
                razorpay_account_id="acc_test123",
            )
        )
        session.commit()
    gateway.payment_status = PaymentStatus.FAILED
    gateway.order_status = OrderStatus.ATTEMPTED
    gateway.order_amount_paid = 0
    gateway.order_amount_due = 499900

    response = deliver(
        client, payload("payment.failed"), "event_creates_case123"
    )

    assert response.status_code == 200
    with database() as session:
        recovery_case = session.scalar(
            select(RecoveryCase).where(
                RecoveryCase.source_type == SourceType.PAYMENT,
                RecoveryCase.source_id == "pay_webhook123",
            )
        )
        event = session.scalar(
            select(WebhookEvent).where(
                WebhookEvent.event_id == "event_creates_case123"
            )
        )
        assert recovery_case is not None
        assert recovery_case.status is RecoveryCaseStatus.AT_RISK
        assert recovery_case.amount_at_risk == 499900
        assert event.recovery_case_id == recovery_case.id


def test_out_of_order_failure_does_not_regress_reconciled_captured_state(
    client, database, gateway
):
    seed_payment_case(database)

    captured = deliver(
        client, payload("payment.captured"), "event_captured_first"
    )
    late_failure = deliver(
        client, payload("payment.failed"), "event_failed_late"
    )

    assert captured.status_code == 200
    assert late_failure.status_code == 200
    with database() as session:
        payment = session.scalar(
            select(Payment).where(Payment.razorpay_payment_id == "pay_webhook123")
        )
        order = session.scalar(
            select(Order).where(Order.razorpay_order_id == "order_webhook123")
        )
        events = list(
            session.scalars(select(WebhookEvent).order_by(WebhookEvent.event_id))
        )
        assert payment.status == "captured"
        assert order.status == "paid"
        assert len(events) == 2
        assert all(
            event.reconciliation_snapshot["payment"]["status"] == "captured"
            for event in events
        )


def test_payment_link_event_reconciles_all_critical_resources(
    client, database, gateway
):
    case_id = seed_payment_link(database)

    response = deliver(
        client, payload("payment_link.paid"), "event_link_paid123"
    )

    assert response.status_code == 200
    assert gateway.payment_link_calls == 1
    assert gateway.payment_calls == 1
    assert gateway.order_calls == 1
    with database() as session:
        event = session.scalar(
            select(WebhookEvent).where(
                WebhookEvent.event_id == "event_link_paid123"
            )
        )
        payment_link = session.scalar(
            select(PaymentLink).where(
                PaymentLink.razorpay_payment_link_id == "plink_webhook123"
            )
        )
        assert event.recovery_case_id == case_id
        assert set(event.reconciliation_snapshot) == {
            "payment_link",
            "payment",
            "order",
        }
        assert payment_link.status == "paid"


def test_unsupported_signed_event_is_safely_ignored(client, database, gateway):
    response = deliver(
        client, payload("refund.processed"), "event_unsupported123"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "IGNORED"
    assert gateway.payment_calls == 0
    assert gateway.payment_link_calls == 0
    with database() as session:
        event = session.scalar(
            select(WebhookEvent).where(
                WebhookEvent.event_id == "event_unsupported123"
            )
        )
        assert event.status is WebhookEventStatus.IGNORED


@pytest.mark.parametrize(
    "event_type",
    [
        "payment.failed",
        "payment.authorized",
        "payment.captured",
        "payment_link.paid",
        "payment_link.partially_paid",
        "payment_link.cancelled",
        "payment_link.expired",
    ],
)
def test_each_supported_event_type_routes_to_reconciliation(client, event_type):
    response = deliver(
        client,
        payload(event_type),
        f"event_supported_{event_type.replace('.', '_')}",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "PROCESSED"


def test_failed_reconciliation_is_retried_on_duplicate_delivery(
    client, database, gateway
):
    seed_payment_case(database)
    gateway.fail_next_payment = True
    body = payload("payment.failed")

    failed = deliver(client, body, "event_retry123")
    retried = deliver(client, body, "event_retry123")

    assert failed.status_code == 503
    assert retried.status_code == 200
    assert retried.json() == {
        "event_id": "event_retry123",
        "status": "PROCESSED",
        "duplicate": True,
    }
    with database() as session:
        event = session.scalar(
            select(WebhookEvent).where(WebhookEvent.event_id == "event_retry123")
        )
        assert event.processing_attempts == 2
        assert event.status is WebhookEventStatus.PROCESSED
        assert event.last_error is None
