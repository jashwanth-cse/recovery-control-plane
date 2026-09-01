from typing import Protocol, runtime_checkable

from app.integrations.types import (
    CreatePaymentLinkRequest,
    NotificationMedium,
    NotificationResult,
    OrderDetails,
    PaymentDetails,
    PaymentLinkDetails,
)


@runtime_checkable
class PaymentGateway(Protocol):
    """Provider-neutral payment capabilities used by application services."""

    def get_order(self, order_id: str) -> OrderDetails: ...

    def get_payment(self, payment_id: str) -> PaymentDetails: ...

    def create_payment_link(
        self, request: CreatePaymentLinkRequest
    ) -> PaymentLinkDetails: ...

    def notify_payment_link(
        self,
        payment_link_id: str,
        medium: NotificationMedium,
    ) -> NotificationResult: ...

    def cancel_payment_link(self, payment_link_id: str) -> PaymentLinkDetails: ...

    def close(self) -> None: ...
