"""add invite_codes table

Revision ID: d5e6f7a8c9b1
Revises: 89ea4d5c4ffc
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'd5e6f7a8c9b1'
down_revision = 'd2a2caa56b70'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'invite_codes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(32), nullable=False),
        sa.Column('max_uses', sa.Integer(), nullable=True),
        sa.Column('use_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
    )
    op.create_index('idx_invite_codes_code', 'invite_codes', ['code'])


def downgrade() -> None:
    op.drop_table('invite_codes')
