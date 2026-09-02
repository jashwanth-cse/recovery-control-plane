"""Make baseline action outcomes idempotent.

Revision ID: 0005_rule_baseline
Revises: 0004_recovery_case_engine
Create Date: 2026-09-02
"""

from typing import Sequence

from alembic import op


revision: str = "0005_rule_baseline"
down_revision: str | None = "0004_recovery_case_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_action_outcomes_action_id",
        "action_outcomes",
        ["action_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_action_outcomes_action_id",
        "action_outcomes",
        type_="unique",
    )
