from enum import Enum
from typing import Any, Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class GatewayModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class OrderStatus(str, Enum):
    CREATED = "created"
    ATTEMPTED = "attempted"
    PAID = "paid"


class PaymentStatus(str, Enum):
    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    REFUNDED = "refunded"
    FAILED = "failed"


class PaymentLinkStatus(str, Enum):
    CREATED = "created"
    PARTIALLY_PAID = "partially_paid"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PAID = "paid"


class NotificationMedium(str, Enum):
    SMS = "sms"
    EMAIL = "email"


class OrderDetails(GatewayModel):
    id: str
    entity: Literal["order"]
    amount: int = Field(ge=0)
    amount_paid: int = Field(ge=0)
    amount_due: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    receipt: str | None = None
    status: OrderStatus
    attempts: int = Field(default=0, ge=0)
    notes: dict[str, Any] | list[Any] = Field(default_factory=dict)
    created_at: int | None = Field(default=None, ge=0)


class PaymentDetails(GatewayModel):
    id: str
    entity: Literal["payment"]
    amount: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    status: PaymentStatus
    order_id: str | None = None
    method: str | None = None
    captured: bool = False
    amount_refunded: int = Field(default=0, ge=0)
    refund_status: str | None = None
    description: str | None = None
    error_code: str | None = None
    error_description: str | None = None
    error_source: str | None = None
    error_step: str | None = None
    error_reason: str | None = None
    invoice_id: str | None = None
    bank: str | None = None
    vpa: str | None = None
    fee: int | None = Field(default=None, ge=0)
    tax: int | None = Field(default=None, ge=0)
    notes: dict[str, Any] | list[Any] = Field(default_factory=dict)
    created_at: int | None = Field(default=None, ge=0)


class PaymentLinkCustomer(GatewayModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=255)
    contact: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=320)


class PaymentLinkNotify(GatewayModel):
    model_config = ConfigDict(extra="forbid")

    sms: bool = False
    email: bool = False


class PaymentLinkCustomerResponse(GatewayModel):
    name: str | None = None
    contact: str | None = None
    email: str | None = None


class PaymentLinkNotifyResponse(GatewayModel):
    sms: bool = False
    email: bool = False


class CreatePaymentLinkRequest(GatewayModel):
    model_config = ConfigDict(extra="forbid")

    amount: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    reference_id: str = Field(min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=2048)
    accept_partial: bool = False
    first_min_partial_amount: int | None = Field(default=None, gt=0)
    customer: PaymentLinkCustomer | None = None
    notify: PaymentLinkNotify | None = None
    expire_by: int | None = Field(default=None, gt=0)
    notes: dict[str, str] = Field(default_factory=dict)
    callback_url: AnyHttpUrl | None = None
    callback_method: Literal["get"] | None = None
    reminder_enable: bool = False

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        if not value.isascii() or not value.isalpha():
            raise ValueError("currency must contain exactly three letters")
        return value.upper()

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 15:
            raise ValueError("notes cannot contain more than 15 entries")
        if any(len(key) > 256 or len(note) > 256 for key, note in value.items()):
            raise ValueError("note keys and values cannot exceed 256 characters")
        return value

    @model_validator(mode="after")
    def validate_link_options(self):
        if self.first_min_partial_amount is not None:
            if not self.accept_partial:
                raise ValueError(
                    "first_min_partial_amount requires accept_partial to be true"
                )
            if self.first_min_partial_amount > self.amount:
                raise ValueError("first_min_partial_amount cannot exceed amount")
        if self.callback_url is None and self.callback_method is not None:
            raise ValueError("callback_method requires callback_url")
        if self.callback_url is not None and self.callback_method != "get":
            raise ValueError("callback_url requires callback_method='get'")
        return self


class PaymentLinkDetails(GatewayModel):
    id: str
    entity: str | None = None
    amount: int = Field(ge=0)
    amount_paid: int = Field(default=0, ge=0)
    currency: str = Field(min_length=3, max_length=3)
    status: PaymentLinkStatus
    reference_id: str | None = None
    short_url: str | None = None
    description: str | None = None
    customer: PaymentLinkCustomerResponse | list[Any] | None = None
    notify: PaymentLinkNotifyResponse | None = None
    accept_partial: bool = False
    first_min_partial_amount: int | None = Field(default=None, ge=0)
    expire_by: int | None = Field(default=None, ge=0)
    expired_at: int | None = Field(default=None, ge=0)
    cancelled_at: int | None = Field(default=None, ge=0)
    created_at: int | None = Field(default=None, ge=0)
    updated_at: int | None = Field(default=None, ge=0)
    reminder_enable: bool = False
    notes: dict[str, Any] = Field(default_factory=dict)
    payments: list[dict[str, Any]] | None = None


class NotificationResult(GatewayModel):
    success: bool
