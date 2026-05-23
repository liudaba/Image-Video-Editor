"""add plan_type to licenses table

Revision ID: 006
Revises: 005_license_key_expiry
Create Date: 2026-05-20
"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005_license_key_expiry'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('licenses', sa.Column('plan_type', sa.String(20), nullable=True, server_default='TRIAL_15D'))


def downgrade() -> None:
    op.drop_column('licenses', 'plan_type')
