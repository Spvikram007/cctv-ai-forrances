"""
Alarm Deduplication Engine.
Phase 12 (F-046, Change ID: CHG-20261125-009).

Detects burst repetitions and merges duplicate events into existing active alarms.
"""

import time
import threading
from typing import Dict, Tuple, Optional
from dataclasses import dataclass

from core.logging.logger import get_logger

logger = get_logger("alarm_deduplicator")


@dataclass
class DedupEntry:
    alarm_id: str
    last_timestamp: float
    occurrence_count: int
    status: str


class AlarmDeduplicator:
    """Thread-safe in-memory cache tracking active alarm signatures."""

    def __init__(self, default_window_seconds: int = 60) -> None:
        self.default_window_seconds = default_window_seconds
        self._entries: Dict[str, DedupEntry] = {}
        self._lock = threading.RLock()

    def check_and_update(
        self,
        dedup_key: str,
        window_seconds: Optional[int] = None,
    ) -> Tuple[bool, Optional[str], int]:
        """
        Checks whether dedup_key matches an existing active alarm within the window.
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
                # If existing alarm is still active (not CLOSED or RESOLVED) and within window
                if entry.status not in ("RESOLVED", "CLOSED") and (now - entry.last_timestamp) <= win:
                    entry.last_timestamp = now
                    entry.occurrence_count += 1
                    logger.debug("Deduplicated event for key '%s': count=%d", dedup_key, entry.occurrence_count)
                    return True, entry.alarm_id, entry.occurrence_count
                else:
                    # Expired or closed; evict
                    del self._entries[dedup_key]

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
        with self._lock:
            keys_to_remove = []
            for k, entry in self._entries.items():
                if entry.alarm_id == alarm_id:
                    entry.status = new_status
                    if new_status in ("RESOLVED", "CLOSED"):
                        keys_to_remove.append(k)
            for k in keys_to_remove:
                del self._entries[k]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
