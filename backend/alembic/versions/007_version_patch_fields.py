"""add patch update fields to app_versions table

Revision ID: 007
Revises: 006
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 新增补丁更新字段
    op.add_column('app_versions', sa.Column('update_type', sa.String(20), nullable=False, server_default='full'))
    op.add_column('app_versions', sa.Column('patch_url', sa.String(500), nullable=True))
    op.add_column('app_versions', sa.Column('patch_hash', sa.String(64), nullable=True))
    op.add_column('app_versions', sa.Column('patch_size', sa.Integer(), nullable=True))
    op.add_column('app_versions', sa.Column('from_version', sa.String(20), nullable=True))
    # 允许 download_url 和 file_size 为空（patch类型可能没有全量包）
    op.alter_column('app_versions', 'download_url', existing_type=sa.String(500), nullable=True)
    op.alter_column('app_versions', 'file_size', existing_type=sa.Integer(), nullable=True)
    # 移除 version 列的 unique 约束（同一版本号可有 full + patch 多条记录）
    try:
        op.drop_constraint('uq_app_versions_version', 'app_versions', type_='unique')
    except Exception:
        try:
            op.drop_index('ix_app_versions_version', table_name='app_versions')
        except Exception:
            pass


def downgrade() -> None:
    # 恢复 unique 约束（注意：如果有重复version记录会失败）
    try:
        op.create_unique_constraint('uq_app_versions_version', 'app_versions', ['version'])
    except Exception:
        pass
    op.alter_column('app_versions', 'file_size', existing_type=sa.Integer(), nullable=False)
    op.alter_column('app_versions', 'download_url', existing_type=sa.String(500), nullable=False)
    op.drop_column('app_versions', 'from_version')
    op.drop_column('app_versions', 'patch_size')
    op.drop_column('app_versions', 'patch_hash')
    op.drop_column('app_versions', 'patch_url')
    op.drop_column('app_versions', 'update_type')
