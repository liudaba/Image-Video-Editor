"""add payment_notify_logs and user password_changed_at

Revision ID: 002_payment_notify
Revises: 001_initial
Create Date: 2026-05-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_payment_notify"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_notify_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("notify_id", sa.String(length=128), nullable=False),
        sa.Column("order_no", sa.String(length=64), nullable=False),
        sa.Column("payment_method", sa.String(length=20), nullable=False),
        sa.Column("raw_data", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notify_id"),
    )
    op.create_index("ix_payment_notify_logs_notify_id", "payment_notify_logs", ["notify_id"])
    op.create_index("ix_payment_notify_logs_order_no", "payment_notify_logs", ["order_no"])

    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_changed_at")
    op.drop_table("payment_notify_logs")
