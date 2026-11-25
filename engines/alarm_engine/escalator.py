"""
Alarm Escalation and SLA Manager.
Phase 12 & 12.1 (F-046, Change ID: CHG-20261125-010).

Monitors persistent SLA deadlines, escalates unacknowledged alarms,
notifies supervisory roles, ensures hash-chained audit trails,
and survives platform restarts cleanly.
"""

import hashlib
from typing import List, Optional, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy import and_

from database.database_manager import db_manager
from database.models.alarms import Alarm, AlarmHistory
from engines.alarm_engine.enums import AlarmStatus, AlarmAction
from core.logging.logger import get_logger

logger = get_logger("alarm_escalator")


def _format_timestamp(ts: Any) -> str:
    """Standardizes timestamps to UTC string format across aware and naive SQLite models."""
    if isinstance(ts, datetime):
        if ts.tzinfo is not None:
            ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
        return ts.strftime("%Y-%m-%d %H:%M:%S.%f")
    return str(ts)


class AlarmEscalationManager:
    """Evaluates and executes SLA escalation policies against persisted alarms."""

    @staticmethod
    def calculate_deadline(first_detected_at: datetime, timeout_seconds: int) -> datetime:
        """Computes the target UTC escalation deadline."""
        return first_detected_at + timedelta(seconds=timeout_seconds)

    @classmethod
    def recover_pending_escalations(
        cls,
        current_time: Optional[datetime] = None,
        session: Optional[Any] = None,
    ) -> List[str]:
        """
        On application startup, recovers and escalates any alarms whose SLA deadline
        expired while the service was stopped or restarting.
        """
        now = current_time or datetime.now(timezone.utc)
        return cls.check_and_escalate_pending_alarms(
            current_time=now,
            session=session,
            operator="SYSTEM_STARTUP_RECOVERY",
        )

    @classmethod
    def check_and_escalate_pending_alarms(
        cls,
        current_time: Optional[datetime] = None,
        operator: str = "SYSTEM_SLA_WATCHDOG",
        session: Optional[Any] = None,
    ) -> List[str]:
        """
        Queries database for active alarms exceeding their escalation deadline.
        Advances escalation level, updates hash-chained audit trail, and returns list of escalated alarm IDs.
        Suppresses duplicate escalations and bounds maximum tier at Tier 3.
        """
        now = current_time or datetime.now(timezone.utc)
        escalated_ids: List[str] = []

        def _do_escalation(sess: Any) -> None:
            # Find all un-resolved/un-closed alarms with an expired deadline
            overdue_alarms = (
                sess.query(Alarm)
                .filter(
                    and_(
                        Alarm.status.in_([AlarmStatus.NEW.value, AlarmStatus.IN_PROGRESS.value]),
                        Alarm.next_escalation_deadline.isnot(None),
                        Alarm.next_escalation_deadline <= now,
                        Alarm.escalation_level < 3,
                        Alarm.is_deleted == False,
                    )
                )
                .all()
            )

            for alarm in overdue_alarms:
                prev_level = alarm.escalation_level
                alarm.escalation_level += 1
                alarm.escalated_at = now
                # Set next tier deadline (e.g. +10 minutes for Tier 2/3) or clear if max reached
                if alarm.escalation_level < 3:
                    alarm.next_escalation_deadline = now + timedelta(seconds=600)
                else:
                    alarm.next_escalation_deadline = None

                # Calculate hash-chained audit trail entry
                last_entry = (
                    sess.query(AlarmHistory)
                    .filter(AlarmHistory.alarm_id == alarm.id)
                    .order_by(AlarmHistory.entry_index.desc())
                    .first()
                )
                if last_entry is None:
                    entry_index = 0
                    prev_hash = "0" * 64
                else:
                    entry_index = (last_entry.entry_index or 0) + 1
                    prev_hash = last_entry.entry_hash or ("0" * 64)

                reason_str = f"SLA breached: Alarm unaddressed. Escalated to Tier {alarm.escalation_level} (from Tier {prev_level})."
                comment_str = f"Automatic escalation triggered by {operator}."
                ts_str = _format_timestamp(now)
                canonical = (
                    f"{entry_index}|{alarm.id}|{prev_hash}|{alarm.status}|{alarm.status}|"
                    f"{operator}|{AlarmAction.ESCALATED.value}|{ts_str}|{reason_str}|{comment_str}"
                )
                entry_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

                history_entry = AlarmHistory(
                    alarm_id=alarm.id,
                    entry_index=entry_index,
                    previous_status=alarm.status,
                    new_status=alarm.status,
                    operator=operator,
                    timestamp=now,
                    action=AlarmAction.ESCALATED.value,
                    reason=reason_str,
                    comments=comment_str,
                    prev_hash=prev_hash,
                    entry_hash=entry_hash,
                )
                sess.add(history_entry)
                escalated_ids.append(alarm.id)
                try:
                    logger.warning(
                        "Alarm %s [%s] escalated to Tier %d (SLA breached)",
                        alarm.id,
                        alarm.title,
                        alarm.escalation_level,
                    )
                except Exception:
                    pass

        try:
            if session is not None:
                _do_escalation(session)
            else:
                with db_manager.get_session() as sess:
                    _do_escalation(sess)
        except Exception as e:
            logger.error("Error executing alarm SLA escalation watchdog: %s", e)

        return escalated_ids
