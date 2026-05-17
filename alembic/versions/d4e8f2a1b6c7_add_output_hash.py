"""add_output_hash

Revision ID: d4e8f2a1b6c7
Revises: b3f7a1c2d4e5
Create Date: 2026-05-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e8f2a1b6c7"
down_revision: Union[str, Sequence[str], None] = "b3f7a1c2d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("validations", sa.Column("output_hash", sa.String(), nullable=True))
    op.create_index(op.f("ix_validations_output_hash"), "validations", ["output_hash"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_validations_output_hash"), table_name="validations")
    op.drop_column("validations", "output_hash")
