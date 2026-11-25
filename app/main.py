"""
CCTV AI Intelligence Platform - Main Desktop Application Entry Point.
Implements the professional Windows 11 PySide6 GUI with dark surveillance theme,
15 primary workspace views, live telemetry, and worker lifecycle management.
"""

import sys
from datetime import datetime, timezone
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QStatusBar, QFrame,
    QComboBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon

from app.bootstrap import bootstrap_application
from app.application_state import app_state
from resources.styles.theme import DARK_THEME_QSS
from modules.dashboard.dashboard_widget import DashboardWidget
from modules.live_monitoring.live_view_widget import LiveViewWidget
from modules.video_playback.playback_widget import PlaybackWidget
from modules.ai_intelligence.ai_dashboard_widget import AIDashboardWidget
from modules.anpr_intelligence.anpr_workspace_widget import ANPRWorkspaceWidget
from modules.video_enhancement.enhancement_widget import VideoEnhancementWidget
from modules.camera_management.discovery_dialog import DeviceDiscoveryDialog
from engines.video_engine.stream_manager import stream_manager
from engines.video_engine.playback_controller import playback_controller
from engines.recording_engine.recording_manager import recording_manager
from engines.ai_engine.inference_worker import inference_worker_manager
from core.workers.worker_manager import worker_manager
from database.database_manager import db_manager
from core.config.settings import settings


class ModulePlaceholderWidget(QWidget):
    """Clean placeholder for upcoming phase modules."""

    def __init__(self, module_title: str, phase_info: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setProperty("class", "card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setAlignment(Qt.AlignCenter)

        lbl_title = QLabel(module_title)
        lbl_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #58a6ff; margin-bottom: 8px;")
        lbl_title.setAlignment(Qt.AlignCenter)

        lbl_phase = QLabel(phase_info)
        lbl_phase.setStyleSheet("font-size: 14px; color: #8b949e;")
        lbl_phase.setAlignment(Qt.AlignCenter)

        card_layout.addWidget(lbl_title)
        card_layout.addWidget(lbl_phase)
        layout.addWidget(card)


class MainWindow(QMainWindow):
    """Primary Command Center Application Window."""

    NAV_ITEMS = [
        ("Dashboard", "Surveillance & System Overview"),
        ("Live View", "64-Channel Real-time Monitoring Grid"),
        ("Playback", "Multi-Camera Synchronized Playback"),
        ("AI Intelligence", "Deep Learning Video Analytics"),
        ("Investigation", "Smart Metadata Search & Indexing"),
        ("Video Forensics", "Digital Integrity & Discontinuity Analysis"),
        ("Video Enhancement", "AI Super-Resolution & Low-Light Enhancement"),
        ("Devices", "ONVIF/RTSP/NVR/DVR Camera Management"),
        ("Network Tools", "IP Scanner, Topology & Diagnostics"),
        ("Alarms", "Real-time Incident & Alert Engine"),
        ("Storage", "Recording Schedules & Volume Management"),
        ("Reports", "PDF/Excel Intelligence & Audit Reports"),
        ("AI Models", "OpenVINO & ONNX Model Registry"),
        ("Administration", "RBAC Users, Roles & Security Policies"),
        ("Settings", "System, Network & Video Configuration"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CCTV AI Intelligence Platform - Command Center")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)

        self._nav_buttons = []
        self._init_ui()
        self._start_timers()

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Top Header Bar
        header = self._create_header()
        root_layout.addWidget(header)

        # 2. Main Workspace Layout (Sidebar + Stacked Workspaces)
        workspace_layout = QHBoxLayout()
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)

        sidebar = self._create_sidebar()
        workspace_layout.addWidget(sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("ContentArea")

        # View 0: Primary Dashboard
        self.dashboard_widget = DashboardWidget()
        self.stack.addWidget(self.dashboard_widget)

        # View 1: Live Monitoring Grid (1, 4, 9, 16 cameras)
        self.live_view_widget = LiveViewWidget()
        self.stack.addWidget(self.live_view_widget)

        # View 2: Playback Workspace (Synchronized Multi-Camera Playback & Export)
        self.playback_widget = PlaybackWidget()
        self.stack.addWidget(self.playback_widget)

        # View 3: AI Intelligence Workspace (Deep Learning Video Analytics)
        self.ai_dashboard_widget = AIDashboardWidget()
        self.stack.addWidget(self.ai_dashboard_widget)

        # View 4: Smart Investigation & ANPR Intelligence Workspace
        self.investigation_widget = ANPRWorkspaceWidget()
        self.stack.addWidget(self.investigation_widget)

        # View 5: Video Forensics (Digital Integrity & Discontinuity Analysis)
        title_5, desc_5 = self.NAV_ITEMS[5]
        self.forensics_placeholder = ModulePlaceholderWidget(
            module_title=f"{title_5.upper()}",
            phase_info=f"{desc_5} — Scheduled for implementation under Phase 5.",
        )
        self.stack.addWidget(self.forensics_placeholder)

        # View 6: Video Enhancement Workspace (Phase 9 - F-040 through F-045)
        self.enhancement_widget = VideoEnhancementWidget()
        self.stack.addWidget(self.enhancement_widget)

        # Views 7 to 14: Module Placeholders
        for idx, (title, desc) in enumerate(self.NAV_ITEMS[7:], start=7):
            phase_num = f"Phase {idx}" if idx < 12 else "Phase 12+"
            placeholder = ModulePlaceholderWidget(
                module_title=f"{title.upper()}",
                phase_info=f"{desc} — Scheduled for implementation under {phase_num}.",
            )
            self.stack.addWidget(placeholder)

        workspace_layout.addWidget(self.stack, stretch=1)
        root_layout.addLayout(workspace_layout, stretch=1)

        # 3. Status Bar
        self._init_status_bar()

    def _create_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("HeaderWidget")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        # Branding & Title
        lbl_title = QLabel("CCTV AI INTELLIGENCE PLATFORM")
        lbl_title.setObjectName("AppTitleLabel")
        layout.addWidget(lbl_title)

        lbl_sep = QLabel("|")
        lbl_sep.setStyleSheet("color: #30363d; font-weight: bold;")
        layout.addWidget(lbl_sep)

        # Site Selector
        lbl_site = QLabel("Site:")
        lbl_site.setStyleSheet("color: #8b949e; font-weight: 600;")
        layout.addWidget(lbl_site)

        self.combo_site = QComboBox()
        self.combo_site.addItems(["Default Headquarters (Main Site)", "Branch 1 (West Facility)", "Branch 2 (South Warehouse)"])
        self.combo_site.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; padding: 4px 8px; border-radius: 4px;")
        layout.addWidget(self.combo_site)

        # Discovery Button
        self.btn_discovery = QPushButton("  Discover Cameras")
        self.btn_discovery.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; border-radius: 4px; padding: 4px 10px; color: #58a6ff; font-weight: 600;")
        self.btn_discovery.clicked.connect(self._open_discovery_dialog)
        layout.addWidget(self.btn_discovery)

        layout.addStretch()

        # Intel OpenVINO Badge
        self.badge_intel = QLabel("INTEL UHD GPU ACTIVE (OpenVINO™)")
        self.badge_intel.setObjectName("BadgeIntel")
        layout.addWidget(self.badge_intel)

        # System Health Badge
        self.badge_health = QLabel("SYSTEM HEALTHY")
        self.badge_health.setObjectName("BadgeHealthy")
        layout.addWidget(self.badge_health)

        # Active Alarms Badge
        self.badge_alarm = QLabel("0 ALARMS")
        self.badge_alarm.setObjectName("BadgeAlarm")
        layout.addWidget(self.badge_alarm)

        # Live Clock
        self.lbl_clock = QLabel()
        self.lbl_clock.setObjectName("ClockLabel")
        self._update_clock()
        layout.addWidget(self.lbl_clock)

        return header

    def _create_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("SidebarWidget")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(4)

        for idx, (title, _) in enumerate(self.NAV_ITEMS):
            btn = QPushButton(f"  {title}")
            btn.setProperty("class", "nav-btn")
            btn.setCheckable(True)
            if idx == 0:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, index=idx: self._switch_view(index))
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        # System Version Indicator
        lbl_ver = QLabel(f"v{settings.app_version} (Offline Local)")
        lbl_ver.setStyleSheet("color: #484f58; font-size: 11px; padding: 8px 12px;")
        layout.addWidget(lbl_ver)

        return sidebar

    def _init_status_bar(self) -> None:
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.lbl_db_status = QLabel("DB: SQLite WAL (Connected)")
        self.lbl_threads = QLabel("Worker Threads: 0")
        self.lbl_uptime = QLabel("Uptime: 0s")
        self.lbl_storage_io = QLabel("Storage IO: Idle")

        self.status_bar.addWidget(self.lbl_db_status, 2)
        self.status_bar.addWidget(self.lbl_threads, 1)
        self.status_bar.addWidget(self.lbl_storage_io, 1)
        self.status_bar.addPermanentWidget(self.lbl_uptime)

    def _switch_view(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)

    def _start_timers(self) -> None:
        # Clock timer (every 1 second)
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)

        # Telemetry timer (every 3 seconds)
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self._update_telemetry)
        self.telemetry_timer.start(3000)

    def _update_clock(self) -> None:
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self.lbl_clock.setText(now_utc)

    def _update_telemetry(self) -> None:
        self.dashboard_widget.refresh_telemetry()
        uptime_sec = int(app_state.uptime_seconds)
        mins, secs = divmod(uptime_sec, 60)
        hours, mins = divmod(mins, 60)
        self.lbl_uptime.setText(f"Uptime: {hours:02d}:{mins:02d}:{secs:02d}")

    def _open_discovery_dialog(self) -> None:
        """Opens camera discovery and manual addition dialog."""
        dialog = DeviceDiscoveryDialog(self)
        dialog.exec()

    def closeEvent(self, event) -> None:
        """Handles clean application shutdown on window close."""
        self.clock_timer.stop()
        self.telemetry_timer.stop()
        inference_worker_manager.stop_all()
        recording_manager.stop_all()
        playback_controller.stop()
        stream_manager.stop_all()
        worker_manager.shutdown()
        db_manager.close()
        event.accept()


def run_desktop_app() -> int:
    """Initializes and runs the PySide6 Qt application event loop."""
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    # Apply Dark Surveillance QSS Theme
    app.setStyleSheet(DARK_THEME_QSS)

    # Run Bootstrap Sequence
    bootstrap_application()

    # Launch Main Window
    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(run_desktop_app())
