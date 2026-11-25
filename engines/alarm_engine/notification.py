"""
Alarm Notification Dispatcher.
Phase 12 (F-046, Change ID: CHG-20261125-009).

Dispatches multi-channel in-app, desktop, and configurable audio alerts
with cooldown suppression to prevent operator notification fatigue.
"""

import time
import threading
from typing import Dict, List, Optional
from datetime import datetime, timezone

from database.database_manager import db_manager
from database.models.alarms import AlarmNotification
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("alarm_notification")


class AlarmNotificationDispatcher:
    """Dispatches notifications across in-app, audio chime, and desktop channels."""

    def __init__(self, suppression_cooldown_sec: float = 30.0) -> None:
        self.suppression_cooldown_sec = suppression_cooldown_sec
        # Tracks last notification timestamp per alarm_id: channel
        self._last_notified: Dict[str, float] = {}
        self._lock = threading.RLock()

    def should_notify(self, alarm_id: str, channel: str) -> bool:
        """Evaluates whether notification is permitted or currently suppressed by cooldown."""
        key = f"{alarm_id}:{channel}"
        now = time.time()
        with self._lock:
            last = self._last_notified.get(key, 0.0)
            if (now - last) >= self.suppression_cooldown_sec:
                self._last_notified[key] = now
                return True
            return False

    def dispatch(
        self,
        alarm_id: str,
        title: str,
        severity: str,
        category: str,
        camera_id: Optional[str] = None,
        channels: Optional[List[str]] = None,
        recipient: str = "ALL_OPERATORS",
    ) -> List[str]:
        """
        Dispatches notification across requested channels.
        Persists delivery records and publishes to platform EventBus.
        """
        active_channels = channels or ["DESKTOP", "IN_APP", "AUDIO"]
        dispatched_channels: List[str] = []

        payload = {
            "alarm_id": alarm_id,
            "title": title,
            "severity": severity,
            "category": category,
            "camera_id": camera_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # 1. In-App Notification (Always publish to EventBus for UI widgets)
        if "IN_APP" in active_channels:
            try:
                bus.publish("alarm.notification", payload, source="alarm_engine")
                dispatched_channels.append("IN_APP")
            except Exception as e:
                logger.error("Failed to publish in-app notification: %s", e)

        # 2. Audio Chime (Check cooldown suppression)
        if "AUDIO" in active_channels and severity in ("CRITICAL", "HIGH", "MEDIUM"):
            if self.should_notify(alarm_id, "AUDIO"):
                try:
                    chime_type = "URGENT" if severity == "CRITICAL" else ("WARNING" if severity == "HIGH" else "NOTICE")
                    bus.publish("alarm.audio_chime", {"alarm_id": alarm_id, "chime_type": chime_type, "severity": severity}, source="alarm_engine")
                    dispatched_channels.append("AUDIO")
                except Exception as e:
                    logger.error("Failed to publish audio chime notification: %s", e)

        # 3. Desktop Notification (Check cooldown suppression)
        if "DESKTOP" in active_channels:
            if self.should_notify(alarm_id, "DESKTOP"):
                try:
                    bus.publish("alarm.desktop_popup", payload, source="alarm_engine")
                    dispatched_channels.append("DESKTOP")
                except Exception as e:
                    logger.error("Failed to publish desktop popup notification: %s", e)

        # Persist notification log (guaranteed non-blocking)
        try:
            with db_manager.get_session() as session:
                for ch in dispatched_channels:
                    rec = AlarmNotification(
                        alarm_id=alarm_id,
                        channel=ch,
                        recipient=recipient,
                        delivery_status="DELIVERED",
                        retry_count=0,
                        timestamp=datetime.now(timezone.utc),
                    )
                    session.add(rec)
        except Exception as e:
            logger.debug("Failed saving notification delivery log: %s", e)

        return dispatched_channels

    def clear_cooldown(self, alarm_id: Optional[str] = None) -> None:
        with self._lock:
            if alarm_id:
                keys_to_del = [k for k in self._last_notified if k.startswith(f"{alarm_id}:")]
                for k in keys_to_del:
                    del self._last_notified[k]
            else:
                self._last_notified.clear()
