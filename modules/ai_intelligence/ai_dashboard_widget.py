"""
AI Intelligence Dashboard Widget.
Provides real-time AI detection statistics, per-channel inference FPS,
GPU/CPU device status, latency gauges, model status, and recent AI events.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QGridLayout, QProgressBar, QTabWidget
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor

from modules.ai_intelligence.analytics_rules_widget import AnalyticsRulesWidget
from core.logging.logger import get_logger

logger = get_logger("ai_dashboard")


class MetricCard(QFrame):
    """Compact metric display card."""

    def __init__(self, title: str, value: str = "—", parent=None):
        super().__init__(parent)
        self.setProperty("class", "card")
        self.setStyleSheet("""
            QFrame { background-color: #161b22; border: 1px solid #30363d;
                     border-radius: 8px; padding: 12px; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")

        self._value_label = QLabel(value)
        self._value_label.setStyleSheet("color: #58a6ff; font-size: 22px; font-weight: 700;")

        layout.addWidget(self._title_label)
        layout.addWidget(self._value_label)

    def set_value(self, value: str, color: str = "#58a6ff"):
        self._value_label.setText(value)
        self._value_label.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: 700;")


class AIDashboardWidget(QWidget):
    """AI Intelligence workspace showing live inference metrics and events."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._start_refresh_timer()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        self.main_tabs = QTabWidget(self)
        self.main_tabs.setStyleSheet("""
            QTabBar::tab { background: #161b22; color: #8b949e; padding: 8px 18px; border: 1px solid #30363d; font-weight: 600; }
            QTabBar::tab:selected { background: #21262d; color: #58a6ff; }
        """)

        # Tab 0: Inference & Hardware Telemetry
        telemetry_widget = QWidget()
        main_layout = QVBoxLayout(telemetry_widget)
        main_layout.setContentsMargins(0, 8, 0, 0)
        main_layout.setSpacing(12)

        # Header
        header = QLabel("AI INTELLIGENCE DASHBOARD")
        header.setStyleSheet("font-size: 18px; font-weight: 700; color: #58a6ff; margin-bottom: 8px;")
        main_layout.addWidget(header)

        # Top metric cards row
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        self.card_device = MetricCard("INFERENCE DEVICE")
        self.card_active_channels = MetricCard("ACTIVE AI CHANNELS", "0")
        self.card_total_detections = MetricCard("TOTAL DETECTIONS", "0")
        self.card_avg_latency = MetricCard("AVG LATENCY", "0 ms")
        self.card_inference_fps = MetricCard("AGGREGATE FPS", "0.0")
        self.card_events = MetricCard("AI EVENTS GENERATED", "0")

        cards_layout.addWidget(self.card_device)
        cards_layout.addWidget(self.card_active_channels)
        cards_layout.addWidget(self.card_total_detections)
        cards_layout.addWidget(self.card_avg_latency)
        cards_layout.addWidget(self.card_inference_fps)
        cards_layout.addWidget(self.card_events)

        main_layout.addLayout(cards_layout)

        # Middle row: Per-channel inference table + Detection class breakdown
        mid_layout = QHBoxLayout()
        mid_layout.setSpacing(12)

        # Per-channel inference metrics table
        channel_group = QGroupBox("PER-CHANNEL INFERENCE STATUS")
        channel_group.setStyleSheet("""
            QGroupBox { background-color: #0d1117; border: 1px solid #30363d;
                        border-radius: 6px; font-weight: 600; color: #c9d1d9;
                        padding-top: 20px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; }
        """)
        channel_layout = QVBoxLayout(channel_group)

        self.channel_table = QTableWidget()
        self.channel_table.setColumnCount(5)
        self.channel_table.setHorizontalHeaderLabels(["Channel", "Device", "FPS", "Latency", "Detections"])
        self.channel_table.horizontalHeader().setStretchLastSection(True)
        self.channel_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.channel_table.setStyleSheet("""
            QTableWidget { background-color: #0d1117; color: #c9d1d9;
                           border: none; gridline-color: #21262d; }
            QHeaderView::section { background-color: #161b22; color: #8b949e;
                                   font-weight: 600; border: 1px solid #21262d; padding: 4px; }
        """)
        self.channel_table.verticalHeader().setVisible(False)
        channel_layout.addWidget(self.channel_table)
        mid_layout.addWidget(channel_group, stretch=2)

        # Detection class breakdown
        class_group = QGroupBox("DETECTION CLASS BREAKDOWN")
        class_group.setStyleSheet("""
            QGroupBox { background-color: #0d1117; border: 1px solid #30363d;
                        border-radius: 6px; font-weight: 600; color: #c9d1d9;
                        padding-top: 20px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; }
        """)
        class_layout = QVBoxLayout(class_group)

        self.class_table = QTableWidget()
        self.class_table.setColumnCount(2)
        self.class_table.setHorizontalHeaderLabels(["Class", "Count"])
        self.class_table.horizontalHeader().setStretchLastSection(True)
        self.class_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.class_table.setStyleSheet("""
            QTableWidget { background-color: #0d1117; color: #c9d1d9;
                           border: none; gridline-color: #21262d; }
            QHeaderView::section { background-color: #161b22; color: #8b949e;
                                   font-weight: 600; border: 1px solid #21262d; padding: 4px; }
        """)
        self.class_table.verticalHeader().setVisible(False)
        class_layout.addWidget(self.class_table)
        mid_layout.addWidget(class_group, stretch=1)

        main_layout.addLayout(mid_layout, stretch=1)

        # Bottom: Recent AI Events table
        events_group = QGroupBox("RECENT AI EVENTS")
        events_group.setStyleSheet("""
            QGroupBox { background-color: #0d1117; border: 1px solid #30363d;
                        border-radius: 6px; font-weight: 600; color: #c9d1d9;
                        padding-top: 20px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; }
        """)
        events_layout = QVBoxLayout(events_group)

        self.events_table = QTableWidget()
        self.events_table.setColumnCount(6)
        self.events_table.setHorizontalHeaderLabels(["Time", "Channel", "Event", "Class", "Confidence", "Severity"])
        self.events_table.horizontalHeader().setStretchLastSection(True)
        self.events_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.events_table.setStyleSheet("""
            QTableWidget { background-color: #0d1117; color: #c9d1d9;
                           border: none; gridline-color: #21262d; }
            QHeaderView::section { background-color: #161b22; color: #8b949e;
                                   font-weight: 600; border: 1px solid #21262d; padding: 4px; }
        """)
        self.events_table.verticalHeader().setVisible(False)
        events_layout.addWidget(self.events_table)

        main_layout.addWidget(events_group, stretch=1)

        self.main_tabs.addTab(telemetry_widget, "Inference & Telemetry")

        # Tab 1: Video Analytics & Surveillance Rules
        self.rules_widget = AnalyticsRulesWidget()
        self.main_tabs.addTab(self.rules_widget, "Surveillance Rules & Analytics")

        root_layout.addWidget(self.main_tabs)

    def _start_refresh_timer(self):
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_data)
        self._refresh_timer.start(2000)

    def refresh_data(self):
        """Refreshes dashboard with live data from inference workers and event processor."""
        try:
            self._update_metrics()
        except Exception as e:
            logger.debug("Dashboard refresh skipped: %s", e)

    def _update_metrics(self):
        """Pulls metrics from inference worker manager and event processor."""
        try:
            from engines.ai_engine.inference_worker import inference_worker_manager
            from engines.event_engine.event_processor import event_processor

            # Get inference metrics
            all_metrics = inference_worker_manager.get_all_metrics()
            active_channels = inference_worker_manager.get_active_channels()

            # Device card
            devices = set(m.get("device", "N/A") for m in all_metrics.values())
            device_str = ", ".join(devices) if devices else "No Active Inference"
            self.card_device.set_value(device_str, "#3fb950" if devices else "#8b949e")

            # Active channels
            self.card_active_channels.set_value(str(len(active_channels)))

            # Aggregate metrics
            total_inferences = sum(m.get("total_inferences", 0) for m in all_metrics.values())
            self.card_total_detections.set_value(f"{total_inferences:,}")

            avg_latencies = [m.get("avg_latency_ms", 0) for m in all_metrics.values() if m.get("avg_latency_ms", 0) > 0]
            avg_lat = sum(avg_latencies) / len(avg_latencies) if avg_latencies else 0
            lat_color = "#3fb950" if avg_lat < 50 else "#d29922" if avg_lat < 100 else "#f85149"
            self.card_avg_latency.set_value(f"{avg_lat:.1f} ms", lat_color)

            total_fps = sum(m.get("fps", 0) for m in all_metrics.values())
            self.card_inference_fps.set_value(f"{total_fps:.1f}")

            # Event stats
            event_stats = event_processor.get_statistics()
            self.card_events.set_value(f"{event_stats.get('total_events_generated', 0):,}")

            # Update per-channel table
            self.channel_table.setRowCount(len(all_metrics))
            for row, (ch_id, metrics) in enumerate(all_metrics.items()):
                self.channel_table.setItem(row, 0, QTableWidgetItem(ch_id[:16]))
                self.channel_table.setItem(row, 1, QTableWidgetItem(metrics.get("device", "N/A")))
                self.channel_table.setItem(row, 2, QTableWidgetItem(f"{metrics.get('fps', 0):.1f}"))
                self.channel_table.setItem(row, 3, QTableWidgetItem(f"{metrics.get('avg_latency_ms', 0):.1f} ms"))
                self.channel_table.setItem(row, 4, QTableWidgetItem(str(metrics.get("total_inferences", 0))))

            # Update class breakdown
            events_by_class = event_stats.get("events_by_class", {})
            self.class_table.setRowCount(len(events_by_class))
            for row, (cls_name, count) in enumerate(sorted(events_by_class.items(), key=lambda x: -x[1])):
                self.class_table.setItem(row, 0, QTableWidgetItem(cls_name))
                self.class_table.setItem(row, 1, QTableWidgetItem(str(count)))

            # Update recent events
            recent = event_processor.get_recent_events(limit=15)
            self.events_table.setRowCount(len(recent))
            for row, evt in enumerate(recent):
                ts = datetime.fromtimestamp(evt.get("timestamp", 0), tz=timezone.utc).strftime("%H:%M:%S")
                self.events_table.setItem(row, 0, QTableWidgetItem(ts))
                self.events_table.setItem(row, 1, QTableWidgetItem(str(evt.get("channel_id", ""))[:16]))
                self.events_table.setItem(row, 2, QTableWidgetItem(evt.get("event_type", "")))
                self.events_table.setItem(row, 3, QTableWidgetItem(evt.get("class_name", "")))
                self.events_table.setItem(row, 4, QTableWidgetItem(f"{evt.get('confidence', 0):.2f}"))

                severity = evt.get("severity", "INFO")
                sev_item = QTableWidgetItem(severity)
                if severity == "CRITICAL":
                    sev_item.setForeground(QColor("#f85149"))
                elif severity == "WARNING":
                    sev_item.setForeground(QColor("#d29922"))
                else:
                    sev_item.setForeground(QColor("#8b949e"))
                self.events_table.setItem(row, 5, sev_item)

        except ImportError:
            pass  # Modules not yet loaded during startup
