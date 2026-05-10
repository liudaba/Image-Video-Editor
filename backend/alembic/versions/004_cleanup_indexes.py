"""add cleanup indexes for payment_notify_logs and orders

Revision ID: 004_cleanup_indexes
Revises: 003_order_fields
Create Date: 2026-05-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_cleanup_indexes"
down_revision: Union[str, None] = "003_order_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_payment_notify_logs_created_at", "payment_notify_logs", ["created_at"])
    op.create_index("ix_orders_status_created_at", "orders", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_orders_status_created_at", table_name="orders")
    op.drop_index("ix_payment_notify_logs_created_at", table_name="payment_notify_logs")
