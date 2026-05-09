"""add order payment_url and qr_code columns

Revision ID: 003_order_fields
Revises: 002_payment_notify
Create Date: 2026-05-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_order_fields"
down_revision: Union[str, None] = "002_payment_notify"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("payment_url", sa.String(length=500), nullable=True))
    op.add_column("orders", sa.Column("qr_code", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "qr_code")
    op.drop_column("orders", "payment_url")
