"""add expiry_date to license_keys

Revision ID: 005_license_key_expiry
Revises: 004_cleanup_indexes
Create Date: 2026-05-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_license_key_expiry"
down_revision: Union[str, None] = "004_cleanup_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("license_keys", sa.Column("expiry_date", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("license_keys", "expiry_date")
