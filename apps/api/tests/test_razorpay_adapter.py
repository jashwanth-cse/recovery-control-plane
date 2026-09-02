import base64
import json

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.integrations.payment_gateway import PaymentGateway
from app.integrations.razorpay import create_razorpay_gateway
from app.integrations.razorpay.errors import (
    RazorpayAPIError,
    RazorpayAuthenticationError,
    RazorpayConfigurationError,
    RazorpayRateLimitError,
    RazorpayRequestValidationError,
    RazorpayResponseValidationError,
    RazorpayServiceError,
)
from app.integrations.types import (
    CreatePaymentLinkRequest,
    NotificationMedium,
    OrderStatus,
    PaymentLinkCustomer,
    PaymentLinkNotify,
    PaymentLinkStatus,
    PaymentStatus,
)

KEY_ID = "rzp_test_contractkey"
KEY_SECRET = "contract-secret-never-log"


def settings(**overrides) -> Settings:
    values = {
        "razorpay_key_id": KEY_ID,
        "razorpay_key_secret": KEY_SECRET,
        "razorpay_api_base_url": "https://api.razorpay.com/v1",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def gateway_for(handler):
    return create_razorpay_gateway(
        settings(), transport=httpx.MockTransport(handler)
    )


def assert_basic_auth(request: httpx.Request) -> None:
    token = base64.b64encode(f"{KEY_ID}:{KEY_SECRET}".encode()).decode()
    assert request.headers["Authorization"] == f"Basic {token}"


def payment_link_response(status: str = "created") -> dict:
    return {
        "id": "plink_contract123",
        "entity": "payment_link",
        "amount": 499900,
        "amount_paid": 0,
        "currency": "INR",
        "status": status,
        "reference_id": "recovery-case-123",
        "short_url": "https://rzp.io/i/example",
        "accept_partial": False,
        "created_at": 1760000000,
    }


def test_gateway_implements_provider_neutral_contract():
    gateway = gateway_for(
        lambda request: httpx.Response(200, json=payment_link_response())
    )

    assert isinstance(gateway, PaymentGateway)
    gateway.close()


def test_settings_redact_key_secret():
    assert KEY_SECRET not in repr(settings())


def test_fetch_order_uses_verified_contract_and_returns_typed_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/orders/order_contract123"
        assert_basic_auth(request)
        return httpx.Response(
            200,
            json={
                "id": "order_contract123",
                "entity": "order",
                "amount": 499900,
                "amount_paid": 0,
                "amount_due": 499900,
                "currency": "INR",
                "receipt": "receipt-123",
                "status": "attempted",
                "attempts": 1,
                "notes": {},
                "created_at": 1760000000,
            },
        )

    with gateway_for(handler) as gateway:
        order = gateway.get_order("order_contract123")

    assert order.status is OrderStatus.ATTEMPTED
    assert order.amount_due == 499900


def test_fetch_payment_uses_verified_contract_and_returns_failure_details():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/payments/pay_contract123"
        assert_basic_auth(request)
        return httpx.Response(
            200,
            json={
                "id": "pay_contract123",
                "entity": "payment",
                "amount": 499900,
                "currency": "INR",
                "status": "failed",
                "order_id": "order_contract123",
                "method": "card",
                "captured": False,
                "error_code": "BAD_REQUEST_ERROR",
                "error_description": "Payment failed.",
                "error_source": "bank",
                "error_step": "payment_authorization",
                "error_reason": "payment_failed",
                "created_at": 1760000000,
            },
        )

    with gateway_for(handler) as gateway:
        payment = gateway.get_payment("pay_contract123")

    assert payment.status is PaymentStatus.FAILED
    assert payment.error_source == "bank"


def test_fetch_payment_link_uses_verified_contract():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/payment_links/plink_contract123"
        assert_basic_auth(request)
        response = payment_link_response("paid")
        response["customer"] = []
        response["notify"] = {"sms": True, "email": True, "whatsapp": False}
        response["payments"] = None
        return httpx.Response(200, json=response)

    with gateway_for(handler) as gateway:
        payment_link = gateway.get_payment_link("plink_contract123")

    assert payment_link.status is PaymentLinkStatus.PAID
    assert payment_link.customer == []


def test_create_recovery_payment_link_sends_only_supported_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/payment_links"
        assert_basic_auth(request)
        assert json.loads(request.content) == {
            "amount": 499900,
            "currency": "INR",
            "reference_id": "recovery-case-123",
            "description": "Recovery for unpaid order",
            "accept_partial": False,
            "customer": {
                "name": "Test Customer",
                "contact": "+919999999999",
                "email": "customer@example.com",
            },
            "notify": {"sms": True, "email": True},
            "expire_by": 1761000000,
            "notes": {"recovery_case_id": "case-123"},
            "callback_url": "https://merchant.example/recovery/callback",
            "callback_method": "get",
            "reminder_enable": False,
        }
        return httpx.Response(200, json=payment_link_response())

    request = CreatePaymentLinkRequest(
        amount=499900,
        currency="inr",
        reference_id="recovery-case-123",
        description="Recovery for unpaid order",
        customer=PaymentLinkCustomer(
            name="Test Customer",
            contact="+919999999999",
            email="customer@example.com",
        ),
        notify=PaymentLinkNotify(sms=True, email=True),
        expire_by=1761000000,
        notes={"recovery_case_id": "case-123"},
        callback_url="https://merchant.example/recovery/callback",
        callback_method="get",
    )

    with gateway_for(handler) as gateway:
        payment_link = gateway.create_payment_link(request)

    assert payment_link.status is PaymentLinkStatus.CREATED
    assert payment_link.short_url == "https://rzp.io/i/example"


@pytest.mark.parametrize("medium", [NotificationMedium.SMS, NotificationMedium.EMAIL])
def test_notify_payment_link_uses_supported_medium(medium):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == (
            f"/v1/payment_links/plink_contract123/notify_by/{medium.value}"
        )
        assert_basic_auth(request)
        return httpx.Response(200, json={"success": True})

    with gateway_for(handler) as gateway:
        result = gateway.notify_payment_link("plink_contract123", medium)

    assert result.success is True


def test_cancel_payment_link_uses_post_contract():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/payment_links/plink_contract123/cancel"
        assert_basic_auth(request)
        return httpx.Response(200, json=payment_link_response("cancelled"))

    with gateway_for(handler) as gateway:
        payment_link = gateway.cancel_payment_link("plink_contract123")

    assert payment_link.status is PaymentLinkStatus.CANCELLED


@pytest.mark.parametrize(
    ("status_code", "error_type", "retryable"),
    [
        (401, RazorpayAuthenticationError, False),
        (429, RazorpayRateLimitError, True),
        (503, RazorpayServiceError, True),
        (400, RazorpayAPIError, False),
    ],
)
def test_api_errors_are_normalized(status_code, error_type, retryable):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={
                "error": {
                    "code": "BAD_REQUEST_ERROR",
                    "description": "Normalized provider failure.",
                    "secret": KEY_SECRET,
                }
            },
        )

    with gateway_for(handler) as gateway:
        with pytest.raises(error_type) as captured:
            gateway.get_order("order_contract123")

    error = captured.value
    assert error.status_code == status_code
    assert error.code == "BAD_REQUEST_ERROR"
    assert error.retryable is retryable
    assert KEY_SECRET not in str(error)
    assert KEY_SECRET not in repr(error)


def test_invalid_provider_response_is_rejected_without_exposing_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "order_contract123", "pii": "hidden"})

    with gateway_for(handler) as gateway:
        with pytest.raises(RazorpayResponseValidationError) as captured:
            gateway.get_order("order_contract123")

    assert "pii" not in str(captured.value)
    assert "hidden" not in str(captured.value)


def test_resource_ids_are_validated_before_request():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    with gateway_for(handler) as gateway:
        with pytest.raises(RazorpayRequestValidationError):
            gateway.get_payment("../payments/pay_unsafe")

    assert called is False


def test_payment_link_request_enforces_partial_payment_contract():
    with pytest.raises(ValidationError):
        CreatePaymentLinkRequest(
            amount=1000,
            currency="INR",
            reference_id="case-123",
            first_min_partial_amount=500,
        )


def test_payment_link_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        CreatePaymentLinkRequest(
            amount=1000,
            currency="INR",
            reference_id="case-123",
            unsupported_action="retry",
        )


def test_missing_credentials_and_live_keys_are_rejected():
    with pytest.raises(RazorpayConfigurationError):
        create_razorpay_gateway(settings(razorpay_key_secret=None))

    with pytest.raises(RazorpayConfigurationError):
        create_razorpay_gateway(settings(razorpay_key_id="rzp_live_forbidden"))
