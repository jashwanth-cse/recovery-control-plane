"""Create foundation migration marker.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-08-30
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "foundation_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("component", sa.String(length=64), nullable=False, unique=True),
        sa.Column("status", sa.String(length=32), nullable=False),
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
    op.execute(
        sa.text(
            "insert into foundation_status (component, status) "
            "values ('phase_0', 'ready')"
        )
    )


def downgrade() -> None:
    op.drop_table("foundation_status")
