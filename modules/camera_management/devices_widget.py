"""
Camera & Device Management Workspace Widget (Phase 15 - Milestone W2/W4).
Mounted at Desktop View 7 (Devices). Provides a dynamic camera inventory table,
real-time online/standby status indicators, search filtering, KPI metrics,
and seamless integration with DeviceDiscoveryDialog.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QComboBox, QMessageBox, QFrame, QApplication, QAbstractItemView
)

from database.database_manager import db_manager
from sqlalchemy import func, select
from database.models.devices import Device, DeviceChannel, StreamProfile
from modules.camera_management.discovery_dialog import DeviceDiscoveryDialog
from core.security.crypto import mask_rtsp_url
from core.logging.logger import get_logger

logger = get_logger("devices_widget")


class DeviceManagementWidget(QWidget):
    """Primary Command Center Workspace for Camera & Device Inventory Management."""

    camera_selected = Signal(str)  # Emits device_id when a camera row is selected

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._cached_devices: List[Dict[str, Any]] = []
        self._init_ui()
        self.refresh_devices()

    def _init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        # 1. Header Toolbar
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        v_title = QVBoxLayout()
        lbl_title = QLabel("CAMERA & DEVICE MANAGEMENT")
        lbl_title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #58a6ff;")
        lbl_sub = QLabel("ONVIF / RTSP / NVR / DVR Network Video Device Inventory & Configuration")
        lbl_sub.setStyleSheet("font-size: 9pt; color: #8b949e;")
        v_title.addWidget(lbl_title)
        v_title.addWidget(lbl_sub)
        header_layout.addLayout(v_title)

        header_layout.addStretch()

        self.btn_refresh = QPushButton("  Refresh List")
        self.btn_refresh.setStyleSheet(
            "background-color: #21262d; border: 1px solid #30363d; border-radius: 4px; "
            "padding: 6px 14px; color: #c9d1d9; font-weight: 600;"
        )
        self.btn_refresh.clicked.connect(self.refresh_devices)
        header_layout.addWidget(self.btn_refresh)

        self.btn_add = QPushButton("+ Add / Discover Camera")
        self.btn_add.setStyleSheet(
            "background-color: #238636; border: 1px solid #2ea043; border-radius: 4px; "
            "padding: 6px 14px; color: #ffffff; font-weight: 600;"
        )
        self.btn_add.clicked.connect(self._open_discovery)
        header_layout.addWidget(self.btn_add)

        root_layout.addLayout(header_layout)

        # 2. KPI Telemetry Cards
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(10)

        self.card_total, self.lbl_val_total = self._create_kpi_card("TOTAL REGISTERED", "0", "#58a6ff")
        self.card_online, self.lbl_val_online = self._create_kpi_card("ONLINE / STREAMING", "0", "#2ea043")
        self.card_standby, self.lbl_val_standby = self._create_kpi_card("STANDBY / OFFLINE", "0", "#d29922")
        self.card_channels, self.lbl_val_channels = self._create_kpi_card("TOTAL CHANNELS", "0", "#a371f7")

        kpi_layout.addWidget(self.card_total)
        kpi_layout.addWidget(self.card_online)
        kpi_layout.addWidget(self.card_standby)
        kpi_layout.addWidget(self.card_channels)
        root_layout.addLayout(kpi_layout)

        # 3. Search and Filter Bar
        filter_frame = QFrame()
        filter_frame.setStyleSheet("background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 6px;")
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(8, 4, 8, 4)
        filter_layout.setSpacing(10)

        lbl_filter = QLabel("Search:")
        lbl_filter.setStyleSheet("color: #8b949e; font-weight: bold;")
        filter_layout.addWidget(lbl_filter)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Filter by camera name, IP address, manufacturer...")
        self.txt_search.setStyleSheet("background: #0d1117; border: 1px solid #30363d; color: #c9d1d9; padding: 4px 8px; border-radius: 4px;")
        self.txt_search.textChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.txt_search, 2)

        lbl_status_filter = QLabel("Status:")
        lbl_status_filter.setStyleSheet("color: #8b949e; font-weight: bold;")
        filter_layout.addWidget(lbl_status_filter)

        self.combo_status = QComboBox()
        self.combo_status.addItems(["All Statuses", "Online Only", "Offline Only"])
        self.combo_status.setStyleSheet("background: #0d1117; border: 1px solid #30363d; color: #c9d1d9; padding: 4px 8px; border-radius: 4px;")
        self.combo_status.currentIndexChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.combo_status)

        root_layout.addWidget(filter_frame)

        # 4. Inventory Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Status", "Camera Name", "IP Address", "HTTP Port", "RTSP Port",
            "Manufacturer", "RTSP URL", "Device ID"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0d1117;
                color: #c9d1d9;
                gridline-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 6px;
                selection-background-color: #1f6feb;
            }
            QHeaderView::section {
                background-color: #161b22;
                color: #8b949e;
                padding: 6px;
                border: 1px solid #21262d;
                font-weight: 600;
            }
        """)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        root_layout.addWidget(self.table)

    def _create_kpi_card(self, title: str, initial_value: str, accent_color: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #161b22;
                border: 1px solid #30363d;
                border-left: 4px solid {accent_color};
                border-radius: 6px;
                padding: 10px;
            }}
        """)
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(8, 4, 8, 4)
        vbox.setSpacing(2)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 8pt; font-weight: bold; color: #8b949e;")
        lbl_v = QLabel(initial_value)
        lbl_v.setObjectName("val")
        lbl_v.setStyleSheet(f"font-size: 16pt; font-weight: bold; color: {accent_color};")

        vbox.addWidget(lbl_t)
        vbox.addWidget(lbl_v)
        return card, lbl_v

    def _open_discovery(self) -> None:
        """Opens discovery dialog and hooks its registration signal for auto-refresh."""
        dialog = DeviceDiscoveryDialog(self)
        dialog.camera_registered.connect(self._on_camera_registered)
        dialog.exec()

    def _on_camera_registered(self, dev_id: str) -> None:
        """Slot invoked whenever a camera is registered in the dialog."""
        logger.info("New camera registered: %s. Refreshing inventory table.", dev_id)
        self.refresh_devices()

    def refresh_devices(self) -> None:
        """Queries database for all non-deleted cameras and updates UI."""
        devices_data = []
        try:
            with db_manager.get_session() as session:
                devices = session.query(Device).filter(Device.is_deleted == False).order_by(Device.created_at.asc()).all()
                total_channels = 0
                for d in devices:
                    primary_ch = d.channels[0] if d.channels else None
                    primary_prof = primary_ch.stream_profiles[0] if (primary_ch and primary_ch.stream_profiles) else None
                    channel_count = session.scalar(
                        select(func.count())
                        .select_from(DeviceChannel)
                        .where(DeviceChannel.device_id == d.id)
                    ) or 0
                    total_channels += channel_count

                    raw_rtsp_url = primary_prof.rtsp_url if primary_prof else f"rtsp://{d.ip_address}:{d.rtsp_port}/live"
                    rtsp_url = mask_rtsp_url(raw_rtsp_url)

                    devices_data.append({
                        "id": d.id,
                        "name": d.name,
                        "ip_address": d.ip_address,
                        "port": d.port or 80,
                        "rtsp_port": d.rtsp_port or 554,
                        "manufacturer": d.manufacturer or "GENERIC_ONVIF",
                        "is_online": bool(d.is_online),
                        "rtsp_url": rtsp_url,
                        "total_channels": channel_count
                    })

            self._cached_devices = devices_data
            total = len(devices_data)
            online = sum(1 for d in devices_data if d["is_online"])
            standby = total - online

            # Update KPI metrics
            self.lbl_val_total.setText(str(total))
            self.lbl_val_online.setText(str(online))
            self.lbl_val_standby.setText(str(standby))
            self.lbl_val_channels.setText(str(total_channels))

            self._apply_filters()
            logger.info("Refreshed camera inventory: %d devices loaded.", total)
        except Exception as e:
            logger.error("Failed to refresh camera list: %s", e)

    def _apply_filters(self) -> None:
        """Filters cached devices according to search text and status dropdown."""
        search = self.txt_search.text().strip().lower()
        status_mode = self.combo_status.currentIndex()  # 0: All, 1: Online Only, 2: Offline Only

        filtered = []
        for d in self._cached_devices:
            if status_mode == 1 and not d["is_online"]:
                continue
            if status_mode == 2 and d["is_online"]:
                continue

            if search:
                matched = (
                    search in d["name"].lower() or
                    search in d["ip_address"].lower() or
                    search in d["manufacturer"].lower() or
                    search in d["id"].lower()
                )
                if not matched:
                    continue

            filtered.append(d)

        self._populate_table(filtered)

    def _populate_table(self, devices: List[Dict[str, Any]]) -> None:
        self.table.setRowCount(len(devices))
        for row, d in enumerate(devices):
            # 0. Status Badge
            is_on = d["is_online"]
            status_text = "● ONLINE" if is_on else "○ STANDBY"
            item_status = QTableWidgetItem(status_text)
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_status.setForeground(QColor("#2ea043" if is_on else "#d29922"))

            # 1. Camera Name
            item_name = QTableWidgetItem(d["name"])
            font = QFont()
            font.setBold(True)
            item_name.setFont(font)

            # 2. IP Address
            item_ip = QTableWidgetItem(d["ip_address"])
            item_ip.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # 3. HTTP Port
            item_port = QTableWidgetItem(str(d["port"]))
            item_port.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # 4. RTSP Port
            item_rtsp = QTableWidgetItem(str(d["rtsp_port"]))
            item_rtsp.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # 5. Manufacturer
            item_mfg = QTableWidgetItem(d["manufacturer"])

            # 6. RTSP URL
            item_url = QTableWidgetItem(d["rtsp_url"])
            item_url.setForeground(QColor("#58a6ff"))

            # 7. Device ID
            item_id = QTableWidgetItem(d["id"][:8] + "...")
            item_id.setToolTip(d["id"])
            item_id.setForeground(QColor("#8b949e"))

            self.table.setItem(row, 0, item_status)
            self.table.setItem(row, 1, item_name)
            self.table.setItem(row, 2, item_ip)
            self.table.setItem(row, 3, item_port)
            self.table.setItem(row, 4, item_rtsp)
            self.table.setItem(row, 5, item_mfg)
            self.table.setItem(row, 6, item_url)
            self.table.setItem(row, 7, item_id)
