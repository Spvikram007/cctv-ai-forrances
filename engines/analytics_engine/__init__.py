"""
Video Analytics and Intelligent Surveillance Rules Engine Package.
"""

from engines.analytics_engine.geometry import (
    point_in_polygon,
    line_segments_intersect,
    get_crossing_direction,
    box_bottom_center,
    box_center,
)
from engines.analytics_engine.rule_evaluator import (
    ZoneConfig,
    TripwireConfig,
    AnalyticsRuleConfig,
    AnalyticsEventData,
    IntrusionDetector,
    TripwireDetector,
    LoiteringDetector,
    CountingManager,
    HeatmapGenerator,
)
from engines.analytics_engine.analytics_pipeline import (
    CameraAnalyticsPipeline,
    AnalyticsManager,
    analytics_manager,
)

__all__ = [
    "point_in_polygon",
    "line_segments_intersect",
    "get_crossing_direction",
    "box_bottom_center",
    "box_center",
    "ZoneConfig",
    "TripwireConfig",
    "AnalyticsRuleConfig",
    "AnalyticsEventData",
    "IntrusionDetector",
    "TripwireDetector",
    "LoiteringDetector",
    "CountingManager",
    "HeatmapGenerator",
    "CameraAnalyticsPipeline",
    "AnalyticsManager",
    "analytics_manager",
]
