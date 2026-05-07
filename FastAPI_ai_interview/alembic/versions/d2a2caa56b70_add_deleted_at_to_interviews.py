"""add_deleted_at_to_interviews

Revision ID: d2a2caa56b70
Revises: c5d6e7f8a9b0
Create Date: 2026-05-07 22:14:22.814558
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = 'd2a2caa56b70'
down_revision: Union[str, None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='interviews' AND COLUMN_NAME='deleted_at'"
    ))
    if result.scalar() == 0:
        op.add_column('interviews', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    try:
        op.create_index(op.f('ix_interviews_deleted_at'), 'interviews', ['deleted_at'], unique=False)
    except Exception:
        pass  # index already exists


def downgrade() -> None:
    try:
        op.drop_index(op.f('ix_interviews_deleted_at'), table_name='interviews')
    except Exception:
        pass
    conn = op.get_bind()
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='interviews' AND COLUMN_NAME='deleted_at'"
    ))
    if result.scalar() == 1:
        op.drop_column('interviews', 'deleted_at')
