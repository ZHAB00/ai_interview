"""add_source_to_questions

Revision ID: 0ab5679bef63
Revises: d2a2caa56b70
Create Date: 2026-05-11 14:49:39.541696
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0ab5679bef63'
down_revision: Union[str, None] = 'd2a2caa56b70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('questions', sa.Column(
        'source', sa.String(20), nullable=False, server_default='manual'
    ))
    op.add_column('questions', sa.Column(
        'source_interview_id', sa.Integer(), nullable=True
    ))
    op.create_index('ix_questions_source', 'questions', ['source'])


def downgrade() -> None:
    op.drop_index('ix_questions_source')
    op.drop_column('questions', 'source_interview_id')
    op.drop_column('questions', 'source')
