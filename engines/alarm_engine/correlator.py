"""
Alarm Correlation Engine.
Phase 12 (F-046, Change ID: CHG-20261125-009).

Correlates multi-event spatial and temporal incidents (network outage clusters,
multi-zone perimeter breaches, stream disconnect-recovery pairs).
"""

import time
import threading
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta

from engines.alarm_engine.normalizer import NormalizedAlarmEvent
from core.logging.logger import get_logger

logger = get_logger("alarm_correlator")


class AlarmCorrelator:
    """Discovers relationships between active alarms and newly arriving events."""

    def __init__(self, correlation_window_sec: float = 60.0) -> None:
        self.correlation_window_sec = correlation_window_sec
        # Maps root cause keys to parent alarm IDs
        # E.g. "NETWORK:GATEWAY:192.168.1.1" -> parent_alarm_id
        self._active_root_causes: Dict[str, str] = {}
        # Maps camera_id to active offline alarm_id
        self._camera_offline_alarms: Dict[str, str] = {}
        self._lock = threading.RLock()

    def register_parent_incident(self, root_key: str, alarm_id: str) -> None:
        """Registers a major infrastructure or perimeter incident as a correlation parent."""
        with self._lock:
            self._active_root_causes[root_key] = alarm_id

    def register_camera_offline(self, camera_id: str, alarm_id: str) -> None:
        """Tracks active camera disconnection alarms for recovery pairing."""
        with self._lock:
            self._camera_offline_alarms[str(camera_id)] = alarm_id

    def find_correlation(self, event: NormalizedAlarmEvent) -> Optional[str]:
        """
        Determines whether a new event should be correlated to an active parent alarm.
        Returns parent alarm_id if correlation exists, otherwise None.
        """
        with self._lock:
            # 1. Network gateway / switch outage correlation
            if event.source_subsystem.upper() == "STREAM" and "DISCONNECTED" in event.event_type.upper():
                for root_key, parent_id in self._active_root_causes.items():
                    if root_key.startswith("NETWORK:GATEWAY") or root_key.startswith("NETWORK:SWITCH"):
                        logger.info("Correlating camera %s disconnection to network incident %s", event.camera_id, parent_id)
                        return parent_id

            # 2. Camera stream recovery correlation
            if event.source_subsystem.upper() == "STREAM" and "RECOVERED" in event.event_type.upper():
                cam = str(event.camera_id) if event.camera_id else ""
                if cam in self._camera_offline_alarms:
                    parent_id = self._camera_offline_alarms[cam]
                    logger.info("Correlating stream recovery for camera %s to offline alarm %s", cam, parent_id)
                    return parent_id

            # 3. Multi-zone spatial correlation on the same camera
            if event.source_subsystem.upper() == "ANALYTICS" and event.camera_id:
                cam_key = f"PERIMETER:{event.camera_id}"
                if cam_key in self._active_root_causes:
                    return self._active_root_causes[cam_key]

        return None

    def clear_root_cause(self, root_key: str) -> None:
        with self._lock:
            self._active_root_causes.pop(root_key, None)

    def clear_camera_offline(self, camera_id: str) -> None:
        with self._lock:
            self._camera_offline_alarms.pop(str(camera_id), None)
