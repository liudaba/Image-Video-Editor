"""add missing enum values to plantype

Revision ID: 009
Revises: 008
Create Date: 2026-05-24

初始plantype enum只包含monthly/yearly/lifetime，
缺少quarterly和trial_15d。此脚本补充缺失的enum值，
确保与PlanType模型定义一致。
"""
from alembic import op

revision = '009'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL ALTER TYPE ... ADD VALUE 不能在事务内执行
    op.execute("ALTER TYPE plantype ADD VALUE IF NOT EXISTS 'quarterly'")
    op.execute("ALTER TYPE plantype ADD VALUE IF NOT EXISTS 'trial_15d'")


def downgrade() -> None:
    # PostgreSQL 不支持从 enum 类型中删除值
    # 如果确实需要回滚，需要重建 enum 类型，此处跳过
    pass
