"""
Camera Discovery and Device Registration Dialog.
Provides ONVIF WS-Discovery multicast search, IP subnet scanning,
and manual camera/recorder registration with encrypted credential storage.
"""

from typing import Optional, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QTabWidget, QWidget, QComboBox, QMessageBox, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal

from integrations.onvif.discovery import CameraDiscoveryEngine, DiscoveredCamera
from core.security.crypto import credential_vault
from database.database_manager import db_manager
from database.models.devices import Device, DeviceChannel, StreamProfile, DeviceCredential, DeviceStatus


class DiscoveryWorkerThread(QThread):
    """Background worker executing network camera discovery without blocking Qt."""

    progress_updated = Signal(int, int)  # current, total
    discovery_finished = Signal(list)     # list of DiscoveredCamera
    error_occurred = Signal(str)

    def __init__(self, mode: str = "WS", subnet_cidr: str = "") -> None:
        super().__init__()
        self.mode = mode
        self.subnet_cidr = subnet_cidr
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        try:
            if self.mode == "WS":
                results = CameraDiscoveryEngine.discover_onvif_ws(timeout_sec=2.5)
            else:
                results = CameraDiscoveryEngine.scan_subnet(
                    subnet_cidr=self.subnet_cidr,
                    progress_cb=lambda cur, tot: self.progress_updated.emit(cur, tot),
                    cancel_token=lambda: self._is_cancelled,
                )
            self.discovery_finished.emit(results)
        except Exception as e:
            self.error_occurred.emit(str(e))


class DeviceDiscoveryDialog(QDialog):
    """Dialog for automated device discovery and manual camera addition."""

    camera_registered = Signal(str)  # Emits channel_id when camera is added

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Camera Discovery & Device Registration")
        self.resize(800, 560)
        self.setStyleSheet("""
            QDialog { background-color: #0d1117; color: #e6edf3; }
            QLineEdit, QComboBox { background-color: #161b22; border: 1px solid #30363d; border-radius: 4px; padding: 6px; color: #f0f6fc; }
            QPushButton { background-color: #21262d; border: 1px solid #30363d; border-radius: 4px; padding: 6px 14px; color: #c9d1d9; font-weight: 600; }
            QPushButton:hover { background-color: #30363d; color: #58a6ff; }
            QTableWidget { background-color: #161b22; gridline-color: #21262d; border: 1px solid #30363d; }
            QProgressBar { background-color: #21262d; border: 1px solid #30363d; border-radius: 4px; text-align: center; height: 14px; }
            QProgressBar::chunk { background-color: #1f6feb; }
        """)

        self.discovered_cams: List[DiscoveredCamera] = []
        self.worker: Optional[DiscoveryWorkerThread] = None

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.setStyleSheet("QTabBar::tab { background: #161b22; color: #8b949e; padding: 8px 16px; } QTabBar::tab:selected { background: #21262d; color: #58a6ff; font-weight: bold; }")

        # Tab 1: Network Auto-Discovery
        tab_auto = QWidget()
        auto_layout = QVBoxLayout(tab_auto)

        ctrl_bar = QHBoxLayout()
        self.btn_ws = QPushButton("ONVIF WS-Discovery (Multicast)")
        self.btn_ws.clicked.connect(self._start_ws_discovery)

        self.txt_subnet = QLineEdit("192.168.1.0/24")
        self.btn_subnet = QPushButton("Scan IP Range")
        self.btn_subnet.clicked.connect(self._start_subnet_scan)

        ctrl_bar.addWidget(self.btn_ws)
        ctrl_bar.addWidget(QLabel("Subnet:"))
        ctrl_bar.addWidget(self.txt_subnet)
        ctrl_bar.addWidget(self.btn_subnet)
        auto_layout.addLayout(ctrl_bar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        auto_layout.addWidget(self.progress_bar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["IP Address", "MAC Address", "Manufacturer", "Model", "ONVIF Port", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        auto_layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.btn_add_selected = QPushButton("Add Selected Camera to System")
        self.btn_add_selected.setStyleSheet("background-color: #238636; color: #ffffff;")
        self.btn_add_selected.clicked.connect(self._add_selected_camera)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_add_selected)
        auto_layout.addLayout(btn_row)

        tabs.addTab(tab_auto, "Network Auto-Discovery")

        # Tab 2: Manual Registration
        tab_manual = QWidget()
        manual_layout = QVBoxLayout(tab_manual)

        form_frame = QFrame()
        form_frame.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 16px;")
        f_layout = QVBoxLayout(form_frame)

        self.txt_man_name = QLineEdit("Gate Camera 1")
        self.combo_man_mfg = QComboBox()
        self.combo_man_mfg.addItems(["Generic ONVIF", "Hikvision", "Dahua", "CP PLUS", "Generic RTSP"])
        self.txt_man_ip = QLineEdit("192.168.1.100")
        self.txt_man_onvif_port = QLineEdit("80")
        self.txt_man_rtsp_url = QLineEdit("rtsp://admin:pass@192.168.1.100:554/Streaming/Channels/101")
        self.txt_man_user = QLineEdit("admin")
        self.txt_man_pass = QLineEdit()
        self.txt_man_pass.setEchoMode(QLineEdit.Password)

        f_layout.addWidget(QLabel("Camera Name:"))
        f_layout.addWidget(self.txt_man_name)
        f_layout.addWidget(QLabel("Manufacturer:"))
        f_layout.addWidget(self.combo_man_mfg)
        f_layout.addWidget(QLabel("IP Address:"))
        f_layout.addWidget(self.txt_man_ip)
        f_layout.addWidget(QLabel("RTSP Stream URL:"))
        f_layout.addWidget(self.txt_man_rtsp_url)
        f_layout.addWidget(QLabel("Username:"))
        f_layout.addWidget(self.txt_man_user)
        f_layout.addWidget(QLabel("Password (Encrypted before storage):"))
        f_layout.addWidget(self.txt_man_pass)

        btn_save_man = QPushButton("Register Camera")
        btn_save_man.setStyleSheet("background-color: #238636; color: #ffffff; margin-top: 10px;")
        btn_save_man.clicked.connect(self._save_manual_camera)
        f_layout.addWidget(btn_save_man)

        manual_layout.addWidget(form_frame)
        manual_layout.addStretch()
        tabs.addTab(tab_manual, "Manual Camera Addition")

        layout.addWidget(tabs)

    def _start_ws_discovery(self) -> None:
        self.btn_ws.setEnabled(False)
        self.table.setRowCount(0)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate

        self.worker = DiscoveryWorkerThread(mode="WS")
        self.worker.discovery_finished.connect(self._on_discovery_done)
        self.worker.start()

    def _start_subnet_scan(self) -> None:
        cidr = self.txt_subnet.text().strip()
        self.btn_subnet.setEnabled(False)
        self.table.setRowCount(0)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.worker = DiscoveryWorkerThread(mode="SUBNET", subnet_cidr=cidr)
        self.worker.progress_updated.connect(lambda cur, tot: self.progress_bar.setValue(int(cur / tot * 100)) if tot > 0 else 0)
        self.worker.discovery_finished.connect(self._on_discovery_done)
        self.worker.start()

    def _on_discovery_done(self, results: List[DiscoveredCamera]) -> None:
        self.btn_ws.setEnabled(True)
        self.btn_subnet.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.discovered_cams = results

        self.table.setRowCount(len(results))
        for row, cam in enumerate(results):
            self.table.setItem(row, 0, QTableWidgetItem(cam.ip_address))
            self.table.setItem(row, 1, QTableWidgetItem(cam.mac_address))
            self.table.setItem(row, 2, QTableWidgetItem(cam.manufacturer))
            self.table.setItem(row, 3, QTableWidgetItem(cam.model))
            self.table.setItem(row, 4, QTableWidgetItem(str(cam.onvif_port)))
            self.table.setItem(row, 5, QTableWidgetItem(cam.status))

    def _add_selected_camera(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "Selection Required", "Please select a discovered camera from the table.")
            return

        idx = selected_rows[0].row()
        cam = self.discovered_cams[idx]

        # Register in database with encrypted password
        with db_manager.get_session() as session:
            dev = Device(
                name=f"{cam.manufacturer} {cam.model}",
                device_type="CAMERA",
                manufacturer=cam.manufacturer,
                ip_address=cam.ip_address,
                port=cam.onvif_port,
                rtsp_port=cam.rtsp_port,
                mac_address=cam.mac_address,
                is_online=True,
            )
            session.add(dev)
            session.flush()

            # Channel 1
            ch = DeviceChannel(device_id=dev.id, channel_number=1, name=f"{dev.name} Ch 1")
            session.add(ch)
            session.flush()

            # Default RTSP Stream Profile
            rtsp_url = f"rtsp://{cam.ip_address}:{cam.rtsp_port}/live"
            prof = StreamProfile(channel_id=ch.id, profile_type="MAIN", rtsp_url=rtsp_url)
            session.add(prof)

            # Encrypted credential placeholder
            cred = DeviceCredential(
                device_id=dev.id,
                username="admin",
                encrypted_password=credential_vault.encrypt_password("admin123"),
                auth_type="DIGEST",
            )
            session.add(cred)

        QMessageBox.information(self, "Camera Added", f"Camera {cam.ip_address} successfully added to database!")
        self.camera_registered.emit(dev.id)
        self.accept()

    def _save_manual_camera(self) -> None:
        name = self.txt_man_name.text().strip()
        ip = self.txt_man_ip.text().strip()
        mfg = self.combo_man_mfg.currentText()
        rtsp_url = self.txt_man_rtsp_url.text().strip()
        user = self.txt_man_user.text().strip()
        pwd = self.txt_man_pass.text()

        if not name or not ip or not rtsp_url:
            QMessageBox.warning(self, "Missing Fields", "Please provide Camera Name, IP Address, and RTSP URL.")
            return

        with db_manager.get_session() as session:
            dev = Device(
                name=name,
                device_type="CAMERA",
                manufacturer=mfg,
                ip_address=ip,
                port=80,
                rtsp_port=554,
                is_online=True,
            )
            session.add(dev)
            session.flush()

            ch = DeviceChannel(device_id=dev.id, channel_number=1, name=f"{name} Ch 1")
            session.add(ch)
            session.flush()

            prof = StreamProfile(channel_id=ch.id, profile_type="MAIN", rtsp_url=rtsp_url)
            session.add(prof)

            if pwd:
                cred = DeviceCredential(
                    device_id=dev.id,
                    username=user,
                    encrypted_password=credential_vault.encrypt_password(pwd),
                    auth_type="DIGEST",
                )
                session.add(cred)

        QMessageBox.information(self, "Success", f"Camera '{name}' registered successfully.")
        self.camera_registered.emit(dev.id)
        self.accept()
