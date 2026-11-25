"""phase14_user_mgmt_rbac_audit

Revision ID: 78a12e9b04f1
Revises: 62f4c08e921d
Create Date: 2026-11-25 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78a12e9b04f1'
down_revision: Union[str, Sequence[str], None] = '62f4c08e921d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema for Phase 14 User Management, RBAC, and Audit Reporting."""
    # 1. users table: add lockout, session, and activity tracking
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('failed_login_attempts', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True))

    # 2. user_sessions table: add last_seen_at
    with op.batch_alter_table('user_sessions') as batch_op:
        batch_op.add_column(sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))

    # 3. audit_logs table: add category, status, and cryptographic hash chaining
    with op.batch_alter_table('audit_logs') as batch_op:
        batch_op.add_column(sa.Column('username', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('category', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('status', sa.String(length=20), server_default='SUCCESS', nullable=False))
        batch_op.add_column(sa.Column('session_id', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('correlation_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('prev_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('record_hash', sa.String(length=64), nullable=True))
        batch_op.create_index('ix_audit_logs_username', ['username'])
        batch_op.create_index('ix_audit_logs_category', ['category'])
        batch_op.create_index('ix_audit_logs_status', ['status'])
        batch_op.create_index('ix_audit_logs_correlation_id', ['correlation_id'])


def downgrade() -> None:
    """Downgrade schema for Phase 14."""
    with op.batch_alter_table('audit_logs') as batch_op:
        batch_op.drop_index('ix_audit_logs_correlation_id')
        batch_op.drop_index('ix_audit_logs_status')
        batch_op.drop_index('ix_audit_logs_category')
        batch_op.drop_index('ix_audit_logs_username')
        batch_op.drop_column('record_hash')
        batch_op.drop_column('prev_hash')
        batch_op.drop_column('correlation_id')
        batch_op.drop_column('session_id')
        batch_op.drop_column('status')
        batch_op.drop_column('category')
        batch_op.drop_column('username')

    with op.batch_alter_table('user_sessions') as batch_op:
        batch_op.drop_column('last_seen_at')

    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('password_changed_at')
        batch_op.drop_column('last_activity_at')
        batch_op.drop_column('last_login_at')
        batch_op.drop_column('locked_until')
        batch_op.drop_column('failed_login_attempts')
