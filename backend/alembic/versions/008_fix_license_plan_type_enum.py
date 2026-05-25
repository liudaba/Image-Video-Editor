"""fix licenses.plan_type from varchar to plantype enum

Revision ID: 008
Revises: 007
Create Date: 2026-05-24

迁移脚本006错误地使用String(20)创建plan_type列，
导致licenses.plan_type为varchar而非PostgreSQL enum类型。
此脚本将其修正为与license_keys/orders一致的plantype enum。
"""
from alembic import op
import sqlalchemy as sa

revision = '008'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 将varchar列中的大写枚举名转换为小写值（与PlanType.value一致）
    # PostgreSQL enum类型存储的是枚举标签（大写），但SQLAlchemy的str,enum.Enum
    # 通过.value（小写）映射，所以需要确保数据兼容
    # 实际上plantype enum的标签是大写的（MONTHLY等），直接转换类型即可
    op.execute(
        "ALTER TABLE licenses ALTER COLUMN plan_type TYPE plantype "
        "USING plan_type::plantype"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE licenses ALTER COLUMN plan_type TYPE varchar(20) "
        "USING plan_type::varchar"
    )
