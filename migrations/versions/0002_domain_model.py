"""Create domain model tables.

Revision ID: 0002_domain_model
Revises: 0001_foundation
Create Date: 2026-08-31
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_domain_model"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum_check(column: str, values: tuple[str, ...]) -> str:
    quoted_values = ", ".join(f"'{value}'" for value in values)
    return f"{column} in ({quoted_values})"


CONSENT_STATUSES = ("UNKNOWN", "OPTED_IN", "OPTED_OUT")
SOURCE_TYPES = ("PAYMENT", "ORDER", "PAYMENT_LINK")
CASE_STATUSES = (
    "AT_RISK",
    "ELIGIBILITY_CHECK",
    "ASSESSING",
    "DECISION_READY",
    "POLICY_CHECK",
    "ACTION_PENDING",
    "EXECUTING",
    "ACTION_FAILED",
    "REASSESS",
    "NEXT_ACTION",
    "RECOVERED",
    "STOPPED",
    "EXPIRED",
    "ESCALATED",
)
ACTION_TYPES = (
    "RECOVERY_LINK",
    "PAYMENT_METHOD_UPDATE_PROMPT",
    "DELAY",
    "STOP",
    "ESCALATE",
)
ACTION_STATUSES = (
    "PENDING",
    "SCHEDULED",
    "EXECUTING",
    "SUCCEEDED",
    "FAILED",
    "BLOCKED",
    "CANCELLED",
)
EXPERIMENT_GROUPS = ("CONTROL", "TREATMENT")
EXPERIMENT_STATUSES = ("DRAFT", "RUNNING", "COMPLETED", "PAUSED")
AUDIT_ACTOR_TYPES = ("SYSTEM", "POLICY", "MODEL", "HUMAN", "RAZORPAY")


def uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        sa.Uuid(),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
        primary_key=True,
    )


def timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def upgrade() -> None:
    op.execute("create extension if not exists pgcrypto")

    op.create_table(
        "merchants",
        uuid_pk(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("razorpay_key_id", sa.String(length=255), nullable=True),
        sa.Column("secret_reference", sa.String(length=255), nullable=True),
        *timestamps(),
    )

    op.create_table(
        "customers",
        uuid_pk(),
        sa.Column("merchant_id", sa.Uuid(), nullable=False),
        sa.Column("external_customer_id", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("consent_status", sa.String(length=16), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"]),
        sa.CheckConstraint(
            enum_check("consent_status", CONSENT_STATUSES),
            name="ck_customers_consent_status",
        ),
        sa.UniqueConstraint(
            "merchant_id",
            "external_customer_id",
            name="uq_customers_merchant_external_customer_id",
        ),
    )

    op.create_table(
        "orders",
        uuid_pk(),
        sa.Column("merchant_id", sa.Uuid(), nullable=False),
        sa.Column("razorpay_order_id", sa.String(length=255), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount_paid", sa.Integer(), nullable=False),
        sa.Column("amount_due", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.CheckConstraint("amount >= 0", name="ck_orders_amount_non_negative"),
        sa.CheckConstraint(
            "amount_paid >= 0", name="ck_orders_amount_paid_non_negative"
        ),
        sa.CheckConstraint("amount_due >= 0", name="ck_orders_amount_due_non_negative"),
        sa.CheckConstraint("attempts >= 0", name="ck_orders_attempts_non_negative"),
        sa.UniqueConstraint("razorpay_order_id", name="uq_orders_razorpay_order_id"),
    )

    op.create_table(
        "payments",
        uuid_pk(),
        sa.Column("merchant_id", sa.Uuid(), nullable=False),
        sa.Column("razorpay_payment_id", sa.String(length=255), nullable=False),
        sa.Column("razorpay_order_id", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=255), nullable=True),
        sa.Column("error_description", sa.Text(), nullable=True),
        sa.Column("error_reason", sa.String(length=255), nullable=True),
        sa.Column("error_source", sa.String(length=255), nullable=True),
        sa.Column("error_step", sa.String(length=255), nullable=True),
        sa.Column("bank", sa.String(length=64), nullable=True),
        sa.Column("vpa", sa.String(length=255), nullable=True),
        sa.Column("invoice_id", sa.String(length=255), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"]),
        sa.CheckConstraint("amount >= 0", name="ck_payments_amount_non_negative"),
        sa.UniqueConstraint(
            "razorpay_payment_id", name="uq_payments_razorpay_payment_id"
        ),
    )
    op.create_index(
        "ix_payments_razorpay_order_id", "payments", ["razorpay_order_id"]
    )

    op.create_table(
        "experiments",
        uuid_pk(),
        sa.Column("merchant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("control_percentage", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"]),
        sa.CheckConstraint(
            "control_percentage >= 0 and control_percentage <= 100",
            name="ck_experiments_control_percentage_range",
        ),
        sa.CheckConstraint(
            enum_check("status", EXPERIMENT_STATUSES),
            name="ck_experiments_status",
        ),
    )

    op.create_table(
        "recovery_cases",
        uuid_pk(),
        sa.Column("merchant_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("amount_at_risk", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("recovery_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recovery_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("contact_count", sa.Integer(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=True),
        sa.Column("experiment_group", sa.String(length=16), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"]),
        sa.CheckConstraint(
            enum_check("source_type", SOURCE_TYPES),
            name="ck_recovery_cases_source_type",
        ),
        sa.CheckConstraint(
            enum_check("status", CASE_STATUSES),
            name="ck_recovery_cases_status",
        ),
        sa.CheckConstraint(
            "experiment_group is null or "
            + enum_check("experiment_group", EXPERIMENT_GROUPS),
            name="ck_recovery_cases_experiment_group",
        ),
        sa.CheckConstraint(
            "amount_at_risk > 0", name="ck_recovery_cases_amount_at_risk_positive"
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_recovery_cases_attempt_count_non_negative"
        ),
        sa.CheckConstraint(
            "contact_count >= 0", name="ck_recovery_cases_contact_count_non_negative"
        ),
        sa.CheckConstraint(
            "recovery_window_end > recovery_window_start",
            name="ck_recovery_cases_window_order",
        ),
        sa.UniqueConstraint(
            "merchant_id",
            "source_type",
            "source_id",
            name="uq_recovery_cases_merchant_source",
        ),
    )
    op.create_index(
        "ix_recovery_cases_merchant_status",
        "recovery_cases",
        ["merchant_id", "status"],
    )

    op.create_table(
        "payment_links",
        uuid_pk(),
        sa.Column("merchant_id", sa.Uuid(), nullable=False),
        sa.Column("razorpay_payment_link_id", sa.String(length=255), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("recovery_case_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("short_url", sa.Text(), nullable=True),
        sa.Column("expire_by", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["recovery_case_id"], ["recovery_cases.id"]),
        sa.CheckConstraint("amount >= 0", name="ck_payment_links_amount_non_negative"),
        sa.UniqueConstraint(
            "razorpay_payment_link_id",
            name="uq_payment_links_razorpay_payment_link_id",
        ),
    )

    op.create_table(
        "recovery_features",
        sa.Column("recovery_case_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("failure_source", sa.String(length=255), nullable=True),
        sa.Column("failure_code", sa.String(length=255), nullable=True),
        sa.Column("payment_method", sa.String(length=64), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("case_age", sa.Integer(), nullable=False),
        sa.Column("customer_tenure", sa.Integer(), nullable=False),
        sa.Column("prior_success_count", sa.Integer(), nullable=False),
        sa.Column("prior_failure_count", sa.Integer(), nullable=False),
        sa.Column("previous_recovery_success_count", sa.Integer(), nullable=False),
        sa.Column("engagement_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("available_payment_methods", sa.JSON(), nullable=True),
        sa.Column(
            "feature_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["recovery_case_id"], ["recovery_cases.id"]),
    )

    op.create_table(
        "recovery_decisions",
        uuid_pk(),
        sa.Column("recovery_case_id", sa.Uuid(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("candidate_actions", sa.JSON(), nullable=False),
        sa.Column("action_scores", sa.JSON(), nullable=False),
        sa.Column("expected_values", sa.JSON(), nullable=False),
        sa.Column("selected_action", sa.String(length=40), nullable=False),
        sa.Column("selected_action_score", sa.Numeric(8, 6), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["recovery_case_id"], ["recovery_cases.id"]),
        sa.CheckConstraint(
            enum_check("selected_action", ACTION_TYPES),
            name="ck_recovery_decisions_selected_action",
        ),
    )
    op.create_index(
        "ix_recovery_decisions_case", "recovery_decisions", ["recovery_case_id"]
    )

    op.create_table(
        "recovery_actions",
        uuid_pk(),
        sa.Column("recovery_case_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("razorpay_resource_id", sa.String(length=255), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("policy_result", sa.JSON(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["recovery_case_id"], ["recovery_cases.id"]),
        sa.CheckConstraint(
            enum_check("action_type", ACTION_TYPES),
            name="ck_recovery_actions_action_type",
        ),
        sa.CheckConstraint(
            enum_check("status", ACTION_STATUSES),
            name="ck_recovery_actions_status",
        ),
    )
    op.create_index(
        "ix_recovery_actions_case_status",
        "recovery_actions",
        ["recovery_case_id", "status"],
    )

    op.create_table(
        "action_outcomes",
        uuid_pk(),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column("amount_recovered", sa.Integer(), nullable=False),
        sa.Column("razorpay_payment_id", sa.String(length=255), nullable=True),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["action_id"], ["recovery_actions.id"]),
    )

    op.create_table(
        "experiment_assignments",
        uuid_pk(),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("recovery_case_id", sa.Uuid(), nullable=False),
        sa.Column("group_name", sa.String(length=16), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"]),
        sa.ForeignKeyConstraint(["recovery_case_id"], ["recovery_cases.id"]),
        sa.CheckConstraint(
            enum_check("group_name", EXPERIMENT_GROUPS),
            name="ck_experiment_assignments_group_name",
        ),
        sa.UniqueConstraint(
            "experiment_id",
            "recovery_case_id",
            name="uq_experiment_assignments_experiment_case",
        ),
    )

    op.create_table(
        "audit_events",
        uuid_pk(),
        sa.Column("recovery_case_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=True),
        sa.Column("decision_snapshot", sa.JSON(), nullable=True),
        sa.Column("policy_snapshot", sa.JSON(), nullable=True),
        sa.Column("action_snapshot", sa.JSON(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["recovery_case_id"], ["recovery_cases.id"]),
        sa.CheckConstraint(
            enum_check("actor_type", AUDIT_ACTOR_TYPES),
            name="ck_audit_events_actor_type",
        ),
    )
    op.create_index(
        "ix_audit_events_case_timestamp",
        "audit_events",
        ["recovery_case_id", "timestamp"],
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("experiment_assignments")
    op.drop_table("action_outcomes")
    op.drop_table("recovery_actions")
    op.drop_table("recovery_decisions")
    op.drop_table("recovery_features")
    op.drop_table("payment_links")
    op.drop_table("recovery_cases")
    op.drop_table("experiments")
    op.drop_index("ix_payments_razorpay_order_id", table_name="payments")
    op.drop_table("payments")
    op.drop_table("orders")
    op.drop_table("customers")
    op.drop_table("merchants")
