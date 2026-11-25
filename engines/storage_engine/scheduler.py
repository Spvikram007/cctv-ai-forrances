"""
Storage Scheduler for Background Health Checks, Retention Pruning, and Archival Maintenance.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

import time
import threading
from typing import Optional, Callable
from core.logging.logger import get_logger

logger = get_logger("storage_scheduler")


class StorageScheduler(threading.Thread):
    """
    Background worker thread executing periodic storage health monitoring,
    disk space auditing, retention pruning, and capacity forecasting outside the UI thread.
    """

    def __init__(
        self,
        health_check_interval_sec: float = 60.0,
        retention_interval_sec: float = 3600.0,
        health_callback: Optional[Callable[[], None]] = None,
        retention_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(name="CCTV-StorageScheduler", daemon=True)
        self.health_check_interval_sec = health_check_interval_sec
        self.retention_interval_sec = retention_interval_sec
        self.health_callback = health_callback
        self.retention_callback = retention_callback

        self._stop_event = threading.Event()
        self._last_health_check = 0.0
        self._last_retention_check = 0.0

    def stop(self) -> None:
        """Signals background thread to terminate."""
        self._stop_event.set()
        logger.info("Storage scheduler stop signaled.")

    def run(self) -> None:
        logger.info("Storage scheduler background thread started.")
        while not self._stop_event.is_set():
            now = time.time()

            # 1. Periodic Health Check
            if (now - self._last_health_check) >= self.health_check_interval_sec:
                self._last_health_check = now
                if self.health_callback:
                    try:
                        self.health_callback()
                    except Exception as e:
                        logger.error("Error executing storage health callback: %s", e)

            # 2. Periodic Retention Pruning
            if (now - self._last_retention_check) >= self.retention_interval_sec:
                self._last_retention_check = now
                if self.retention_callback:
                    try:
                        self.retention_callback()
                    except Exception as e:
                        logger.error("Error executing storage retention callback: %s", e)

            # Sleep in short increments for responsive shutdown
            self._stop_event.wait(timeout=1.0)

        logger.info("Storage scheduler background thread stopped.")
