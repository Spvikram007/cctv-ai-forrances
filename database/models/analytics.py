"""
Video Analytics and Intelligent Surveillance Rules Database Models.
Stores polygon zones, virtual tripwires, analytics rules, detection events,
counting statistics, occupancy records, and heatmap density matrices.
"""

from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime
from database.models.base import Base


class AnalyticsZone(Base):
    __tablename__ = "analytics_zones"

    channel_id = Column(String(64), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    zone_type = Column(String(50), default="INTRUSION", nullable=False, index=True)  # INTRUSION, LOITERING, EXCLUSION, COUNTING
    polygon_json = Column(Text, nullable=False)  # Normalized [[x, y], ...] coordinates in [0.0, 1.0]
    color_hex = Column(String(10), default="#FF0000", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class TripwireLine(Base):
    __tablename__ = "tripwire_lines"

    channel_id = Column(String(64), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    line_coords_json = Column(Text, nullable=False)  # Normalized {"pt1": [x1, y1], "pt2": [x2, y2]} in [0.0, 1.0]
    direction = Column(String(20), default="BIDIRECTIONAL", nullable=False)  # A_TO_B, B_TO_A, BIDIRECTIONAL
    color_hex = Column(String(10), default="#00FF00", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class AnalyticsRule(Base):
    __tablename__ = "analytics_rules"

    channel_id = Column(String(64), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    rule_type = Column(String(50), nullable=False, index=True)  # INTRUSION, LINE_CROSSING, LOITERING, COUNTING, OCCUPANCY
    zone_id = Column(String(36), nullable=True, index=True)
    tripwire_id = Column(String(36), nullable=True, index=True)
    target_classes_json = Column(Text, default='["person", "car", "bus", "truck", "motorcycle", "bicycle"]', nullable=False)
    confidence_threshold = Column(Float, default=0.50, nullable=False)
    min_dwell_time_sec = Column(Float, default=5.0, nullable=False)  # For loitering
    severity = Column(String(20), default="WARNING", nullable=False)  # INFO, WARNING, CRITICAL
    schedule_json = Column(Text, nullable=True)  # E.g. {"days": [0,1,2,3,4,5,6], "start_time": "00:00", "end_time": "23:59"}
    trigger_recording = Column(Boolean, default=True, nullable=False)
    alarm_sound = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    channel_id = Column(String(64), nullable=False, index=True)
    rule_id = Column(String(36), nullable=True, index=True)
    rule_name = Column(String(100), nullable=True)
    rule_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), default="WARNING", nullable=False)
    track_id = Column(Integer, nullable=True, index=True)
    class_name = Column(String(50), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    dwell_time_sec = Column(Float, default=0.0, nullable=False)
    crossing_direction = Column(String(20), nullable=True)
    details_json = Column(Text, nullable=True)
    snapshot_path = Column(String(500), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    is_acknowledged = Column(Boolean, default=False, nullable=False)


class ObjectCount(Base):
    __tablename__ = "object_counts"

    channel_id = Column(String(64), nullable=False, index=True)
    rule_id = Column(String(36), nullable=True, index=True)
    line_or_zone_id = Column(String(36), nullable=True, index=True)
    class_name = Column(String(50), nullable=False, index=True)
    direction = Column(String(20), nullable=False)  # ENTER (A_TO_B) or EXIT (B_TO_A)
    count_delta = Column(Integer, default=1, nullable=False)
    track_id = Column(Integer, nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)


class OccupancyRecord(Base):
    __tablename__ = "occupancy_records"

    channel_id = Column(String(64), nullable=False, index=True)
    zone_id = Column(String(36), nullable=True, index=True)
    zone_name = Column(String(100), nullable=True)
    current_occupancy = Column(Integer, default=0, nullable=False)
    person_count = Column(Integer, default=0, nullable=False)
    vehicle_count = Column(Integer, default=0, nullable=False)
    max_capacity = Column(Integer, nullable=True)
    is_over_capacity = Column(Boolean, default=False, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)


class HeatmapData(Base):
    __tablename__ = "heatmap_data"

    channel_id = Column(String(64), nullable=False, index=True)
    time_window_start = Column(DateTime(timezone=True), nullable=False, index=True)
    time_window_end = Column(DateTime(timezone=True), nullable=False, index=True)
    grid_width = Column(Integer, default=64, nullable=False)
    grid_height = Column(Integer, default=36, nullable=False)
    density_matrix_json = Column(Text, nullable=False)
    total_points = Column(Integer, default=0, nullable=False)
