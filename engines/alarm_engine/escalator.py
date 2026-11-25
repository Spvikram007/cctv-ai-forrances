"""
Alarm Escalation and SLA Manager.
Phase 12 (F-046, Change ID: CHG-20261125-009).

Monitors persistent SLA deadlines, escalates unacknowledged alarms,
notifies supervisory roles, and survives platform restarts cleanly.
"""

from typing import List, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy import and_

from database.database_manager import db_manager
from database.models.alarms import Alarm, AlarmHistory
from engines.alarm_engine.enums import AlarmStatus, AlarmAction
from core.logging.logger import get_logger

logger = get_logger("alarm_escalator")


class AlarmEscalationManager:
    """Evaluates and executes SLA escalation policies against persisted alarms."""

    @staticmethod
    def calculate_deadline(first_detected_at: datetime, timeout_seconds: int) -> datetime:
        """Computes the target UTC escalation deadline."""
        return first_detected_at + timedelta(seconds=timeout_seconds)

    @classmethod
    def check_and_escalate_pending_alarms(
        cls,
        current_time: Optional[datetime] = None,
        operator: str = "SYSTEM_SLA_WATCHDOG",
    ) -> List[str]:
        """
        Queries database for active alarms exceeding their escalation deadline.
        Advances escalation level, updates audit trail, and returns list of escalated alarm IDs.
        """
        now = current_time or datetime.now(timezone.utc)
        escalated_ids: List[str] = []

        try:
            with db_manager.get_session() as session:
                # Find all un-resolved/un-closed alarms with an expired deadline
                overdue_alarms = (
                    session.query(Alarm)
                    .filter(
                        and_(
                            Alarm.status.in_([AlarmStatus.NEW.value, AlarmStatus.IN_PROGRESS.value]),
                            Alarm.next_escalation_deadline.isnot(None),
                            Alarm.next_escalation_deadline <= now,
                            Alarm.is_deleted == False,
                        )
                    )
                    .all()
                )

                for alarm in overdue_alarms:
                    alarm.escalation_level += 1
                    alarm.escalated_at = now
                    # Set next tier deadline (e.g. +10 minutes for Tier 2/3) or clear if max reached
                    if alarm.escalation_level < 3:
                        alarm.next_escalation_deadline = now + timedelta(seconds=600)
                    else:
                        alarm.next_escalation_deadline = None

                    # Append to append-only audit trail
                    history_entry = AlarmHistory(
                        alarm_id=alarm.id,
                        previous_status=alarm.status,
                        new_status=alarm.status,
                        operator=operator,
                        timestamp=now,
                        action=AlarmAction.ESCALATED.value,
                        reason=f"SLA breached: Alarm unaddressed. Escalated to Tier {alarm.escalation_level}.",
                        comments=f"Automatic escalation triggered by SLA watchdog.",
                    )
                    session.add(history_entry)
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

        except Exception as e:
            logger.error("Error executing alarm SLA escalation watchdog: %s", e)

        return escalated_ids
