"""phase7_face_and_anpr

Revision ID: 62f4c08e921d
Revises: 57a91c3e80ab
Create Date: 2026-11-24 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '62f4c08e921d'
down_revision: Union[str, Sequence[str], None] = '57a91c3e80ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema for Phase 7 Authorized Face Intelligence and ANPR."""
    # 1. face_identities
    op.create_table(
        'face_identities',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False, index=True),
        sa.Column('identity_code', sa.String(length=50), unique=True, nullable=False, index=True),
        sa.Column('category', sa.String(length=50), server_default='AUTHORIZED_STAFF', nullable=False, index=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False, index=True),
        sa.Column('department', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='0', nullable=False, index=True),
    )

    # 2. face_templates
    op.create_table(
        'face_templates',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('identity_id', sa.String(length=36), sa.ForeignKey('face_identities.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('encrypted_template', sa.Text(), nullable=False),
        sa.Column('algorithm', sa.String(length=50), server_default='MobileFaceNet-512', nullable=False),
        sa.Column('vector_dim', sa.Integer(), server_default='512', nullable=False),
        sa.Column('quality_score', sa.Float(), server_default='1.0', nullable=False),
        sa.Column('is_revoked', sa.Boolean(), server_default='0', nullable=False, index=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revocation_reason', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='0', nullable=False, index=True),
    )

    # 3. face_enrollments
    op.create_table(
        'face_enrollments',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('identity_id', sa.String(length=36), sa.ForeignKey('face_identities.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('enrolled_by_user_id', sa.String(length=36), nullable=True, index=True),
        sa.Column('status', sa.String(length=30), server_default='APPROVED', nullable=False, index=True),
        sa.Column('authorization_ref', sa.String(length=100), nullable=True),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='0', nullable=False, index=True),
    )

    # 4. face_match_events
    op.create_table(
        'face_match_events',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('channel_id', sa.String(length=64), nullable=False, index=True),
        sa.Column('identity_id', sa.String(length=36), sa.ForeignKey('face_identities.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('candidate_name', sa.String(length=100), nullable=False, index=True),
        sa.Column('category', sa.String(length=50), server_default='AUTHORIZED_STAFF', nullable=False, index=True),
        sa.Column('similarity_score', sa.Float(), nullable=False),
        sa.Column('threshold_applied', sa.Float(), server_default='0.65', nullable=False),
        sa.Column('snapshot_path', sa.String(length=500), nullable=True),
        sa.Column('face_bbox_json', sa.Text(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), server_default='0', nullable=False, index=True),
        sa.Column('verified_by_user_id', sa.String(length=36), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='0', nullable=False, index=True),
    )

    # 5. anpr_detections
    op.create_table(
        'anpr_detections',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('channel_id', sa.String(length=64), nullable=False, index=True),
        sa.Column('track_id', sa.Integer(), nullable=True, index=True),
        sa.Column('vehicle_class', sa.String(length=50), server_default='car', nullable=False, index=True),
        sa.Column('plate_text', sa.String(length=30), nullable=False, index=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('character_confidences_json', sa.Text(), nullable=True),
        sa.Column('plate_format', sa.String(length=30), server_default='STANDARD', nullable=False),
        sa.Column('requires_manual_review', sa.Boolean(), server_default='0', nullable=False, index=True),
        sa.Column('plate_crop_path', sa.String(length=500), nullable=True),
        sa.Column('vehicle_snapshot_path', sa.String(length=500), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='0', nullable=False, index=True),
    )

    # 6. anpr_plate_records
    op.create_table(
        'anpr_plate_records',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('plate_text_normalized', sa.String(length=30), unique=True, nullable=False, index=True),
        sa.Column('vehicle_class', sa.String(length=50), server_default='car', nullable=False),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('total_sightings', sa.Integer(), server_default='1', nullable=False),
        sa.Column('is_watchlist', sa.Boolean(), server_default='0', nullable=False, index=True),
        sa.Column('watchlist_category', sa.String(length=50), nullable=True),
        sa.Column('owner_or_notes', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='0', nullable=False, index=True),
    )

    # 7. vehicle_events
    op.create_table(
        'vehicle_events',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('channel_id', sa.String(length=64), nullable=False, index=True),
        sa.Column('plate_text', sa.String(length=30), nullable=False, index=True),
        sa.Column('event_type', sa.String(length=50), server_default='PLATE_DETECTED', nullable=False, index=True),
        sa.Column('severity', sa.String(length=20), server_default='INFO', nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=True),
        sa.Column('details_json', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='0', nullable=False, index=True),
    )

    # 8. biometric_audit_logs
    op.create_table(
        'biometric_audit_logs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), nullable=True, index=True),
        sa.Column('action', sa.String(length=100), nullable=False, index=True),
        sa.Column('identity_id', sa.String(length=36), nullable=True, index=True),
        sa.Column('template_id', sa.String(length=36), nullable=True),
        sa.Column('details_json', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='0', nullable=False, index=True),
    )


def downgrade() -> None:
    """Downgrade schema for Phase 7."""
    op.drop_table('biometric_audit_logs')
    op.drop_table('vehicle_events')
    op.drop_table('anpr_plate_records')
    op.drop_table('anpr_detections')
    op.drop_table('face_match_events')
    op.drop_table('face_enrollments')
    op.drop_table('face_templates')
    op.drop_table('face_identities')
