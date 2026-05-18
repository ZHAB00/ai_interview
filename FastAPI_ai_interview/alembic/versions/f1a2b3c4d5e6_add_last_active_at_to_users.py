"""add last_active_at_to_users

Revision ID: f1a2b3c4d5e6
Revises: 89ea4d5c4ffc
Create Date: 2026-05-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = '89ea4d5c4ffc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('last_active_at', sa.DateTime(), nullable=True))

def downgrade() -> None:
    op.drop_column('users', 'last_active_at')
