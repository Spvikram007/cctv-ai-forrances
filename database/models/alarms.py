"""
Unified Alarm Management Database Models.
Phase 12 (F-046, Change ID: CHG-20261125-009).

Stores alarms, alarm raw events, lifecycle history audit log, alarm policies,
operator assignments, and notification delivery records.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, Index, text
from database.models.base import Base


class Alarm(Base):
    """
    Central persistent Alarm entity representing correlated and prioritized security,
    safety, operational, network, forensic, and hardware incidents.
    """
    __tablename__ = "alarms"

    event_id = Column(String(64), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False, default="SECURITY", index=True)
    source_subsystem = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False, default="MEDIUM", index=True)
    priority = Column(String(20), nullable=False, default="P3_NORMAL", index=True)
    status = Column(String(20), nullable=False, default="NEW", index=True)
    camera_id = Column(String(64), nullable=True, index=True)
    site_id = Column(String(64), nullable=True, index=True)
    zone_id = Column(String(64), nullable=True, index=True)
    first_detected_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_detected_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    occurrence_count = Column(Integer, nullable=False, default=1)
    assigned_operator = Column(String(100), nullable=True, index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(100), nullable=True)
    in_progress_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(100), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by = Column(String(100), nullable=True)
    related_alarm_id = Column(String(36), nullable=True, index=True)
    escalation_level = Column(Integer, nullable=False, default=0)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    next_escalation_deadline = Column(DateTime(timezone=True), nullable=True, index=True)
    evidence_refs = Column(Text, nullable=True)  # JSON-encoded evidence references
    alarm_metadata = Column(Text, nullable=True)  # JSON-encoded metadata payload
    dedup_key = Column(String(255), nullable=True, index=True)

    __table_args__ = (
        Index("idx_alarm_dedup_status", "dedup_key", "status"),
        Index("idx_alarm_deadline_status", "next_escalation_deadline", "status"),
        Index("idx_alarm_status_sev_time", "status", "severity", "last_detected_at"),
        Index(
            "uq_alarm_active_dedup",
            "dedup_key",
            unique=True,
            sqlite_where=text("status IN ('NEW', 'ACKNOWLEDGED', 'IN_PROGRESS', 'REOPENED') AND is_deleted = 0 AND dedup_key IS NOT NULL"),
            postgresql_where=text("status IN ('NEW', 'ACKNOWLEDGED', 'IN_PROGRESS', 'REOPENED') AND is_deleted = FALSE AND dedup_key IS NOT NULL"),
        ),
    )


class AlarmEvent(Base):
    """
    Subsystem-level normalized atomic event linked to an Alarm record.
    Provides complete provenance from raw sensor/AI detection to alarm resolution.
    """
    __tablename__ = "alarm_events"

    alarm_id = Column(String(36), nullable=True, index=True)
    source_event_id = Column(String(64), nullable=False, index=True)
    source_subsystem = Column(String(50), nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    camera_id = Column(String(64), nullable=True, index=True)
    event_timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    received_timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    confidence = Column(Float, nullable=True)
    event_metadata = Column(Text, nullable=True)  # JSON-encoded raw event payload
    processing_status = Column(String(30), nullable=False, default="PROCESSED")


class AlarmHistory(Base):
    """
    Append-only lifecycle audit trail recording every state change, note,
    assignment, escalation, and resolution for forensic traceability.
    Secured with rolling SHA-256 hash chains.
    """
    __tablename__ = "alarm_history"

    alarm_id = Column(String(36), nullable=False, index=True)
    entry_index = Column(Integer, nullable=False, default=0)
    previous_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)
    operator = Column(String(100), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    action = Column(String(50), nullable=False, index=True)
    reason = Column(String(255), nullable=True)
    comments = Column(Text, nullable=True)
    prev_hash = Column(String(64), nullable=True)
    entry_hash = Column(String(64), nullable=True)


class AlarmPolicy(Base):
    """
    Configurable classification, severity, deduplication, and escalation rules.
    """
    __tablename__ = "alarm_policies"

    rule_name = Column(String(100), nullable=False, unique=True)
    event_source = Column(String(50), nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    severity = Column(String(20), nullable=False, default="MEDIUM")
    priority = Column(String(20), nullable=False, default="P3_NORMAL")
    enabled = Column(Boolean, nullable=False, default=True)
    dedup_window_seconds = Column(Integer, nullable=False, default=60)
    escalation_timeout_seconds = Column(Integer, nullable=False, default=300)
    escalation_target_role = Column(String(50), nullable=False, default="SUPERVISOR")
    notification_channels = Column(Text, nullable=False, default='["DESKTOP", "IN_APP"]')
    auto_resolve_timeout_seconds = Column(Integer, nullable=False, default=0)


class AlarmAssignment(Base):
    """
    Audit log of operator assignment and handoff actions.
    """
    __tablename__ = "alarm_assignments"

    alarm_id = Column(String(36), nullable=False, index=True)
    assigned_user = Column(String(100), nullable=False, index=True)
    assigned_by = Column(String(100), nullable=False)
    assigned_timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    assignment_reason = Column(String(255), nullable=True)


class AlarmNotification(Base):
    """
    Record of sent desktop, audio, webhook, or in-app notifications with durable retry state.
    """
    __tablename__ = "alarm_notifications"

    alarm_id = Column(String(36), nullable=False, index=True)
    channel = Column(String(30), nullable=False, index=True)
    recipient = Column(String(100), nullable=False)
    delivery_status = Column(String(20), nullable=False, default="DELIVERED", index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    payload = Column(Text, nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
