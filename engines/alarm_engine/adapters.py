"""
Subsystem Event Adapters for Alarm Management.
Phase 12 (F-046, Change ID: CHG-20261125-009).

Subscribes to platform EventBus topics across Analytics, AI, Biometrics, Streams,
Network, Storage, and Forensics, translating them into normalized alarms.
"""

from typing import Dict, Any, List
from core.events.event_bus import bus, Event
from engines.alarm_engine.alarm_service import alarm_service
from core.logging.logger import get_logger

logger = get_logger("alarm_adapters")


class AlarmEventBusAdapter:
    """Subscribes to cross-platform topics and routes them to the Alarm Service."""

    def __init__(self) -> None:
        self._subscribed = False
        self._handlers: Dict[str, Any] = {}

    def start(self) -> None:
        """Attaches handlers to all platform event topics."""
        if self._subscribed:
            return

        self._handlers = {
            "analytics.event": self._on_analytics_event,
            "ai.event": self._on_ai_event,
            "anpr.watchlist_alert": self._on_anpr_watchlist,
            "face.candidate_match": self._on_face_match,
            "stream.disconnected": self._on_stream_disconnected,
            "stream.recovered": self._on_stream_recovered,
            "stream.frozen": self._on_stream_frozen,
            "network.fault_detected": self._on_network_fault,
            "network.security_alert": self._on_network_security,
            "camera.auth_failure": self._on_camera_auth_failure,
            "recording.failed": self._on_recording_failed,
            "recording.interrupted": self._on_recording_interrupted,
            "storage.write_failure": self._on_storage_write_failure,
            "storage.volume_critical": self._on_storage_critical,
            "storage.volume_low": self._on_storage_low,
            "forensic.integrity_failure": self._on_forensic_failure,
        }

        for topic, handler in self._handlers.items():
            bus.subscribe(topic, handler)

        self._subscribed = True
        logger.info("AlarmEventBusAdapter subscribed to %d platform event topics", len(self._handlers))

    def stop(self) -> None:
        """Detaches handlers from platform event topics."""
        if not self._subscribed:
            return

        for topic, handler in self._handlers.items():
            bus.unsubscribe(topic, handler)

        self._handlers.clear()
        self._subscribed = False
        logger.info("AlarmEventBusAdapter detached from platform event topics")

    # --- Topic Handlers ---
    def _on_analytics_event(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        rule_type = data.get("rule_type") or "ANALYTICS_EVENT"
        alarm_service.enqueue_event("ANALYTICS", rule_type, data)

    def _on_ai_event(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        event_type = data.get("event_type") or "AI_DETECTION"
        alarm_service.enqueue_event("AI", event_type, data)

    def _on_anpr_watchlist(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        alarm_service.enqueue_event("ANPR", "WATCHLIST_ALERT", data)

    def _on_face_match(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        alarm_service.enqueue_event("FACE", "CANDIDATE_MATCH", data)

    def _on_stream_disconnected(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        alarm_service.enqueue_event("STREAM", "STREAM_DISCONNECTED", data)

    def _on_stream_recovered(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        alarm_service.enqueue_event("STREAM", "STREAM_RECOVERED", data)

    def _on_stream_frozen(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        alarm_service.enqueue_event("STREAM", "STREAM_FROZEN", data)

    def _on_network_fault(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        fault = data.get("fault_type") or "NETWORK_FAULT"
        alarm_service.enqueue_event("NETWORK", fault, data)

    def _on_network_security(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        alarm_service.enqueue_event("NETWORK", "SECURITY_ALERT", data)

    def _on_storage_critical(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        alarm_service.enqueue_event("STORAGE", "VOLUME_CRITICAL", data)

    def _on_storage_low(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        alarm_service.enqueue_event("STORAGE", "VOLUME_LOW", data)

    def _on_camera_auth_failure(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        alarm_service.enqueue_event("CAMERA", "AUTH_FAILURE", data)

    def _on_recording_failed(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        alarm_service.enqueue_event("RECORDING", "FAILED", data)

    def _on_recording_interrupted(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        alarm_service.enqueue_event("RECORDING", "INTERRUPTED", data)

    def _on_storage_write_failure(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        alarm_service.enqueue_event("STORAGE", "WRITE_FAILURE", data)

    def _on_forensic_failure(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {"payload": event.data}
        alarm_service.enqueue_event("FORENSICS", "INTEGRITY_FAILURE", data)


# Global adapter singleton
alarm_adapter = AlarmEventBusAdapter()
