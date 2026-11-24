"""
AI Intelligence Workspace Module Package.
Surveillance AI dashboard, live telemetry, and detection analytics.
"""

from modules.ai_intelligence.ai_dashboard_widget import (
    AIDashboardWidget,
    MetricCard,
)
from modules.ai_intelligence.analytics_rules_widget import (
    AnalyticsRulesWidget,
    InteractiveAnalyticsCanvas,
)

__all__ = [
    "AIDashboardWidget",
    "MetricCard",
    "AnalyticsRulesWidget",
    "InteractiveAnalyticsCanvas",
]
