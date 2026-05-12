"""add_jd_fields_to_interviews

Revision ID: 89ea4d5c4ffc
Revises: 0ab5679bef63
Create Date: 2026-05-11 23:39:31.073767
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '89ea4d5c4ffc'
down_revision: Union[str, None] = '0ab5679bef63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('interviews', sa.Column('jd_text', sa.Text(), nullable=True))
    op.add_column('interviews', sa.Column('jd_analysis', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('interviews', 'jd_analysis')
    op.drop_column('interviews', 'jd_text')
