"""
Thread-safe Event Bus for CCTV AI Intelligence Platform.
Enables loose coupling and reactive communication between Video Streams,
AI Inference, Alarm System, UI Components, and Storage Services.
"""

import threading
from typing import Callable, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from core.logging.logger import get_logger

logger = get_logger("event_bus")


@dataclass
class Event:
    """Standard Event message across the platform."""
    topic: str
    data: Any
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "system"


class EventBus:
    """Thread-safe publish-subscribe event broker."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Event], None]]] = {}
        self._lock = threading.RLock()

    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        """Subscribes a callable handler to a topic (exact match or wildcard 'topic.*')."""
        with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            if handler not in self._subscribers[topic]:
                self._subscribers[topic].append(handler)
        logger.debug("Subscribed %s to event topic '%s'", getattr(handler, "__name__", str(handler)), topic)

    def unsubscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        """Unsubscribes a handler from a topic."""
        with self._lock:
            if topic in self._subscribers and handler in self._subscribers[topic]:
                self._subscribers[topic].remove(handler)
                if not self._subscribers[topic]:
                    del self._subscribers[topic]

    def publish(self, topic: str, data: Any, source: str = "system") -> None:
        """Dispatches an event synchronously to all registered topic subscribers."""
        event = Event(topic=topic, data=data, source=source)
        handlers_to_call: List[Callable[[Event], None]] = []

        with self._lock:
            # Exact topic match
            if topic in self._subscribers:
                handlers_to_call.extend(self._subscribers[topic])
            # Wildcard root match (e.g., 'alarm.*' matches 'alarm.critical')
            if ".*" in topic or "*" in self._subscribers:
                if "*" in self._subscribers:
                    handlers_to_call.extend(self._subscribers["*"])
            # Prefix matches
            for registered_topic, handlers in self._subscribers.items():
                if registered_topic.endswith(".*"):
                    prefix = registered_topic[:-2]
                    if topic.startswith(prefix + ".") and registered_topic != topic:
                        handlers_to_call.extend(handlers)

        for handler in handlers_to_call:
            try:
                handler(event)
            except Exception as e:
                try:
                    handler_name = getattr(handler, "__name__", "handler")
                    logger.error("Error executing event handler %s for topic '%s': %s", handler_name, topic, e)
                except Exception:
                    pass


# Global event bus singleton
bus = EventBus()
