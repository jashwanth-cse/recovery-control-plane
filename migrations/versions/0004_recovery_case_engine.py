"""Add Razorpay account ownership mapping.

Revision ID: 0004_recovery_case_engine
Revises: 0003_webhook_events
Create Date: 2026-09-02
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004_recovery_case_engine"
down_revision: str | None = "0003_webhook_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "merchants",
        sa.Column("razorpay_account_id", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_merchants_razorpay_account_id",
        "merchants",
        ["razorpay_account_id"],
    )
    op.add_column(
        "payment_links",
        sa.Column(
            "amount_paid", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.create_check_constraint(
        "ck_payment_links_amount_paid_non_negative",
        "payment_links",
        "amount_paid >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_payment_links_amount_paid_non_negative",
        "payment_links",
        type_="check",
    )
    op.drop_column("payment_links", "amount_paid")
    op.drop_constraint(
        "uq_merchants_razorpay_account_id", "merchants", type_="unique"
    )
    op.drop_column("merchants", "razorpay_account_id")
