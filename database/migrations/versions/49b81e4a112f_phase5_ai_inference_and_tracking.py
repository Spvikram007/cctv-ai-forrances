"""phase5_ai_inference_and_tracking

Revision ID: 49b81e4a112f
Revises: 328e2912c14c
Create Date: 2026-11-22 21:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '49b81e4a112f'
down_revision: Union[str, Sequence[str], None] = '328e2912c14c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema for Phase 5 AI Inference, Detection & Tracking."""
    with op.batch_alter_table('ai_jobs') as batch_op:
        batch_op.add_column(sa.Column('execution_device', sa.String(length=20), server_default='CPU', nullable=False))
        batch_op.add_column(sa.Column('actual_fps', sa.Float(), server_default='0.0', nullable=False))
        batch_op.alter_column('channel_id', type_=sa.String(length=64), existing_type=sa.String(length=36))

    with op.batch_alter_table('detections') as batch_op:
        batch_op.alter_column('channel_id', type_=sa.String(length=64), existing_type=sa.String(length=36))

    with op.batch_alter_table('object_tracks') as batch_op:
        batch_op.alter_column('channel_id', type_=sa.String(length=64), existing_type=sa.String(length=36))

    with op.batch_alter_table('ai_events') as batch_op:
        batch_op.alter_column('channel_id', type_=sa.String(length=64), existing_type=sa.String(length=36))


def downgrade() -> None:
    """Downgrade schema for Phase 5."""
    with op.batch_alter_table('ai_events') as batch_op:
        batch_op.alter_column('channel_id', type_=sa.String(length=36), existing_type=sa.String(length=64))

    with op.batch_alter_table('object_tracks') as batch_op:
        batch_op.alter_column('channel_id', type_=sa.String(length=36), existing_type=sa.String(length=64))

    with op.batch_alter_table('detections') as batch_op:
        batch_op.alter_column('channel_id', type_=sa.String(length=36), existing_type=sa.String(length=64))

    with op.batch_alter_table('ai_jobs') as batch_op:
        batch_op.alter_column('channel_id', type_=sa.String(length=36), existing_type=sa.String(length=64))
        batch_op.drop_column('actual_fps')
        batch_op.drop_column('execution_device')
