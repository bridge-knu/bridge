"""engine state: diagnosis_sessions, plan_infos, plan_blocks.done_at

Revision ID: 7a1c3e5d9b20
Revises: 2e8b046b2197
Create Date: 2026-11-21 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '7a1c3e5d9b20'
down_revision: str | None = '2e8b046b2197'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('diagnosis_sessions',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_diagnosis_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_diagnosis_sessions'))
    )
    op.create_table('plan_infos',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('deferred', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_plan_infos_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_plan_infos'))
    )
    op.add_column('plan_blocks', sa.Column('done_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('plan_blocks', 'done_at')
    op.drop_table('plan_infos')
    op.drop_table('diagnosis_sessions')
