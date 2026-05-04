"""add is_favorited to interviews

Revision ID: b4e5f6a7c8d9
Revises: a1b2c3d4e5f6
Create Date: 2026-05-04
"""
from alembic import op
import sqlalchemy as sa

revision = 'b4e5f6a7c8d9'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('interviews', sa.Column('is_favorited', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('interviews', 'is_favorited')
