"""
Central Alarm Engine Service.
Phase 12 & 12.1 (F-046, Change ID: CHG-20261125-010).

Coordinates event ingestion, normalization, policy evaluation, deduplication,
correlation, persistent database transactions, SLA escalations, notifications,
cryptographically-chained audit trails, and RBAC lifecycle state machine.
"""

import json
import time
import queue
import hashlib
import threading
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
from sqlalchemy import desc, func, and_, or_
from sqlalchemy.exc import IntegrityError

from database.database_manager import db_manager
from database.models.alarms import (
    Alarm,
    AlarmEvent,
    AlarmHistory,
    AlarmPolicy,
    AlarmAssignment,
    AlarmNotification,
)
from engines.alarm_engine.enums import (
    AlarmSeverity,
    AlarmPriority,
    AlarmStatus,
    AlarmCategory,
    AlarmAction,
)
from engines.alarm_engine.normalizer import (
    NormalizedAlarmEvent,
    EventNormalizer,
)
from engines.alarm_engine.policy_engine import AlarmPolicyEngine
from engines.alarm_engine.deduplicator import AlarmDeduplicator
from engines.alarm_engine.correlator import AlarmCorrelator
from engines.alarm_engine.escalator import AlarmEscalationManager
from engines.alarm_engine.notification import AlarmNotificationDispatcher
from engines.alarm_engine.checkpoints import create_alarm_checkpoint, verify_checkpoint_integrity
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("alarm_service")


# RBAC Role Definitions & Action Permissions
ROLE_PERMISSIONS: Dict[str, set] = {
    "VIEWER": {"VIEW"},
    "OPERATOR": {"VIEW", "ACKNOWLEDGE", "INVESTIGATE", "RESOLVE", "ADD_NOTE", "ESCALATE"},
    "SUPERVISOR": {"VIEW", "ACKNOWLEDGE", "INVESTIGATE", "ASSIGN", "RESOLVE", "CLOSE", "REOPEN", "ADD_NOTE", "ESCALATE", "CONFIGURE_POLICY", "PURGE"},
    "INVESTIGATOR": {"VIEW", "ACKNOWLEDGE", "INVESTIGATE", "RESOLVE", "CLOSE", "ADD_NOTE", "ACCESS_EVIDENCE", "LINK"},
    "ADMIN": {"VIEW", "ACKNOWLEDGE", "INVESTIGATE", "ASSIGN", "RESOLVE", "CLOSE", "REOPEN", "ADD_NOTE", "ESCALATE", "ACCESS_EVIDENCE", "LINK", "CONFIGURE_POLICY", "ADMIN_OVERRIDE", "DELETE", "PURGE"},
}


class AlarmEngineService:
    """Core alarm engine coordinating all alarm operations, workers, and storage."""

    def __init__(self, max_queue_size: int = 10000) -> None:
        self.policy_engine = AlarmPolicyEngine()
        self.deduplicator = AlarmDeduplicator(default_window_seconds=60)
        self.correlator = AlarmCorrelator(correlation_window_sec=60.0)
        self.escalator = AlarmEscalationManager()
        self.notification_dispatcher = AlarmNotificationDispatcher(suppression_cooldown_sec=30.0)

        # Thread-safe bounded asynchronous event ingestion queue
        self._stop_event = threading.Event()
        self._ingestion_queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._worker_running = True
        self._worker_thread = threading.Thread(target=self._process_queue_loop, daemon=True, name="AlarmIngestionWorker")
        self._worker_thread.start()

        # SLA escalation watchdog thread
        self._watchdog_thread = threading.Thread(target=self._escalation_watchdog_loop, daemon=True, name="AlarmSLAWatchdog")
        self._watchdog_thread.start()

        # Recover active deduplication signatures and pending SLA escalations on startup
        try:
            with db_manager.get_session() as session:
                recovered_dedup = self.deduplicator.recover_from_database(session)
                recovered_esc = self.escalator.recover_pending_escalations(session=session)
                logger.info(
                    "Startup recovery complete: %d active deduplication signatures, %d pending SLA escalations",
                    recovered_dedup,
                    len(recovered_esc),
                )
        except Exception as e:
            logger.debug("Startup alarm recovery note: %s", e)

    def stop(self) -> None:
        """Gracefully shuts down background worker threads."""
        self._worker_running = False
        self._stop_event.set()
        try:
            self._ingestion_queue.put_nowait(None)
        except Exception:
            pass
        if hasattr(self, "_worker_thread") and self._worker_thread.is_alive():
            try:
                self._worker_thread.join(timeout=1.0)
            except Exception:
                pass
        if hasattr(self, "_watchdog_thread") and self._watchdog_thread.is_alive():
            try:
                self._watchdog_thread.join(timeout=1.0)
            except Exception:
                pass

    def enqueue_event(self, source_subsystem: str, event_type: str, data: Dict[str, Any]) -> bool:
        """
        Asynchronously queues a raw subsystem event for non-blocking processing.
        Returns False if queue is saturated (backpressure protection).
        """
        try:
            self._ingestion_queue.put_nowait((source_subsystem, event_type, data))
            return True
        except queue.Full:
            logger.error("Alarm ingestion queue full! Dropping event from %s:%s", source_subsystem, event_type)
            return False

    def _process_queue_loop(self) -> None:
        """Background worker thread draining the ingestion queue."""
        while self._worker_running:
            try:
                item = self._ingestion_queue.get(timeout=1.0)
                if item is None:
                    break
                source, event_type, data = item
                self.process_raw_event(source, event_type, data)
                self._ingestion_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                try:
                    logger.error("Error processing queued alarm event: %s", e)
                except Exception:
                    pass

    def _escalation_watchdog_loop(self) -> None:
        """Periodic background evaluation of SLA deadlines every 10 seconds."""
        while self._worker_running:
            try:
                if self._stop_event.wait(timeout=10.0):
                    break
                if not self._worker_running:
                    break
                escalated = self.escalator.check_and_escalate_pending_alarms()
                for alarm_id in escalated:
                    # Notify about escalation
                    bus.publish("alarm.escalated", {"alarm_id": alarm_id}, source="alarm_escalator")
            except Exception as e:
                logger.debug("Escalation watchdog exception: %s", e)

    # -------------------------------------------------------------------------
    # Cryptographic Hash Chaining Helpers
    # -------------------------------------------------------------------------
    @staticmethod
    def _format_timestamp(ts: Any) -> str:
        """Standardizes timestamps to UTC string format across aware and naive SQLite models."""
        if isinstance(ts, datetime):
            if ts.tzinfo is not None:
                ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
            return ts.strftime("%Y-%m-%d %H:%M:%S.%f")
        return str(ts)

    @classmethod
    def compute_history_hash(
        cls,
        entry_index: int,
        alarm_id: str,
        prev_hash: str,
        previous_status: Optional[str],
        new_status: str,
        operator: str,
        action: str,
        timestamp: Any,
        reason: Optional[str],
        comments: Optional[str],
    ) -> str:
        """Computes deterministic SHA-256 rolling digest for alarm audit history entry."""
        ts_str = cls._format_timestamp(timestamp)
        canonical = (
            f"{entry_index}|{alarm_id}|{prev_hash}|{previous_status or ''}|"
            f"{new_status}|{operator}|{action}|{ts_str}|{reason or ''}|{comments or ''}"
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _append_history_entry(
        self,
        session: Any,
        alarm_id: str,
        previous_status: Optional[str],
        new_status: str,
        operator: str,
        action: str,
        timestamp: Optional[datetime] = None,
        reason: Optional[str] = None,
        comments: Optional[str] = None,
    ) -> AlarmHistory:
        """
        Appends an immutable, sequentially-indexed, hash-chained audit record.
        Maintains an unbroken cryptographic link across all lifecycle events.
        """
        now = timestamp or datetime.now(timezone.utc)
        last_entry = (
            session.query(AlarmHistory)
            .filter(AlarmHistory.alarm_id == alarm_id)
            .order_by(AlarmHistory.entry_index.desc())
            .first()
        )
        if last_entry is None:
            entry_index = 0
            prev_hash = "0" * 64
        else:
            entry_index = (last_entry.entry_index or 0) + 1
            prev_hash = last_entry.entry_hash or ("0" * 64)

        entry_hash = self.compute_history_hash(
            entry_index=entry_index,
            alarm_id=alarm_id,
            prev_hash=prev_hash,
            previous_status=previous_status,
            new_status=new_status,
            operator=operator,
            action=action,
            timestamp=now,
            reason=reason,
            comments=comments,
        )

        history = AlarmHistory(
            alarm_id=alarm_id,
            entry_index=entry_index,
            previous_status=previous_status,
            new_status=new_status,
            operator=operator,
            timestamp=now,
            action=action,
            reason=reason,
            comments=comments,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )
        session.add(history)
        return history

    # -------------------------------------------------------------------------
    # Ingestion & Normalization
    # -------------------------------------------------------------------------
    def process_raw_event(self, source_subsystem: str, event_type: str, data: Dict[str, Any]) -> Optional[str]:
        """Normalizes and processes a raw event synchronously."""
        try:
            norm_event = EventNormalizer.normalize(source_subsystem, event_type, data)
            return self.process_normalized_event(norm_event)
        except Exception as e:
            logger.error("Failed processing raw event %s:%s - %s", source_subsystem, event_type, e)
            return None

    def process_normalized_event(self, event: NormalizedAlarmEvent) -> str:
        """
        Evaluates policy, checks deduplication with DB fallback, correlates with parent incidents,
        persists Alarm and AlarmEvent records, and dispatches notifications.
        """
        policy = self.policy_engine.get_policy(event.source_subsystem, event.event_type)
        if not policy.enabled:
            logger.debug("Event %s dropped: Policy disabled", event.event_type)
            return ""

        # Fast in-memory deduplication check first
        dedup_window = policy.dedup_window_seconds
        is_dup, existing_alarm_id, occurrence_count = self.deduplicator.check_and_update(
            dedup_key=event.dedup_key or "",
            window_seconds=dedup_window,
            session=None,
        )
        if not is_dup and event.dedup_key:
            # Fallback to persistent database check only if not matched in memory
            with db_manager.get_session() as session:
                is_dup, existing_alarm_id, occurrence_count = self.deduplicator.check_and_update(
                    dedup_key=event.dedup_key,
                    window_seconds=dedup_window,
                    session=session,
                )

        if is_dup and existing_alarm_id:
            # Update existing active alarm
            self._update_duplicate_alarm(existing_alarm_id, event, occurrence_count)
            # Dispatch repeat notification if cooldown permits
            self.notification_dispatcher.dispatch(
                alarm_id=existing_alarm_id,
                title=f"{event.title} (x{occurrence_count})",
                severity=event.severity.value,
                category=event.category.value,
                camera_id=event.camera_id,
                channels=policy.notification_channels,
            )
            return existing_alarm_id

        # Check multi-event correlation
        related_alarm_id = self.correlator.find_correlation(event)

        # Create new Alarm record
        alarm_id = self._create_new_alarm(event, policy, related_alarm_id)

        # Register in deduplication and correlation trackers
        if event.dedup_key:
            self.deduplicator.register_alarm(event.dedup_key, alarm_id, status=AlarmStatus.NEW.value)

        if event.source_subsystem.upper() == "NETWORK" and ("GATEWAY" in event.event_type.upper() or "SWITCH" in event.event_type.upper()):
            root_key = f"NETWORK:{event.event_type.upper()}:{event.metadata.get('gateway_ip', 'default')}"
            self.correlator.register_parent_incident(root_key, alarm_id)

        if event.source_subsystem.upper() == "STREAM" and "DISCONNECTED" in event.event_type.upper() and event.camera_id:
            self.correlator.register_camera_offline(event.camera_id, alarm_id)

        # Dispatch notifications
        self.notification_dispatcher.dispatch(
            alarm_id=alarm_id,
            title=event.title,
            severity=event.severity.value,
            category=event.category.value,
            camera_id=event.camera_id,
            channels=policy.notification_channels,
        )

        return alarm_id

    def _create_new_alarm(
        self,
        event: NormalizedAlarmEvent,
        policy: Any,
        related_alarm_id: Optional[str] = None,
    ) -> str:
        """Persists a new Alarm, AlarmEvent, and initial AlarmHistory entry with cryptographic hash chain."""
        now = datetime.now(timezone.utc)
        deadline = now + timedelta(seconds=policy.escalation_timeout_seconds) if policy.escalation_timeout_seconds > 0 else None

        try:
            with db_manager.get_session() as session:
                new_alarm = Alarm(
                    event_id=event.event_id,
                    title=event.title,
                    description=event.description,
                    category=event.category.value,
                    source_subsystem=event.source_subsystem,
                    severity=event.severity.value,
                    priority=event.priority.value,
                    status=AlarmStatus.NEW.value,
                    camera_id=event.camera_id,
                    site_id=event.site_id,
                    zone_id=event.zone_id,
                    first_detected_at=event.timestamp,
                    last_detected_at=event.timestamp,
                    occurrence_count=1,
                    related_alarm_id=related_alarm_id,
                    escalation_level=0,
                    next_escalation_deadline=deadline,
                    evidence_refs=json.dumps(event.evidence_refs) if event.evidence_refs else None,
                    alarm_metadata=json.dumps(event.metadata) if event.metadata else None,
                    dedup_key=event.dedup_key,
                )
                session.add(new_alarm)
                session.flush()

                # Record atomic event log
                alarm_event = AlarmEvent(
                    alarm_id=new_alarm.id,
                    source_event_id=event.event_id,
                    source_subsystem=event.source_subsystem,
                    event_type=event.event_type,
                    camera_id=event.camera_id,
                    event_timestamp=event.timestamp,
                    received_timestamp=now,
                    confidence=event.confidence,
                    event_metadata=json.dumps(event.metadata) if event.metadata else None,
                    processing_status="PROCESSED",
                )
                session.add(alarm_event)

                # Record creation audit trail with rolling hash chain
                self._append_history_entry(
                    session=session,
                    alarm_id=new_alarm.id,
                    previous_status=None,
                    new_status=AlarmStatus.NEW.value,
                    operator="SYSTEM",
                    timestamp=now,
                    action=AlarmAction.CREATED.value,
                    reason="Event normalized and ingested",
                    comments=f"Created from {event.source_subsystem}:{event.event_type}",
                )
                alarm_id = str(new_alarm.id)
        except IntegrityError:
            # Race condition under concurrent workers: another thread committed an active alarm with the same dedup_key
            logger.info("Database unique constraint triggered for dedup_key '%s' — resolving race via atomic update", event.dedup_key)
            with db_manager.get_session() as session:
                existing = (
                    session.query(Alarm)
                    .filter(
                        Alarm.dedup_key == event.dedup_key,
                        Alarm.status.in_([AlarmStatus.NEW.value, AlarmStatus.ACKNOWLEDGED.value, AlarmStatus.IN_PROGRESS.value, AlarmStatus.REOPENED.value]),
                        Alarm.is_deleted == False,
                    )
                    .first()
                )
                if existing:
                    existing_id = str(existing.id)
                    self._update_duplicate_alarm(existing_id, event, existing.occurrence_count + 1)
                    if event.dedup_key:
                        self.deduplicator.register_alarm(event.dedup_key, existing_id, status=existing.status)
                    return existing_id
            raise

        try:
            logger.info("Created new alarm %s [%s] - Severity: %s", alarm_id, event.title, event.severity.value)
        except Exception:
            pass
        bus.publish("alarm.created", {"alarm_id": alarm_id, "title": event.title, "severity": event.severity.value}, source="alarm_engine")
        return alarm_id

    def _update_duplicate_alarm(
        self,
        alarm_id: str,
        event: NormalizedAlarmEvent,
        occurrence_count: int,
    ) -> None:
        """Updates last detected timestamp and occurrence counter for duplicate bursts using atomic SQL."""
        now = datetime.now(timezone.utc)
        with db_manager.get_session() as session:
            # Atomic SQL increment to avoid lost updates under concurrent workers
            session.query(Alarm).filter(Alarm.id == alarm_id).update({
                Alarm.last_detected_at: event.timestamp,
                Alarm.occurrence_count: Alarm.occurrence_count + 1,
            }, synchronize_session=False)

            # Append raw event
            alarm_event = AlarmEvent(
                alarm_id=alarm_id,
                source_event_id=event.event_id,
                source_subsystem=event.source_subsystem,
                event_type=event.event_type,
                camera_id=event.camera_id,
                event_timestamp=event.timestamp,
                received_timestamp=now,
                confidence=event.confidence,
                event_metadata=json.dumps(event.metadata) if event.metadata else None,
                processing_status="DUPLICATE_MERGED",
            )
            session.add(alarm_event)

    # -------------------------------------------------------------------------
    # Lifecycle Transitions & RBAC Actions
    # -------------------------------------------------------------------------
    @classmethod
    def _validate_permission(cls, role: str, required_action: str) -> None:
        """Validates operator role against action permissions."""
        role_upper = (role or "OPERATOR").upper()
        allowed_actions = ROLE_PERMISSIONS.get(role_upper, {"VIEW"})
        if required_action not in allowed_actions and "ADMIN_OVERRIDE" not in allowed_actions:
            raise PermissionError(f"Role '{role_upper}' lacks permission '{required_action}' for alarm action.")

    def acknowledge_alarm(self, alarm_id: str, operator: str, role: str = "OPERATOR", comments: str = "") -> bool:
        """Acknowledges an alarm, stopping initial acknowledgment SLA."""
        self._validate_permission(role, "ACKNOWLEDGE")
        now = datetime.now(timezone.utc)

        with db_manager.get_session() as session:
            alarm = session.query(Alarm).filter(Alarm.id == alarm_id, Alarm.is_deleted == False).first()
            if not alarm:
                return False

            prev_status = alarm.status
            alarm.status = AlarmStatus.ACKNOWLEDGED.value
            alarm.acknowledged_at = now
            alarm.acknowledged_by = operator
            # Once acknowledged, clear acknowledgment SLA deadline
            alarm.next_escalation_deadline = None

            self._append_history_entry(
                session=session,
                alarm_id=alarm.id,
                previous_status=prev_status,
                new_status=AlarmStatus.ACKNOWLEDGED.value,
                operator=operator,
                timestamp=now,
                action=AlarmAction.ACKNOWLEDGED.value,
                reason="Operator acknowledged incident",
                comments=comments or "Acknowledged by operator",
            )

        self.deduplicator.update_status(alarm_id, AlarmStatus.ACKNOWLEDGED.value)
        bus.publish("alarm.acknowledged", {"alarm_id": alarm_id, "operator": operator}, source="alarm_engine")
        logger.info("Alarm %s acknowledged by %s", alarm_id, operator)
        return True

    def assign_alarm(
        self,
        alarm_id: str,
        assigned_user: str,
        operator: str,
        role: str = "SUPERVISOR",
        reason: str = "",
    ) -> bool:
        """Assigns an alarm to an investigator or operator."""
        self._validate_permission(role, "ASSIGN")
        now = datetime.now(timezone.utc)

        with db_manager.get_session() as session:
            alarm = session.query(Alarm).filter(Alarm.id == alarm_id, Alarm.is_deleted == False).first()
            if not alarm:
                return False

            alarm.assigned_operator = assigned_user

            assignment = AlarmAssignment(
                alarm_id=alarm.id,
                assigned_user=assigned_user,
                assigned_by=operator,
                assigned_timestamp=now,
                assignment_reason=reason or "Incident assigned for investigation",
            )
            session.add(assignment)

            self._append_history_entry(
                session=session,
                alarm_id=alarm.id,
                previous_status=alarm.status,
                new_status=alarm.status,
                operator=operator,
                timestamp=now,
                action=AlarmAction.ASSIGNED.value,
                reason=f"Assigned to {assigned_user}",
                comments=reason,
            )

        bus.publish("alarm.assigned", {"alarm_id": alarm_id, "assigned_user": assigned_user}, source="alarm_engine")
        logger.info("Alarm %s assigned to %s by %s", alarm_id, assigned_user, operator)
        return True

    def start_investigation(self, alarm_id: str, operator: str, role: str = "OPERATOR", comments: str = "") -> bool:
        """Transitions an alarm to IN_PROGRESS."""
        self._validate_permission(role, "INVESTIGATE")
        now = datetime.now(timezone.utc)

        with db_manager.get_session() as session:
            alarm = session.query(Alarm).filter(Alarm.id == alarm_id, Alarm.is_deleted == False).first()
            if not alarm:
                return False

            prev_status = alarm.status
            alarm.status = AlarmStatus.IN_PROGRESS.value
            alarm.in_progress_at = now
            if not alarm.assigned_operator:
                alarm.assigned_operator = operator

            self._append_history_entry(
                session=session,
                alarm_id=alarm.id,
                previous_status=prev_status,
                new_status=AlarmStatus.IN_PROGRESS.value,
                operator=operator,
                timestamp=now,
                action=AlarmAction.STATUS_CHANGE.value,
                reason="Investigation commenced",
                comments=comments or "Investigation in progress",
            )

        self.deduplicator.update_status(alarm_id, AlarmStatus.IN_PROGRESS.value)
        bus.publish("alarm.in_progress", {"alarm_id": alarm_id, "operator": operator}, source="alarm_engine")
        return True

    def resolve_alarm(
        self,
        alarm_id: str,
        operator: str,
        role: str = "OPERATOR",
        reason: str = "False alarm / Verified resolved",
        comments: str = "",
        resolution_notes: str = "",
    ) -> bool:
        """Resolves an alarm."""
        self._validate_permission(role, "RESOLVE")
        now = datetime.now(timezone.utc)
        comments = comments or resolution_notes or ""

        cam_id = None
        with db_manager.get_session() as session:
            alarm = session.query(Alarm).filter(Alarm.id == alarm_id, Alarm.is_deleted == False).first()
            if not alarm:
                return False

            cam_id = alarm.camera_id
            prev_status = alarm.status
            alarm.status = AlarmStatus.RESOLVED.value
            alarm.resolved_at = now
            alarm.resolved_by = operator
            alarm.next_escalation_deadline = None

            self._append_history_entry(
                session=session,
                alarm_id=alarm.id,
                previous_status=prev_status,
                new_status=AlarmStatus.RESOLVED.value,
                operator=operator,
                timestamp=now,
                action=AlarmAction.RESOLVED.value,
                reason=reason,
                comments=comments,
            )

        self.deduplicator.update_status(alarm_id, AlarmStatus.RESOLVED.value)
        if cam_id:
            self.correlator.clear_camera_offline(cam_id)

        bus.publish("alarm.resolved", {"alarm_id": alarm_id, "operator": operator}, source="alarm_engine")
        logger.info("Alarm %s resolved by %s: %s", alarm_id, operator, reason)
        return True

    def close_alarm(
        self,
        alarm_id: str,
        operator: str,
        role: str = "SUPERVISOR",
        comments: str = "",
        reason: str = "",
    ) -> bool:
        """Closes an alarm permanently after supervisory review."""
        self._validate_permission(role, "CLOSE")
        now = datetime.now(timezone.utc)
        comments = comments or reason or "Case closed"
        reason_text = reason or "Closed after review"

        with db_manager.get_session() as session:
            alarm = session.query(Alarm).filter(Alarm.id == alarm_id, Alarm.is_deleted == False).first()
            if not alarm:
                return False

            prev_status = alarm.status
            alarm.status = AlarmStatus.CLOSED.value
            alarm.closed_at = now
            alarm.closed_by = operator
            alarm.next_escalation_deadline = None

            self._append_history_entry(
                session=session,
                alarm_id=alarm.id,
                previous_status=prev_status,
                new_status=AlarmStatus.CLOSED.value,
                operator=operator,
                timestamp=now,
                action=AlarmAction.CLOSED.value,
                reason=reason_text,
                comments=comments,
            )

        self.deduplicator.update_status(alarm_id, AlarmStatus.CLOSED.value)
        bus.publish("alarm.closed", {"alarm_id": alarm_id, "operator": operator}, source="alarm_engine")
        logger.info("Alarm %s closed by %s", alarm_id, operator)
        return True

    def reopen_alarm(
        self,
        alarm_id: str,
        operator: str,
        role: str = "SUPERVISOR",
        reason: str = "Incident re-occurred or requires further review",
        comments: str = "",
    ) -> bool:
        """Reopens a previously resolved or closed alarm."""
        self._validate_permission(role, "REOPEN")
        now = datetime.now(timezone.utc)

        with db_manager.get_session() as session:
            alarm = session.query(Alarm).filter(Alarm.id == alarm_id, Alarm.is_deleted == False).first()
            if not alarm:
                return False

            prev_status = alarm.status
            alarm.status = AlarmStatus.REOPENED.value
            alarm.next_escalation_deadline = now + timedelta(seconds=300)

            self._append_history_entry(
                session=session,
                alarm_id=alarm.id,
                previous_status=prev_status,
                new_status=AlarmStatus.REOPENED.value,
                operator=operator,
                timestamp=now,
                action=AlarmAction.REOPENED.value,
                reason=reason,
                comments=comments,
            )

        self.deduplicator.update_status(alarm_id, AlarmStatus.REOPENED.value)
        bus.publish("alarm.reopened", {"alarm_id": alarm_id, "operator": operator}, source="alarm_engine")
        logger.info("Alarm %s reopened by %s: %s", alarm_id, operator, reason)
        return True

    def add_operator_note(
        self,
        alarm_id: str,
        operator: str,
        note_text: str = "",
        role: str = "OPERATOR",
        note: Optional[str] = None,
    ) -> bool:
        """Appends an operator note to the alarm history."""
        self._validate_permission(role, "ADD_NOTE")
        now = datetime.now(timezone.utc)
        note_content = (note_text or note or "").strip()

        with db_manager.get_session() as session:
            alarm = session.query(Alarm).filter(Alarm.id == alarm_id, Alarm.is_deleted == False).first()
            if not alarm:
                return False

            self._append_history_entry(
                session=session,
                alarm_id=alarm.id,
                previous_status=alarm.status,
                new_status=alarm.status,
                operator=operator,
                timestamp=now,
                action=AlarmAction.NOTE_ADDED.value,
                reason="Operator observation",
                comments=note_content,
            )

        bus.publish("alarm.note_added", {"alarm_id": alarm_id, "operator": operator}, source="alarm_engine")
        return True

    def escalate_manually(
        self,
        alarm_id: str,
        operator: str,
        role: str = "OPERATOR",
        reason: str = "Operator manual escalation",
    ) -> bool:
        """Allows an operator or supervisor to escalate an incident manually."""
        self._validate_permission(role, "ESCALATE")
        now = datetime.now(timezone.utc)

        with db_manager.get_session() as session:
            alarm = session.query(Alarm).filter(Alarm.id == alarm_id, Alarm.is_deleted == False).first()
            if not alarm:
                return False

            alarm.escalation_level += 1
            alarm.escalated_at = now
            alarm.next_escalation_deadline = now + timedelta(seconds=600)

            self._append_history_entry(
                session=session,
                alarm_id=alarm.id,
                previous_status=alarm.status,
                new_status=alarm.status,
                operator=operator,
                timestamp=now,
                action=AlarmAction.ESCALATED.value,
                reason=reason,
                comments=f"Manual escalation by {operator} to Level {alarm.escalation_level}",
            )

        bus.publish("alarm.escalated", {"alarm_id": alarm_id, "operator": operator}, source="alarm_engine")
        return True

    def audit_evidence_access(
        self,
        alarm_id: str,
        operator: str,
        role: str = "INVESTIGATOR",
        evidence_type: str = "SNAPSHOT",
        comments: str = "",
    ) -> bool:
        """
        Enforces RBAC permissions and records an immutable, hash-chained audit record
        whenever sensitive biometric or ANPR evidence is accessed or viewed.
        """
        self._validate_permission(role, "ACCESS_EVIDENCE")
        now = datetime.now(timezone.utc)
        with db_manager.get_session() as session:
            alarm = session.query(Alarm).filter(Alarm.id == alarm_id, Alarm.is_deleted == False).first()
            if not alarm:
                return False

            self._append_history_entry(
                session=session,
                alarm_id=alarm.id,
                previous_status=alarm.status,
                new_status=alarm.status,
                operator=operator,
                action=AlarmAction.EVIDENCE_VIEWED.value,
                timestamp=now,
                reason=f"Evidence access ({evidence_type})",
                comments=comments or f"Operator {operator} ({role}) inspected {evidence_type} evidence",
            )

        bus.publish("alarm.evidence_accessed", {
            "alarm_id": alarm_id,
            "operator": operator,
            "role": role,
            "evidence_type": evidence_type,
        }, source="alarm_engine")
        logger.info("Evidence access audited for alarm %s by %s (%s)", alarm_id, operator, role)
        return True

    def verify_history_integrity(self, alarm_id: str, custom_checkpoint_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Cryptographically verifies the rolling SHA-256 hash chain of an alarm's audit history
        and cross-validates against external authoritative checkpoints to detect forgery/reconstruction.
        """
        with db_manager.get_session() as session:
            entries = (
                session.query(AlarmHistory)
                .filter(AlarmHistory.alarm_id == alarm_id, AlarmHistory.is_deleted == False)
                .order_by(AlarmHistory.entry_index.asc(), AlarmHistory.timestamp.asc())
                .all()
            )
            if not entries:
                return {
                    "valid": True,
                    "total_entries": 0,
                    "broken_at_index": None,
                    "details": "No audit trail entries recorded.",
                    "checkpoint_verified": False,
                }

            expected_prev_hash = "0" * 64
            for idx, entry in enumerate(entries):
                if entry.entry_index != idx:
                    return {
                        "valid": False,
                        "total_entries": len(entries),
                        "broken_at_index": idx,
                        "details": f"Index discontinuity: expected index {idx}, found {entry.entry_index}.",
                        "checkpoint_verified": False,
                    }

                if entry.prev_hash != expected_prev_hash:
                    return {
                        "valid": False,
                        "total_entries": len(entries),
                        "broken_at_index": idx,
                        "details": f"Hash chain linkage broken at index {idx}: expected prev_hash {expected_prev_hash}, found {entry.prev_hash}.",
                        "checkpoint_verified": False,
                    }

                recomputed = self.compute_history_hash(
                    entry_index=entry.entry_index,
                    alarm_id=entry.alarm_id,
                    prev_hash=entry.prev_hash,
                    previous_status=entry.previous_status,
                    new_status=entry.new_status,
                    operator=entry.operator,
                    action=entry.action,
                    timestamp=entry.timestamp,
                    reason=entry.reason,
                    comments=entry.comments,
                )
                if entry.entry_hash != recomputed:
                    return {
                        "valid": False,
                        "total_entries": len(entries),
                        "broken_at_index": idx,
                        "details": f"Cryptographic digest mismatch at index {idx}: stored {entry.entry_hash}, recomputed {recomputed}.",
                        "checkpoint_verified": False,
                    }

                expected_prev_hash = entry.entry_hash

            # Cross-verify against external authoritative filesystem checkpoints
            cp_result = verify_checkpoint_integrity(alarm_id, entries, custom_path=custom_checkpoint_path)
            if not cp_result.get("checkpoint_verified", True):
                violated_idx = None
                if "violated_checkpoint" in cp_result:
                    violated_idx = cp_result["violated_checkpoint"].get("entry_index")
                return {
                    "valid": False,
                    "total_entries": len(entries),
                    "broken_at_index": violated_idx,
                    "details": cp_result["details"],
                    "checkpoint_violation": True,
                    "checkpoint_verified": False,
                }

            return {
                "valid": True,
                "total_entries": len(entries),
                "broken_at_index": None,
                "details": f"Cryptographic integrity successfully verified across all {len(entries)} audit entries (checkpoints verified: {cp_result.get('has_checkpoints', False)}).",
                "checkpoint_verified": cp_result.get("has_checkpoints", False),
            }

    def create_history_checkpoint(self, alarm_id: str, custom_path: Optional[str] = None) -> Dict[str, Any]:
        """Creates an external signed checkpoint anchoring the latest history entry."""
        with db_manager.get_session() as session:
            entries = (
                session.query(AlarmHistory)
                .filter(AlarmHistory.alarm_id == alarm_id, AlarmHistory.is_deleted == False)
                .order_by(AlarmHistory.entry_index.asc())
                .all()
            )
            if not entries:
                raise ValueError(f"No history entries found for alarm '{alarm_id}'")
            latest = entries[-1]
            return create_alarm_checkpoint(
                alarm_id=alarm_id,
                entry_index=latest.entry_index,
                entry_hash=latest.entry_hash,
                total_entries=len(entries),
                custom_path=custom_path,
            )

    def soft_delete_alarm(
        self,
        alarm_id: str,
        operator: str,
        role: str = "ADMIN",
        reason: str = "Administrative deletion",
    ) -> bool:
        """Soft-deletes an alarm with RBAC enforcement and append-only audit trail."""
        self._validate_permission(role, "DELETE")
        now = datetime.now(timezone.utc)
        with db_manager.get_session() as session:
            alarm = session.query(Alarm).filter(Alarm.id == alarm_id, Alarm.is_deleted == False).first()
            if not alarm:
                return False
            alarm.is_deleted = True
            self._append_history_entry(
                session=session,
                alarm_id=alarm.id,
                previous_status=alarm.status,
                new_status=alarm.status,
                operator=operator,
                action=AlarmAction.DELETED.value,
                timestamp=now,
                reason=reason,
                comments=f"Soft deleted by {operator}",
            )
        bus.publish("alarm.deleted", {"alarm_id": alarm_id, "operator": operator}, source="alarm_engine")
        return True

    def purge_expired_alarms(
        self,
        retention_days: int = 90,
        operator: str = "SYSTEM",
        role: str = "ADMIN",
    ) -> int:
        """Purges closed or resolved alarms older than retention_days, strictly preserving locked evidence."""
        self._validate_permission(role, "PURGE")
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        with db_manager.get_session() as session:
            candidates = (
                session.query(Alarm)
                .filter(
                    Alarm.status.in_([AlarmStatus.RESOLVED.value, AlarmStatus.CLOSED.value]),
                    Alarm.last_detected_at < cutoff,
                    Alarm.is_deleted == False,
                )
                .all()
            )
            purged_count = 0
            for a in candidates:
                ev_refs = json.loads(a.evidence_refs) if a.evidence_refs else {}
                if ev_refs.get("is_locked") or ev_refs.get("evidence_package_id"):
                    continue
                a.is_deleted = True
                purged_count += 1
            return purged_count

    # -------------------------------------------------------------------------
    # Queries & Dashboard Metrics
    # -------------------------------------------------------------------------
    def get_alarms(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        camera_id: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Queries alarms with comprehensive filtering, search, and pagination."""
        with db_manager.get_session() as session:
            query = session.query(Alarm).filter(Alarm.is_deleted == False)

            if status:
                query = query.filter(Alarm.status == status)
            if severity:
                query = query.filter(Alarm.severity == severity)
            if category:
                query = query.filter(Alarm.category == category)
            if camera_id:
                query = query.filter(Alarm.camera_id == camera_id)
            if start_time:
                query = query.filter(Alarm.last_detected_at >= start_time)
            if end_time:
                query = query.filter(Alarm.last_detected_at <= end_time)
            if search:
                term = f"%{search}%"
                query = query.filter(or_(Alarm.title.ilike(term), Alarm.description.ilike(term)))

            total_count = query.count()
            alarms = query.order_by(desc(Alarm.last_detected_at)).offset(offset).limit(limit).all()

            results = []
            for a in alarms:
                results.append({
                    "id": a.id,
                    "title": a.title,
                    "description": a.description,
                    "category": a.category,
                    "source_subsystem": a.source_subsystem,
                    "severity": a.severity,
                    "priority": a.priority,
                    "status": a.status,
                    "camera_id": a.camera_id,
                    "first_detected_at": a.first_detected_at.isoformat() if a.first_detected_at else None,
                    "last_detected_at": a.last_detected_at.isoformat() if a.last_detected_at else None,
                    "occurrence_count": a.occurrence_count,
                    "assigned_operator": a.assigned_operator,
                    "escalation_level": a.escalation_level,
                    "evidence_refs": json.loads(a.evidence_refs) if a.evidence_refs else {},
                    "related_alarm_id": a.related_alarm_id,
                })

            return results, total_count

    def get_active_alarms(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Queries active, non-deleted alarms (convenience wrapper)."""
        alarms, _ = self.get_alarms(limit=limit)
        return alarms

    def get_alarm_by_id(self, alarm_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves single complete alarm record with full metadata."""
        with db_manager.get_session() as session:
            alarm = session.query(Alarm).filter(Alarm.id == alarm_id, Alarm.is_deleted == False).first()
            if not alarm:
                return None
            return {
                "id": alarm.id,
                "title": alarm.title,
                "description": alarm.description,
                "category": alarm.category,
                "source_subsystem": alarm.source_subsystem,
                "severity": alarm.severity,
                "priority": alarm.priority,
                "status": alarm.status,
                "camera_id": alarm.camera_id,
                "site_id": alarm.site_id,
                "zone_id": alarm.zone_id,
                "first_detected_at": alarm.first_detected_at.isoformat() if alarm.first_detected_at else None,
                "last_detected_at": alarm.last_detected_at.isoformat() if alarm.last_detected_at else None,
                "occurrence_count": alarm.occurrence_count,
                "assigned_operator": alarm.assigned_operator,
                "acknowledged_at": alarm.acknowledged_at.isoformat() if alarm.acknowledged_at else None,
                "acknowledged_by": alarm.acknowledged_by,
                "resolved_at": alarm.resolved_at.isoformat() if alarm.resolved_at else None,
                "resolved_by": alarm.resolved_by,
                "closed_at": alarm.closed_at.isoformat() if alarm.closed_at else None,
                "closed_by": alarm.closed_by,
                "escalation_level": alarm.escalation_level,
                "evidence_refs": json.loads(alarm.evidence_refs) if alarm.evidence_refs else {},
                "alarm_metadata": json.loads(alarm.alarm_metadata) if alarm.alarm_metadata else {},
                "related_alarm_id": alarm.related_alarm_id,
            }

    def get_alarm_history(self, alarm_id: str) -> List[Dict[str, Any]]:
        """Retrieves chronological append-only audit trail for an alarm."""
        with db_manager.get_session() as session:
            entries = (
                session.query(AlarmHistory)
                .filter(AlarmHistory.alarm_id == alarm_id, AlarmHistory.is_deleted == False)
                .order_by(AlarmHistory.entry_index.asc(), AlarmHistory.timestamp.asc())
                .all()
            )
            return [
                {
                    "id": e.id,
                    "alarm_id": e.alarm_id,
                    "entry_index": e.entry_index,
                    "previous_status": e.previous_status,
                    "new_status": e.new_status,
                    "operator": e.operator,
                    "timestamp": e.timestamp.isoformat() if hasattr(e.timestamp, "isoformat") else str(e.timestamp),
                    "action": e.action,
                    "reason": e.reason,
                    "comments": e.comments,
                    "prev_hash": e.prev_hash,
                    "entry_hash": e.entry_hash,
                }
                for e in entries
            ]

    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """Calculates executive dashboard metrics."""
        with db_manager.get_session() as session:
            now = datetime.now(timezone.utc)
            today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

            # Query active alarms in a single query
            active_rows = session.query(
                Alarm.status,
                Alarm.severity,
                Alarm.escalation_level
            ).filter(
                Alarm.status.in_([AlarmStatus.NEW.value, AlarmStatus.ACKNOWLEDGED.value, AlarmStatus.IN_PROGRESS.value, AlarmStatus.REOPENED.value]),
                Alarm.is_deleted == False,
            ).all()

            total_active = len(active_rows)
            critical_count = sum(1 for r in active_rows if r[1] == AlarmSeverity.CRITICAL.value)
            unack_count = sum(1 for r in active_rows if r[0] == AlarmStatus.NEW.value)
            in_progress_count = sum(1 for r in active_rows if r[0] == AlarmStatus.IN_PROGRESS.value)
            escalated_count = sum(1 for r in active_rows if (r[2] or 0) > 0)

            resolved_today = session.query(func.count(Alarm.id)).filter(
                Alarm.status.in_([AlarmStatus.RESOLVED.value, AlarmStatus.CLOSED.value]),
                Alarm.resolved_at >= today_start,
                Alarm.is_deleted == False,
            ).scalar() or 0

            # Severity distribution from queried active alarms
            sev_counts = {sev.value: 0 for sev in AlarmSeverity}
            for r in active_rows:
                if r[1] in sev_counts:
                    sev_counts[r[1]] += 1

            return {
                "total_active": total_active,
                "critical_count": critical_count,
                "unacknowledged_count": unack_count,
                "in_progress_count": in_progress_count,
                "escalated_count": escalated_count,
                "resolved_today": resolved_today,
                "severity_distribution": sev_counts,
            }

    def get_alarm_statistics(self) -> Dict[str, Any]:
        """Calculates SLA statistics including MTTA and MTTR."""
        with db_manager.get_session() as session:
            # Calculate MTTA (Mean Time to Acknowledge in minutes)
            acked = session.query(Alarm.first_detected_at, Alarm.acknowledged_at).filter(
                Alarm.acknowledged_at.isnot(None),
                Alarm.is_deleted == False,
            ).limit(200).all()

            mtta_minutes = 0.0
            if acked:
                diffs = [(a[1] - a[0]).total_seconds() / 60.0 for a in acked if a[1] and a[0]]
                if diffs:
                    mtta_minutes = round(sum(diffs) / len(diffs), 1)

            # Calculate MTTR (Mean Time to Resolve in minutes)
            resolved = session.query(Alarm.first_detected_at, Alarm.resolved_at).filter(
                Alarm.resolved_at.isnot(None),
                Alarm.is_deleted == False,
            ).limit(200).all()

            mttr_minutes = 0.0
            if resolved:
                diffs = [(r[1] - r[0]).total_seconds() / 60.0 for r in resolved if r[1] and r[0]]
                if diffs:
                    mttr_minutes = round(sum(diffs) / len(diffs), 1)

            # Top cameras by alarm count
            top_cams = (
                session.query(Alarm.camera_id, func.count(Alarm.id))
                .filter(Alarm.camera_id.isnot(None), Alarm.is_deleted == False)
                .group_by(Alarm.camera_id)
                .order_by(desc(func.count(Alarm.id)))
                .limit(5)
                .all()
            )

            return {
                "mtta_minutes": mtta_minutes,
                "mttr_minutes": mttr_minutes,
                "top_cameras": [{"camera_id": c[0], "alarm_count": c[1]} for c in top_cams],
            }


# Global singleton instance
alarm_service = AlarmEngineService()
