"""Add durable Razorpay webhook event ingestion.

Revision ID: 0003_webhook_events
Revises: 0002_domain_model
Create Date: 2026-09-01
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003_webhook_events"
down_revision: str | None = "0002_domain_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


WEBHOOK_EVENT_STATUSES = (
    "RECEIVED",
    "PROCESSING",
    "PROCESSED",
    "IGNORED",
    "FAILED",
)


def upgrade() -> None:
    quoted_statuses = ", ".join(f"'{value}'" for value in WEBHOOK_EVENT_STATUSES)
    op.create_table(
        "webhook_events",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("account_id", sa.String(length=255), nullable=True),
        sa.Column("event_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "processing_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("recovery_case_id", sa.Uuid(), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("reconciliation_snapshot", sa.JSON(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["recovery_case_id"], ["recovery_cases.id"]),
        sa.CheckConstraint(
            f"status in ({quoted_statuses})",
            name="ck_webhook_events_status",
        ),
        sa.CheckConstraint(
            "processing_attempts >= 0",
            name="ck_webhook_events_processing_attempts_non_negative",
        ),
        sa.UniqueConstraint(
            "provider", "event_id", name="uq_webhook_events_provider_event_id"
        ),
    )
    op.create_index(
        "ix_webhook_events_status_received",
        "webhook_events",
        ["status", "received_at"],
    )
    op.create_index(
        "ix_webhook_events_type_resource",
        "webhook_events",
        ["event_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_events_type_resource", table_name="webhook_events")
    op.drop_index("ix_webhook_events_status_received", table_name="webhook_events")
    op.drop_table("webhook_events")
