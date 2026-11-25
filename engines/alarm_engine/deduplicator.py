"""
Alarm Deduplication Engine.
Phase 12 & 12.1 (F-046, Change ID: CHG-20261125-010).

Detects burst repetitions and merges duplicate events into existing active alarms.
Supports in-memory caching, atomic DB updates, and persistent startup recovery.
"""

import time
import threading
from typing import Dict, Tuple, Optional, Any
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

from core.logging.logger import get_logger

logger = get_logger("alarm_deduplicator")

ACTIVE_STATUSES = ("NEW", "ACKNOWLEDGED", "IN_PROGRESS", "REOPENED")


@dataclass
class DedupEntry:
    alarm_id: str
    last_timestamp: float
    occurrence_count: int
    status: str


class AlarmDeduplicator:
    """
    Thread-safe hybrid cache and DB-backed deduplicator tracking active alarm signatures.
    Protects against duplicate creation across application restarts and concurrent workers.
    """

    def __init__(self, default_window_seconds: int = 60) -> None:
        self.default_window_seconds = default_window_seconds
        self._entries: Dict[str, DedupEntry] = {}
        self._lock = threading.RLock()

    def recover_from_database(self, session: Any, lookback_seconds: int = 3600) -> int:
        """
        Recovers active deduplication signatures from database on application restart.
        Ensures alarms created before restart are not duplicated after restart.
        """
        from database.models.alarms import Alarm
        threshold = datetime.now(timezone.utc) - timedelta(seconds=lookback_seconds)
        with self._lock:
            alarms = (
                session.query(Alarm)
                .filter(
                    Alarm.status.in_(ACTIVE_STATUSES),
                    Alarm.last_detected_at >= threshold,
                    Alarm.is_deleted == False,
                )
                .all()
            )
            recovered_count = 0
            for a in alarms:
                if a.dedup_key:
                    ts = a.last_detected_at.timestamp() if hasattr(a.last_detected_at, "timestamp") else time.time()
                    self._entries[a.dedup_key] = DedupEntry(
                        alarm_id=str(a.id),
                        last_timestamp=ts,
                        occurrence_count=a.occurrence_count,
                        status=a.status,
                    )
                    recovered_count += 1
            logger.info("Deduplicator recovered %d active alarm signatures from database", recovered_count)
            return recovered_count

    def check_and_update(
        self,
        dedup_key: str,
        window_seconds: Optional[int] = None,
        session: Optional[Any] = None,
    ) -> Tuple[bool, Optional[str], int]:
        """
        Checks whether dedup_key matches an existing active alarm within the window.
        If not in memory and a DB session is provided, queries database as persistent fallback.
        Returns:
            (is_duplicate: bool, existing_alarm_id: Optional[str], occurrence_count: int)
        """
        if not dedup_key:
            return False, None, 1

        win = window_seconds if window_seconds is not None else self.default_window_seconds
        now = time.time()

        with self._lock:
            entry = self._entries.get(dedup_key)
            if entry is not None:
                # If existing alarm is still active and within window
                if entry.status in ACTIVE_STATUSES and (now - entry.last_timestamp) <= win:
                    entry.last_timestamp = now
                    entry.occurrence_count += 1
                    logger.debug("Deduplicated event (memory) for key '%s': count=%d", dedup_key, entry.occurrence_count)
                    return True, entry.alarm_id, entry.occurrence_count
                else:
                    # Expired or closed; evict
                    del self._entries[dedup_key]

            # If not in memory and DB session provided, check DB for persistent fallback
            if session is not None:
                from database.models.alarms import Alarm
                threshold = datetime.now(timezone.utc) - timedelta(seconds=win)
                existing = (
                    session.query(Alarm)
                    .filter(
                        Alarm.dedup_key == dedup_key,
                        Alarm.status.in_(ACTIVE_STATUSES),
                        Alarm.last_detected_at >= threshold,
                        Alarm.is_deleted == False,
                    )
                    .order_by(Alarm.last_detected_at.desc())
                    .first()
                )
                if existing:
                    new_count = existing.occurrence_count + 1
                    self._entries[dedup_key] = DedupEntry(
                        alarm_id=str(existing.id),
                        last_timestamp=now,
                        occurrence_count=new_count,
                        status=existing.status,
                    )
                    logger.debug("Deduplicated event (database fallback) for key '%s': count=%d", dedup_key, new_count)
                    return True, str(existing.id), new_count

        return False, None, 1

    def register_alarm(self, dedup_key: str, alarm_id: str, status: str = "NEW") -> None:
        """Registers a newly created active alarm in the deduplication cache."""
        if not dedup_key:
            return
        with self._lock:
            self._entries[dedup_key] = DedupEntry(
                alarm_id=alarm_id,
                last_timestamp=time.time(),
                occurrence_count=1,
                status=status,
            )

    def update_status(self, alarm_id: str, new_status: str) -> None:
        """Updates or evicts cached entry when alarm transitions to resolved/closed."""
        target_id = str(alarm_id)
        with self._lock:
            keys_to_remove = []
            for k, entry in self._entries.items():
                if entry.alarm_id == target_id:
                    entry.status = new_status
                    if new_status not in ACTIVE_STATUSES:
                        keys_to_remove.append(k)
            for k in keys_to_remove:
                del self._entries[k]

    def evict(self, dedup_key: str) -> None:
        """Explicitly evicts a key from the in-memory cache."""
        with self._lock:
            self._entries.pop(dedup_key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
