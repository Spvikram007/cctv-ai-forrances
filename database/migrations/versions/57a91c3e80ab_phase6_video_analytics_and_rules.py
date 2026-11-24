"""phase6_video_analytics_and_rules

Revision ID: 57a91c3e80ab
Revises: 49b81e4a112f
Create Date: 2026-11-24 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57a91c3e80ab'
down_revision: Union[str, Sequence[str], None] = '49b81e4a112f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema for Phase 6 Video Analytics and Intelligent Surveillance Rules."""
    # 1. analytics_zones
    op.create_table(
        'analytics_zones',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('channel_id', sa.String(length=64), nullable=False, index=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('zone_type', sa.String(length=50), server_default='INTRUSION', nullable=False, index=True),
        sa.Column('polygon_json', sa.Text(), nullable=False),
        sa.Column('color_hex', sa.String(length=10), server_default='#FF0000', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='0', nullable=False, index=True),
    )

    # 2. tripwire_lines
    op.create_table(
        'tripwire_lines',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('channel_id', sa.String(length=64), nullable=False, index=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('line_coords_json', sa.Text(), nullable=False),
        sa.Column('direction', sa.String(length=20), server_default='BIDIRECTIONAL', nullable=False),
        sa.Column('color_hex', sa.String(length=10), server_default='#00FF00', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='0', nullable=False, index=True),
    )

    # 3. analytics_rules
    op.create_table(
        'analytics_rules',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('channel_id', sa.String(length=64), nullable=False, index=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('rule_type', sa.String(length=50), nullable=False, index=True),
        sa.Column('zone_id', sa.String(length=36), nullable=True, index=True),
        sa.Column('tripwire_id', sa.String(length=36), nullable=True, index=True),
        sa.Column('target_classes_json', sa.Text(), server_default='["person", "car", "bus", "truck", "motorcycle", "bicycle"]', nullable=False),
        sa.Column('confidence_threshold', sa.Float(), server_default='0.5', nullable=False),
        sa.Column('min_dwell_time_sec', sa.Float(), server_default='5.0', nullable=False),
        sa.Column('severity', sa.String(length=20), server_default='WARNING', nullable=False),
        sa.Column('schedule_json', sa.Text(), nullable=True),
        sa.Column('trigger_recording', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('alarm_sound', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='0', nullable=False, index=True),
    )

    # 4. analytics_events
    op.create_table(
        'analytics_events',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('channel_id', sa.String(length=64), nullable=False, index=True),
        sa.Column('rule_id', sa.String(length=36), nullable=True, index=True),
        sa.Column('rule_name', sa.String(length=100), nullable=True),
        sa.Column('rule_type', sa.String(length=50), nullable=False, index=True),
        sa.Column('severity', sa.String(length=20), server_default='WARNING', nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=True, index=True),
        sa.Column('class_name', sa.String(length=50), nullable=False, index=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('dwell_time_sec', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('crossing_direction', sa.String(length=20), nullable=True),
        sa.Column('details_json', sa.Text(), nullable=True),
        sa.Column('snapshot_path', sa.String(length=500), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('is_acknowledged', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='0', nullable=False, index=True),
    )

    # 5. object_counts
    op.create_table(
        'object_counts',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('channel_id', sa.String(length=64), nullable=False, index=True),
        sa.Column('rule_id', sa.String(length=36), nullable=True, index=True),
        sa.Column('line_or_zone_id', sa.String(length=36), nullable=True, index=True),
        sa.Column('class_name', sa.String(length=50), nullable=False, index=True),
        sa.Column('direction', sa.String(length=20), nullable=False),
        sa.Column('count_delta', sa.Integer(), server_default='1', nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=False, index=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='0', nullable=False, index=True),
    )

    # 6. occupancy_records
    op.create_table(
        'occupancy_records',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('channel_id', sa.String(length=64), nullable=False, index=True),
        sa.Column('zone_id', sa.String(length=36), nullable=True, index=True),
        sa.Column('zone_name', sa.String(length=100), nullable=True),
        sa.Column('current_occupancy', sa.Integer(), server_default='0', nullable=False),
        sa.Column('person_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('vehicle_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_capacity', sa.Integer(), nullable=True),
        sa.Column('is_over_capacity', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='0', nullable=False, index=True),
    )

    # 7. heatmap_data
    op.create_table(
        'heatmap_data',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('channel_id', sa.String(length=64), nullable=False, index=True),
        sa.Column('time_window_start', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('time_window_end', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('grid_width', sa.Integer(), server_default='64', nullable=False),
        sa.Column('grid_height', sa.Integer(), server_default='36', nullable=False),
        sa.Column('density_matrix_json', sa.Text(), nullable=False),
        sa.Column('total_points', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default='0', nullable=False, index=True),
    )


def downgrade() -> None:
    """Downgrade schema for Phase 6."""
    op.drop_table('heatmap_data')
    op.drop_table('occupancy_records')
    op.drop_table('object_counts')
    op.drop_table('analytics_events')
    op.drop_table('analytics_rules')
    op.drop_table('tripwire_lines')
    op.drop_table('analytics_zones')
