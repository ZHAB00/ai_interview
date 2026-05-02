"""add skill_tags to questions

Revision ID: a1b2c3d4e5f6
Revises: 8edc35502aac
Create Date: 2026-04-28

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '8edc35502aac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('questions', sa.Column('skill_tags', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('questions', 'skill_tags')
