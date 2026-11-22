"""
Surveillance Command Center Dashboard Widget.
Displays real-time hardware telemetry (CPU, RAM, Intel UHD 730 GPU, Storage),
surveillance capacity metrics (up to 64 channels), OpenVINO AI engine status,
and recent surveillance/AI events.
"""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QFrame, QProgressBar, QTableWidget, QTableWidgetItem,
    QHeaderView, QScrollArea
)
from PySide6.QtCore import Qt

from app.application_state import app_state
from core.hardware.detector import HardwareDetector


class MetricCard(QFrame):
    """Reusable metric card component."""

    def __init__(self, title: str, value: str = "0", subtext: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setProperty("class", "card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.lbl_title = QLabel(title)
        self.lbl_title.setProperty("class", "card-title")

        self.lbl_value = QLabel(value)
        self.lbl_value.setProperty("class", "card-value")

        self.lbl_subtext = QLabel(subtext)
        self.lbl_subtext.setProperty("class", "card-subtext")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_subtext)
        layout.addStretch()

    def set_value(self, value: str, subtext: Optional[str] = None) -> None:
        self.lbl_value.setText(value)
        if subtext is not None:
            self.lbl_subtext.setText(subtext)


class GaugeCard(QFrame):
    """Metric card with embedded progress bar gauge."""

    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setProperty("class", "card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        self.lbl_title = QLabel(title)
        self.lbl_title.setProperty("class", "card-title")

        self.lbl_value = QLabel("0%")
        self.lbl_value.setProperty("class", "card-value")

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)

        self.lbl_subtext = QLabel("")
        self.lbl_subtext.setProperty("class", "card-subtext")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.progress)
        layout.addWidget(self.lbl_subtext)
        layout.addStretch()

    def update_gauge(self, percent: float, value_str: str, subtext: str) -> None:
        val = int(min(max(percent, 0), 100))
        self.progress.setValue(val)
        self.lbl_value.setText(value_str)
        self.lbl_subtext.setText(subtext)

        # Dynamic warning/critical color coding
        if val > 90:
            self.progress.setProperty("class", "critical")
        elif val > 75:
            self.progress.setProperty("class", "warning")
        else:
            self.progress.setProperty("class", "")
        self.progress.style().unpolish(self.progress)
        self.progress.style().polish(self.progress)


class DashboardWidget(QWidget):
    """Primary surveillance and intelligence dashboard workspace."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 1. Section Header: Surveillance Capacity
        lbl_sec1 = QLabel("SURVEILLANCE OVERVIEW (64-CHANNEL CAPACITY)")
        lbl_sec1.setProperty("class", "card-title")
        layout.addWidget(lbl_sec1)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        self.card_total = MetricCard("Configured Cameras", "0 / 64", "Capacity: 64 Channels")
        self.card_online = MetricCard("Online Streams", "0", "0% active")
        self.card_offline = MetricCard("Offline Cameras", "0", "All normal")
        self.card_recordings = MetricCard("Active Recordings", "0", "Storage streaming")
        self.card_ai_detections = MetricCard("Active AI Inference", "0", "Live pipeline")
        self.card_alarms = MetricCard("Critical Alarms", "0", "No active triggers")

        cards_layout.addWidget(self.card_total)
        cards_layout.addWidget(self.card_online)
        cards_layout.addWidget(self.card_offline)
        cards_layout.addWidget(self.card_recordings)
        cards_layout.addWidget(self.card_ai_detections)
        cards_layout.addWidget(self.card_alarms)
        layout.addLayout(cards_layout)

        # 2. Section Header: Hardware & Acceleration Telemetry
        lbl_sec2 = QLabel("SYSTEM & INTEL HARDWARE ACCELERATION")
        lbl_sec2.setProperty("class", "card-title")
        layout.addWidget(lbl_sec2)

        hw_layout = QHBoxLayout()
        hw_layout.setSpacing(12)

        self.gauge_cpu = GaugeCard("Intel CPU Load")
        self.gauge_ram = GaugeCard("System RAM")
        self.gauge_gpu = GaugeCard("Intel UHD GPU Status")
        self.gauge_disk = GaugeCard("Storage Capacity")

        hw_layout.addWidget(self.gauge_cpu)
        hw_layout.addWidget(self.gauge_ram)
        hw_layout.addWidget(self.gauge_gpu)
        hw_layout.addWidget(self.gauge_disk)
        layout.addLayout(hw_layout)

        # 3. Acceleration Detail Panel
        self.panel_accel = QFrame()
        self.panel_accel.setProperty("class", "card")
        accel_layout = QGridLayout(self.panel_accel)
        accel_layout.setContentsMargins(16, 12, 16, 12)
        accel_layout.setSpacing(8)

        self.lbl_cpu_model = QLabel("CPU: Probing...")
        self.lbl_gpu_model = QLabel("GPU: Probing...")
        self.lbl_openvino_status = QLabel("OpenVINO: Initializing...")
        self.lbl_db_backend = QLabel("Database Engine: Probing...")

        accel_layout.addWidget(self.lbl_cpu_model, 0, 0)
        accel_layout.addWidget(self.lbl_gpu_model, 0, 1)
        accel_layout.addWidget(self.lbl_openvino_status, 1, 0)
        accel_layout.addWidget(self.lbl_db_backend, 1, 1)
        layout.addWidget(self.panel_accel)

        # 4. Section: Live Intelligence & Event Feed
        lbl_sec3 = QLabel("RECENT SURVEILLANCE & AI EVENTS")
        lbl_sec3.setProperty("class", "card-title")
        layout.addWidget(lbl_sec3)

        self.table_events = QTableWidget(0, 5)
        self.table_events.setHorizontalHeaderLabels(["Timestamp (UTC)", "Camera", "Event Type", "Severity", "Details"])
        self.table_events.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_events.setMinimumHeight(240)
        self.table_events.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_events.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table_events)

        layout.addStretch()

        scroll.setWidget(container)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

        # Initial telemetry population
        self.refresh_telemetry()

    def refresh_telemetry(self) -> None:
        """Polls runtime metrics safely and updates UI widgets."""
        report = app_state.hardware_report or HardwareDetector.generate_full_report()

        # Update Hardware Gauges
        cpu = HardwareDetector.detect_cpu()
        self.gauge_cpu.update_gauge(
            percent=cpu.current_usage_percent,
            value_str=f"{cpu.current_usage_percent:.1f}%",
            subtext=f"{cpu.logical_cores} Cores @ {cpu.frequency_mhz} MHz",
        )

        ram = HardwareDetector.detect_ram()
        self.gauge_ram.update_gauge(
            percent=ram.usage_percent,
            value_str=f"{ram.used_gb:.1f} / {ram.total_gb:.1f} GB",
            subtext=f"{ram.available_gb:.1f} GB Available",
        )

        storage = HardwareDetector.detect_storage()
        self.gauge_disk.update_gauge(
            percent=storage.usage_percent,
            value_str=f"{storage.free_gb:.1f} GB Free",
            subtext=f"Total: {storage.total_gb:.1f} GB ({storage.drive_path})",
        )

        # GPU Gauge
        if report.openvino.has_intel_gpu_acceleration:
            self.gauge_gpu.update_gauge(
                percent=15.0,  # Idle baseline
                value_str="ACTIVE (Intel GPU)",
                subtext="OpenVINO GPU Offload Enabled",
            )
        else:
            self.gauge_gpu.update_gauge(
                percent=0.0,
                value_str="CPU FALLBACK",
                subtext="OpenVINO CPU Execution",
            )

        # Update Acceleration Panel Details
        gpu_name = report.gpus[0].name if report.gpus else "Integrated Display Device"
        self.lbl_cpu_model.setText(f"<b>CPU:</b> {cpu.model} ({cpu.logical_cores} Threads)")
        self.lbl_gpu_model.setText(f"<b>GPU:</b> {gpu_name}")
        self.lbl_openvino_status.setText(
            f"<b>OpenVINO™:</b> v{report.openvino.version} | Devices: {', '.join(report.openvino.available_devices)}"
        )
        self.lbl_db_backend.setText("<b>Database:</b> SQLite WAL Mode (PostgreSQL Compatible)")

        # Update Surveillance Overview
        summary = app_state.get_summary()
        self.card_total.set_value(f"{summary['configured_channels']} / 64")
        self.card_online.set_value(str(summary["online_channels"]))
        self.card_offline.set_value(str(summary["offline_channels"]))
        self.card_recordings.set_value(str(summary["active_recordings"]))
        self.card_ai_detections.set_value(str(summary["active_ai_channels"]))
        self.card_alarms.set_value(str(summary["active_alarms"]))
