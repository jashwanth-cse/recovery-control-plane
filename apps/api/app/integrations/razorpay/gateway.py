import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.errors import (
    RazorpayRequestValidationError,
    RazorpayResponseValidationError,
)
from app.integrations.types import (
    CreatePaymentLinkRequest,
    NotificationMedium,
    NotificationResult,
    OrderDetails,
    PaymentDetails,
    PaymentLinkDetails,
)

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)
RESOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


def _validated_resource_id(resource_id: str, prefix: str) -> str:
    if (
        len(resource_id) <= len(prefix)
        or not resource_id.startswith(prefix)
        or not RESOURCE_ID_PATTERN.fullmatch(resource_id)
    ):
        raise RazorpayRequestValidationError(
            f"Expected a valid Razorpay {prefix.rstrip('_')} id."
        )
    return resource_id


def _parse_response(
    model: type[ResponseModel], payload: dict, operation: str
) -> ResponseModel:
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise RazorpayResponseValidationError(
            f"Razorpay returned an invalid response for {operation}."
        ) from exc


class RazorpayPaymentGateway:
    def __init__(self, client: RazorpayClient) -> None:
        self._client = client

    def get_order(self, order_id: str) -> OrderDetails:
        resource_id = _validated_resource_id(order_id, "order_")
        payload = self._client.request("GET", f"orders/{resource_id}")
        return _parse_response(OrderDetails, payload, "fetch order")

    def get_payment(self, payment_id: str) -> PaymentDetails:
        resource_id = _validated_resource_id(payment_id, "pay_")
        payload = self._client.request("GET", f"payments/{resource_id}")
        return _parse_response(PaymentDetails, payload, "fetch payment")

    def get_payment_link(self, payment_link_id: str) -> PaymentLinkDetails:
        resource_id = _validated_resource_id(payment_link_id, "plink_")
        payload = self._client.request("GET", f"payment_links/{resource_id}")
        return _parse_response(PaymentLinkDetails, payload, "fetch payment link")

    def create_payment_link(
        self, request: CreatePaymentLinkRequest
    ) -> PaymentLinkDetails:
        payload = self._client.request(
            "POST",
            "payment_links",
            json=request.model_dump(mode="json", exclude_none=True),
        )
        return _parse_response(PaymentLinkDetails, payload, "create payment link")

    def notify_payment_link(
        self,
        payment_link_id: str,
        medium: NotificationMedium,
    ) -> NotificationResult:
        resource_id = _validated_resource_id(payment_link_id, "plink_")
        payload = self._client.request(
            "POST", f"payment_links/{resource_id}/notify_by/{medium.value}"
        )
        return _parse_response(NotificationResult, payload, "notify payment link")

    def cancel_payment_link(self, payment_link_id: str) -> PaymentLinkDetails:
        resource_id = _validated_resource_id(payment_link_id, "plink_")
        payload = self._client.request(
            "POST", f"payment_links/{resource_id}/cancel"
        )
        return _parse_response(PaymentLinkDetails, payload, "cancel payment link")

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
