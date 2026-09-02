from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Enum as SqlEnum
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.domain.enums import (
    ActionType,
    AuditActorType,
    CustomerConsentStatus,
    ExperimentGroup,
    ExperimentStatus,
    RecoveryActionStatus,
    RecoveryCaseStatus,
    SourceType,
    WebhookEventStatus,
)
from app.domain.recovery_case import ensure_valid_case_values, ensure_valid_transition


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def enum_column(enum_class, length: int):
    return SqlEnum(enum_class, native_enum=False, length=length, validate_strings=True)


class Merchant(Base):
    __tablename__ = "merchants"
    __table_args__ = (
        UniqueConstraint(
            "razorpay_account_id", name="uq_merchants_razorpay_account_id"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    razorpay_account_id: Mapped[str | None] = mapped_column(String(255))
    razorpay_key_id: Mapped[str | None] = mapped_column(String(255))
    secret_reference: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    customers: Mapped[list["Customer"]] = relationship(back_populates="merchant")
    recovery_cases: Mapped[list["RecoveryCase"]] = relationship(
        back_populates="merchant"
    )


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint(
            "merchant_id",
            "external_customer_id",
            name="uq_customers_merchant_external_customer_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    external_customer_id: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(32))
    consent_status: Mapped[CustomerConsentStatus] = mapped_column(
        enum_column(CustomerConsentStatus, 16),
        nullable=False,
        default=CustomerConsentStatus.UNKNOWN,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    merchant: Mapped[Merchant] = relationship(back_populates="customers")
    orders: Mapped[list["Order"]] = relationship(back_populates="customer")
    recovery_cases: Mapped[list["RecoveryCase"]] = relationship(
        back_populates="customer"
    )


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("razorpay_order_id", name="uq_orders_razorpay_order_id"),
        CheckConstraint("amount >= 0", name="ck_orders_amount_non_negative"),
        CheckConstraint("amount_paid >= 0", name="ck_orders_amount_paid_non_negative"),
        CheckConstraint("amount_due >= 0", name="ck_orders_amount_due_non_negative"),
        CheckConstraint("attempts >= 0", name="ck_orders_attempts_non_negative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    razorpay_order_id: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id")
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_paid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    amount_due: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    customer: Mapped[Customer | None] = relationship(back_populates="orders")
    merchant: Mapped[Merchant] = relationship()


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("razorpay_payment_id", name="uq_payments_razorpay_payment_id"),
        CheckConstraint("amount >= 0", name="ck_payments_amount_non_negative"),
        Index("ix_payments_razorpay_order_id", "razorpay_order_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    razorpay_payment_id: Mapped[str] = mapped_column(String(255), nullable=False)
    razorpay_order_id: Mapped[str | None] = mapped_column(String(255))
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(255))
    error_description: Mapped[str | None] = mapped_column(Text)
    error_reason: Mapped[str | None] = mapped_column(String(255))
    error_source: Mapped[str | None] = mapped_column(String(255))
    error_step: Mapped[str | None] = mapped_column(String(255))
    bank: Mapped[str | None] = mapped_column(String(64))
    vpa: Mapped[str | None] = mapped_column(String(255))
    invoice_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    merchant: Mapped[Merchant] = relationship()


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (
        CheckConstraint(
            "control_percentage >= 0 and control_percentage <= 100",
            name="ck_experiments_control_percentage_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    control_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ExperimentStatus] = mapped_column(
        enum_column(ExperimentStatus, 16),
        nullable=False,
        default=ExperimentStatus.DRAFT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    merchant: Mapped[Merchant] = relationship()


class RecoveryCase(Base):
    __tablename__ = "recovery_cases"
    __table_args__ = (
        UniqueConstraint(
            "merchant_id",
            "source_type",
            "source_id",
            name="uq_recovery_cases_merchant_source",
        ),
        CheckConstraint(
            "amount_at_risk > 0", name="ck_recovery_cases_amount_at_risk_positive"
        ),
        CheckConstraint(
            "attempt_count >= 0", name="ck_recovery_cases_attempt_count_non_negative"
        ),
        CheckConstraint(
            "contact_count >= 0", name="ck_recovery_cases_contact_count_non_negative"
        ),
        CheckConstraint(
            "recovery_window_end > recovery_window_start",
            name="ck_recovery_cases_window_order",
        ),
        Index("ix_recovery_cases_merchant_status", "merchant_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id")
    )
    source_type: Mapped[SourceType] = mapped_column(
        enum_column(SourceType, 16), nullable=False
    )
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_at_risk: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[RecoveryCaseStatus] = mapped_column(
        enum_column(RecoveryCaseStatus, 32),
        nullable=False,
        default=RecoveryCaseStatus.AT_RISK,
    )
    recovery_window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    recovery_window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    experiment_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("experiments.id")
    )
    experiment_group: Mapped[ExperimentGroup | None] = mapped_column(
        enum_column(ExperimentGroup, 16)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    merchant: Mapped[Merchant] = relationship(back_populates="recovery_cases")
    customer: Mapped[Customer | None] = relationship(back_populates="recovery_cases")
    experiment: Mapped[Experiment | None] = relationship()

    def validate(self) -> None:
        ensure_valid_case_values(
            self.source_type,
            self.source_id,
            self.amount_at_risk,
            self.currency,
            self.recovery_window_start,
            self.recovery_window_end,
        )

    def transition_to(self, target_status: RecoveryCaseStatus) -> None:
        ensure_valid_transition(self.status, target_status)
        self.status = target_status


class PaymentLink(Base):
    __tablename__ = "payment_links"
    __table_args__ = (
        UniqueConstraint(
            "razorpay_payment_link_id",
            name="uq_payment_links_razorpay_payment_link_id",
        ),
        CheckConstraint("amount >= 0", name="ck_payment_links_amount_non_negative"),
        CheckConstraint(
            "amount_paid >= 0", name="ck_payment_links_amount_paid_non_negative"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    razorpay_payment_link_id: Mapped[str] = mapped_column(String(255), nullable=False)
    order_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orders.id")
    )
    recovery_case_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recovery_cases.id")
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_paid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    short_url: Mapped[str | None] = mapped_column(Text)
    expire_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    merchant: Mapped[Merchant] = relationship()
    order: Mapped[Order | None] = relationship()
    recovery_case: Mapped[RecoveryCase | None] = relationship()


class RecoveryFeature(Base):
    __tablename__ = "recovery_features"

    recovery_case_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("recovery_cases.id"),
        primary_key=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    failure_source: Mapped[str | None] = mapped_column(String(255))
    failure_code: Mapped[str | None] = mapped_column(String(255))
    payment_method: Mapped[str | None] = mapped_column(String(64))
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    case_age: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    customer_tenure: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prior_success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prior_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    previous_recovery_success_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    engagement_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    available_payment_methods: Mapped[list[str] | None] = mapped_column(JSON)
    feature_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    recovery_case: Mapped[RecoveryCase] = relationship()


class RecoveryDecision(Base):
    __tablename__ = "recovery_decisions"
    __table_args__ = (Index("ix_recovery_decisions_case", "recovery_case_id"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    recovery_case_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recovery_cases.id"), nullable=False
    )
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_actions: Mapped[dict] = mapped_column(JSON, nullable=False)
    action_scores: Mapped[dict] = mapped_column(JSON, nullable=False)
    expected_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    selected_action: Mapped[ActionType] = mapped_column(
        enum_column(ActionType, 40), nullable=False
    )
    selected_action_score: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    recovery_case: Mapped[RecoveryCase] = relationship()


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"
    __table_args__ = (Index("ix_recovery_actions_case_status", "recovery_case_id", "status"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    recovery_case_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recovery_cases.id"), nullable=False
    )
    action_type: Mapped[ActionType] = mapped_column(
        enum_column(ActionType, 40), nullable=False
    )
    status: Mapped[RecoveryActionStatus] = mapped_column(
        enum_column(RecoveryActionStatus, 16),
        nullable=False,
        default=RecoveryActionStatus.PENDING,
    )
    razorpay_resource_id: Mapped[str | None] = mapped_column(String(255))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    policy_result: Mapped[dict | None] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    recovery_case: Mapped[RecoveryCase] = relationship()


class ActionOutcome(Base):
    __tablename__ = "action_outcomes"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    action_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recovery_actions.id"), nullable=False
    )
    outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_recovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(255))
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    action: Mapped[RecoveryAction] = relationship()


class ExperimentAssignment(Base):
    __tablename__ = "experiment_assignments"
    __table_args__ = (
        UniqueConstraint(
            "experiment_id",
            "recovery_case_id",
            name="uq_experiment_assignments_experiment_case",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    experiment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("experiments.id"), nullable=False
    )
    recovery_case_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recovery_cases.id"), nullable=False
    )
    group_name: Mapped[ExperimentGroup] = mapped_column(
        enum_column(ExperimentGroup, 16), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    experiment: Mapped[Experiment] = relationship()
    recovery_case: Mapped[RecoveryCase] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_case_timestamp", "recovery_case_id", "timestamp"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    recovery_case_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recovery_cases.id")
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_type: Mapped[AuditActorType] = mapped_column(
        enum_column(AuditActorType, 16), nullable=False
    )
    input_snapshot: Mapped[dict | None] = mapped_column(JSON)
    decision_snapshot: Mapped[dict | None] = mapped_column(JSON)
    policy_snapshot: Mapped[dict | None] = mapped_column(JSON)
    action_snapshot: Mapped[dict | None] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    recovery_case: Mapped[RecoveryCase | None] = relationship()


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "provider", "event_id", name="uq_webhook_events_provider_event_id"
        ),
        CheckConstraint(
            "processing_attempts >= 0",
            name="ck_webhook_events_processing_attempts_non_negative",
        ),
        Index("ix_webhook_events_status_received", "status", "received_at"),
        Index("ix_webhook_events_type_resource", "event_type", "resource_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(255))
    event_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[WebhookEventStatus] = mapped_column(
        enum_column(WebhookEventStatus, 16),
        nullable=False,
        default=WebhookEventStatus.RECEIVED,
    )
    processing_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recovery_case_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recovery_cases.id")
    )
    resource_id: Mapped[str | None] = mapped_column(String(255))
    reconciliation_snapshot: Mapped[dict | None] = mapped_column(JSON)
    last_error: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recovery_case: Mapped[RecoveryCase | None] = relationship()
