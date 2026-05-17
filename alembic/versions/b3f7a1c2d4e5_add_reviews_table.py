"""add_reviews_table

Revision ID: b3f7a1c2d4e5
Revises: a265d5630c3e
Create Date: 2026-05-16 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3f7a1c2d4e5'
down_revision: Union[str, Sequence[str], None] = 'a265d5630c3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create reviews table and update claims.status for new statuses."""
    op.create_table(
        'reviews',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('claim_id', sa.Uuid(), nullable=False),
        sa.Column('validation_id', sa.Uuid(), nullable=True),
        sa.Column('reviewer_id', sa.String(), nullable=False),
        sa.Column('decision', sa.String(), nullable=False),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('override_rationale', sa.String(), nullable=True),
        sa.Column('claim_status_before', sa.String(), nullable=False),
        sa.Column('claim_status_after', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id']),
        sa.ForeignKeyConstraint(['validation_id'], ['validations.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_reviews_id'), 'reviews', ['id'], unique=False)
    op.create_index(op.f('ix_reviews_claim_id'), 'reviews', ['claim_id'], unique=False)
    op.create_index(op.f('ix_reviews_reviewer_id'), 'reviews', ['reviewer_id'], unique=False)


def downgrade() -> None:
    """Drop reviews table."""
    op.drop_index(op.f('ix_reviews_reviewer_id'), table_name='reviews')
    op.drop_index(op.f('ix_reviews_claim_id'), table_name='reviews')
    op.drop_index(op.f('ix_reviews_id'), table_name='reviews')
    op.drop_table('reviews')
