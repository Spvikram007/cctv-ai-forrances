"""
Alarm Notification Dispatcher.
Phase 12 (F-046, Change ID: CHG-20261125-009).

Dispatches multi-channel in-app, desktop, and configurable audio alerts
with cooldown suppression to prevent operator notification fatigue.
"""

import time
import json
import threading
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timezone, timedelta

from database.database_manager import db_manager
from database.models.alarms import AlarmNotification
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("alarm_notification")


class AlarmNotificationDispatcher:
    """Dispatches notifications across in-app, audio chime, desktop, and webhook channels with durable retries."""

    def __init__(self, suppression_cooldown_sec: float = 30.0) -> None:
        self.suppression_cooldown_sec = suppression_cooldown_sec
        # Tracks last notification timestamp per alarm_id: channel
        self._last_notified: Dict[str, float] = {}
        self._lock = threading.RLock()
        self._channel_handlers: Dict[str, Callable[[Dict[str, Any]], bool]] = {}

    def register_channel_handler(self, channel: str, handler: Callable[[Dict[str, Any]], bool]) -> None:
        """Registers a custom transport delivery handler (e.g. webhook, SMS, email)."""
        with self._lock:
            self._channel_handlers[channel.upper()] = handler

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
        Persists delivery records and durable retry tracking for failures.
        """
        active_channels = channels or ["DESKTOP", "IN_APP", "AUDIO"]
        dispatched_channels: List[str] = []
        failed_channels: List[tuple] = []

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
                failed_channels.append(("IN_APP", str(e)))

        # 2. Audio Chime (Check cooldown suppression)
        if "AUDIO" in active_channels and severity in ("CRITICAL", "HIGH", "MEDIUM"):
            if self.should_notify(alarm_id, "AUDIO"):
                try:
                    chime_type = "URGENT" if severity == "CRITICAL" else ("WARNING" if severity == "HIGH" else "NOTICE")
                    bus.publish("alarm.audio_chime", {"alarm_id": alarm_id, "chime_type": chime_type, "severity": severity}, source="alarm_engine")
                    dispatched_channels.append("AUDIO")
                except Exception as e:
                    logger.error("Failed to publish audio chime notification: %s", e)
                    failed_channels.append(("AUDIO", str(e)))

        # 3. Desktop Notification (Check cooldown suppression)
        if "DESKTOP" in active_channels:
            if self.should_notify(alarm_id, "DESKTOP"):
                try:
                    bus.publish("alarm.desktop_popup", payload, source="alarm_engine")
                    dispatched_channels.append("DESKTOP")
                except Exception as e:
                    logger.error("Failed to publish desktop popup notification: %s", e)
                    failed_channels.append(("DESKTOP", str(e)))

        # 4. Custom/External Channels (e.g. WEBHOOK, EMAIL)
        for ch in active_channels:
            ch_upper = ch.upper()
            if ch_upper in ("IN_APP", "AUDIO", "DESKTOP"):
                continue

            if self.should_notify(alarm_id, ch_upper):
                handler = self._channel_handlers.get(ch_upper)
                if handler:
                    try:
                        ok = handler(payload)
                        if ok:
                            dispatched_channels.append(ch_upper)
                        else:
                            failed_channels.append((ch_upper, "Handler returned false"))
                    except Exception as e:
                        logger.error("Channel %s handler delivery error: %s", ch_upper, e)
                        failed_channels.append((ch_upper, str(e)))
                else:
                    # Default EventBus emission
                    try:
                        bus.publish(f"alarm.channel.{ch_upper.lower()}", payload, source="alarm_engine")
                        dispatched_channels.append(ch_upper)
                    except Exception as e:
                        failed_channels.append((ch_upper, str(e)))

        # Persist notification log with durable retry state (guaranteed non-blocking)
        now_dt = datetime.now(timezone.utc)
        payload_json = json.dumps(payload)
        try:
            with db_manager.get_session() as session:
                for ch in dispatched_channels:
                    rec = AlarmNotification(
                        alarm_id=alarm_id,
                        channel=ch,
                        recipient=recipient,
                        delivery_status="DELIVERED",
                        retry_count=0,
                        payload=payload_json,
                        timestamp=now_dt,
                    )
                    session.add(rec)

                for ch, err in failed_channels:
                    rec = AlarmNotification(
                        alarm_id=alarm_id,
                        channel=ch,
                        recipient=recipient,
                        delivery_status="FAILED",
                        retry_count=1,
                        error_message=err,
                        payload=payload_json,
                        next_retry_at=now_dt + timedelta(seconds=60),
                        timestamp=now_dt,
                    )
                    session.add(rec)
                    bus.publish("alarm.notification_failed", {"alarm_id": alarm_id, "channel": ch, "error": err}, source="alarm_engine")
        except Exception as e:
            logger.debug("Failed saving notification delivery log: %s", e)

        return dispatched_channels

    def retry_failed_notifications(self, max_retries: int = 3, session: Optional[Any] = None) -> Dict[str, Any]:
        """
        Durable retry loop: scans database for failed notifications and attempts re-delivery.
        Marks records DELIVERED upon success, or PERMANENTLY_FAILED after max_retries.
        """
        now = datetime.now(timezone.utc)
        results = {"retried": 0, "succeeded": 0, "failed": 0, "permanently_failed": 0}

        def _do_retries(sess: Any) -> None:
            failed_records = (
                sess.query(AlarmNotification)
                .filter(
                    AlarmNotification.delivery_status == "FAILED",
                    AlarmNotification.retry_count < max_retries,
                )
                .all()
            )
            results["retried"] = len(failed_records)

            for rec in failed_records:
                payload = json.loads(rec.payload) if rec.payload else {"alarm_id": rec.alarm_id}
                handler = self._channel_handlers.get(rec.channel.upper())
                success = False

                try:
                    if handler:
                        success = handler(payload)
                    else:
                        bus.publish(f"alarm.channel.{rec.channel.lower()}", payload, source="alarm_retry")
                        success = True
                except Exception as e:
                    rec.error_message = str(e)
                    success = False

                if success:
                    rec.delivery_status = "DELIVERED"
                    rec.error_message = None
                    results["succeeded"] += 1
                else:
                    rec.retry_count += 1
                    rec.next_retry_at = now + timedelta(seconds=60 * (2 ** rec.retry_count))
                    results["failed"] += 1
                    if rec.retry_count >= max_retries:
                        rec.delivery_status = "PERMANENTLY_FAILED"
                        results["permanently_failed"] += 1
                        logger.warning(
                            "Notification %s for alarm %s permanently failed after %d retries",
                            rec.id, rec.alarm_id, rec.retry_count
                        )

        if session is not None:
            _do_retries(session)
        else:
            with db_manager.get_session() as sess:
                _do_retries(sess)

        return results

    def get_notification_health(self) -> Dict[str, Any]:
        """Queries delivery statistics across all persisted notifications."""
        with db_manager.get_session() as session:
            from sqlalchemy import func
            rows = (
                session.query(AlarmNotification.delivery_status, func.count(AlarmNotification.id))
                .group_by(AlarmNotification.delivery_status)
                .all()
            )
            counts = {status: count for status, count in rows}
            return {
                "delivered": counts.get("DELIVERED", 0),
                "failed": counts.get("FAILED", 0),
                "permanently_failed": counts.get("PERMANENTLY_FAILED", 0),
                "total": sum(counts.values()),
            }

    def clear_cooldown(self, alarm_id: Optional[str] = None) -> None:
        with self._lock:
            if alarm_id:
                keys_to_del = [k for k in self._last_notified if k.startswith(f"{alarm_id}:")]
                for k in keys_to_del:
                    del self._last_notified[k]
            else:
                self._last_notified.clear()
