"""
AI Event Engine Package.
Processes detections, applies deduplication, triggers recording,
and generates real-time security events.
"""

from engines.event_engine.event_processor import (
    AIEventProcessor,
    AIEventRecord,
    EventDeduplicator,
    event_processor,
)

__all__ = [
    "AIEventProcessor",
    "AIEventRecord",
    "EventDeduplicator",
    "event_processor",
]
