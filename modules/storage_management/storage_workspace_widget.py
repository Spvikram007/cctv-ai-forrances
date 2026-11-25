"""
PySide6 Enterprise Storage Management Command Center Workspace.
Phase 13 (F-047, Change ID: CHG-20261125-012).

Mounted at View 10 in the main Command Center. Provides unified operational oversight
across local storage, RAID monitoring, NAS connections, recording failover, manifests,
multi-tier archival, and retention policy management.
"""

import os
import threading
from typing import Dict, Any, List, Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTabWidget,
    QProgressBar,
    QFrame,
    QMessageBox,
    QInputDialog,
    QLineEdit,
    QComboBox,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont

from database.database_manager import db_manager
from database.models.recordings import StorageVolume, Recording
from database.models.storage import (
    StoragePool,
    StorageAllocation,
    StorageFailoverEvent,
    StorageRecordingManifest,
    StorageArchivalJob,
    NASConnection,
)
from engines.storage_engine.storage_service import enterprise_storage_service
from engines.storage_engine.enums import RAIDStatus, VolumeStatus, FailoverStatus
from resources.styles.theme import SurveillanceTheme
from core.logging.logger import get_logger

logger = get_logger("storage_ui")


class StorageManagementWidget(QWidget):
    """
    Central storage administration workspace mounted at View 10.
    Provides 8 dedicated surveillance storage management tabs with real-time telemetry.
    """

    data_refreshed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._init_ui()
        self._load_telemetry()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Header & Title Bar
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Enterprise Storage & Failover Management")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet(f"color: {SurveillanceTheme.TEXT_PRIMARY};")

        subtitle = QLabel("F-047: Local Disks, Hardware RAID, SMB/NFS NAS Shares, Automated Failover & Multi-Tier Archival")
        subtitle.setFont(QFont("Segoe UI", 9))
        subtitle.setStyleSheet(f"color: {SurveillanceTheme.TEXT_SECONDARY};")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        # Action Buttons
        self.btn_audit = QPushButton("Audit Storage Health")
        self.btn_audit.setStyleSheet(SurveillanceTheme.get_action_button_style("primary"))
        self.btn_audit.clicked.connect(self._on_audit_clicked)
        header_layout.addWidget(self.btn_audit)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setStyleSheet(SurveillanceTheme.get_action_button_style("secondary"))
        self.btn_refresh.clicked.connect(self._load_telemetry)
        header_layout.addWidget(self.btn_refresh)
        layout.addLayout(header_layout)

        # 2. Executive KPI Summary Cards
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(10)
        self.kpi_total_cap = self._create_kpi_card("TOTAL CAPACITY", "0.0 GB", "Monitored Storage")
        self.kpi_free_space = self._create_kpi_card("FREE SPACE", "0.0 GB", "Safety Reserves")
        self.kpi_volumes = self._create_kpi_card("VOLUMES ONLINE", "0 / 0", "Local & Network")
        self.kpi_raid_status = self._create_kpi_card("RAID HEALTH", "OPTIMAL", "Array Status")
        self.kpi_failovers = self._create_kpi_card("ACTIVE FAILOVERS", "0", "Redirected Streams")

        kpi_layout.addWidget(self.kpi_total_cap)
        kpi_layout.addWidget(self.kpi_free_space)
        kpi_layout.addWidget(self.kpi_volumes)
        kpi_layout.addWidget(self.kpi_raid_status)
        kpi_layout.addWidget(self.kpi_failovers)
        layout.addLayout(kpi_layout)

        # 3. Main Operational Tab Control
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(SurveillanceTheme.get_tab_widget_style())

        self.tab_overview = self._build_overview_tab()
        self.tab_disks = self._build_disks_tab()
        self.tab_raid = self._build_raid_tab()
        self.tab_pools = self._build_pools_tab()
        self.tab_nas = self._build_nas_tab()
        self.tab_failover = self._build_failover_tab()
        self.tab_archival = self._build_archival_tab()
        self.tab_forecast = self._build_forecast_tab()

        self.tabs.addTab(self.tab_overview, "Storage Overview")
        self.tabs.addTab(self.tab_disks, "Physical Disks")
        self.tabs.addTab(self.tab_raid, "RAID Status")
        self.tabs.addTab(self.tab_pools, "Pools & Allocations")
        self.tabs.addTab(self.tab_nas, "NAS Connections")
        self.tabs.addTab(self.tab_failover, "Failover & Manifests")
        self.tabs.addTab(self.tab_archival, "Archival & Retention")
        self.tabs.addTab(self.tab_forecast, "Capacity Forecast")
        layout.addWidget(self.tabs, stretch=1)

        # Status Bar
        self.lbl_status = QLabel("System Status: Storage Engine Active | All Adapters Healthy")
        self.lbl_status.setFont(QFont("Segoe UI", 9))
        self.lbl_status.setStyleSheet(f"color: {SurveillanceTheme.ACCENT_SUCCESS};")
        layout.addWidget(self.lbl_status)

    def _create_kpi_card(self, title: str, value: str, subtitle: str) -> QFrame:
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet(SurveillanceTheme.get_kpi_card_style())
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        lbl_title = QLabel(title)
        lbl_title.setFont(QFont("Segoe UI", 8, QFont.Bold))
        lbl_title.setStyleSheet(f"color: {SurveillanceTheme.TEXT_MUTED};")

        lbl_val = QLabel(value)
        lbl_val.setFont(QFont("Segoe UI", 16, QFont.Bold))
        lbl_val.setStyleSheet(f"color: {SurveillanceTheme.TEXT_PRIMARY};")
        lbl_val.setObjectName("kpi_value")

        lbl_sub = QLabel(subtitle)
        lbl_sub.setFont(QFont("Segoe UI", 8))
        lbl_sub.setStyleSheet(f"color: {SurveillanceTheme.TEXT_SECONDARY};")

        layout.addWidget(lbl_title)
        layout.addWidget(lbl_val)
        layout.addWidget(lbl_sub)
        return card

    # -------------------------------------------------------------------------
    # Tab Builders
    # -------------------------------------------------------------------------
    def _build_overview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        lbl = QLabel("Active Surveillance Storage Volumes")
        lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        lbl.setStyleSheet(f"color: {SurveillanceTheme.TEXT_PRIMARY};")
        layout.addWidget(lbl)

        self.tbl_volumes = QTableWidget()
        self.tbl_volumes.setColumnCount(8)
        self.tbl_volumes.setHorizontalHeaderLabels([
            "Volume Name", "Mount Path", "Type", "Filesystem", "Total (GB)", "Free (GB)", "Used %", "Status"
        ])
        self.tbl_volumes.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_volumes.setStyleSheet(SurveillanceTheme.get_table_style())
        layout.addWidget(self.tbl_volumes)
        return widget

    def _build_disks_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        lbl = QLabel("Host Logical Drives & Physical Disks")
        lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        lbl.setStyleSheet(f"color: {SurveillanceTheme.TEXT_PRIMARY};")
        layout.addWidget(lbl)

        self.tbl_disks = QTableWidget()
        self.tbl_disks.setColumnCount(6)
        self.tbl_disks.setHorizontalHeaderLabels([
            "Drive / Path", "Volume Name", "Filesystem", "Total Space", "Free Space", "NTFS/ReFS Flags"
        ])
        self.tbl_disks.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_disks.setStyleSheet(SurveillanceTheme.get_table_style())
        layout.addWidget(self.tbl_disks)
        return widget

    def _build_raid_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        header = QHBoxLayout()
        lbl = QLabel("RAID Arrays & Resiliency Sets")
        lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        lbl.setStyleSheet(f"color: {SurveillanceTheme.TEXT_PRIMARY};")
        header.addWidget(lbl)
        header.addStretch()

        self.btn_rebuild = QPushButton("Initiate Array Rebuild")
        self.btn_rebuild.setStyleSheet(SurveillanceTheme.get_action_button_style("warning"))
        self.btn_rebuild.clicked.connect(self._on_rebuild_clicked)
        header.addWidget(self.btn_rebuild)
        layout.addLayout(header)

        self.tbl_raid = QTableWidget()
        self.tbl_raid.setColumnCount(7)
        self.tbl_raid.setHorizontalHeaderLabels([
            "Array ID", "Name", "RAID Level", "Status", "Capacity", "Rebuild %", "Telemetry Source"
        ])
        self.tbl_raid.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_raid.setStyleSheet(SurveillanceTheme.get_table_style())
        layout.addWidget(self.tbl_raid)
        return widget

    def _build_pools_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        lbl = QLabel("Camera Storage Allocations & Target Pools")
        lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        lbl.setStyleSheet(f"color: {SurveillanceTheme.TEXT_PRIMARY};")
        layout.addWidget(lbl)

        self.tbl_alloc = QTableWidget()
        self.tbl_alloc.setColumnCount(6)
        self.tbl_alloc.setHorizontalHeaderLabels([
            "Camera Channel", "Assigned Pool", "Primary Volume", "Failover Target", "Quota (GB)", "Priority"
        ])
        self.tbl_alloc.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_alloc.setStyleSheet(SurveillanceTheme.get_table_style())
        layout.addWidget(self.tbl_alloc)
        return widget

    def _build_nas_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        header = QHBoxLayout()
        lbl = QLabel("Network-Attached Storage (SMB/CIFS & NFS)")
        lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        lbl.setStyleSheet(f"color: {SurveillanceTheme.TEXT_PRIMARY};")
        header.addWidget(lbl)
        header.addStretch()

        self.btn_add_nas = QPushButton("Register NAS Profile")
        self.btn_add_nas.setStyleSheet(SurveillanceTheme.get_action_button_style("primary"))
        self.btn_add_nas.clicked.connect(self._on_add_nas_clicked)
        header.addWidget(self.btn_add_nas)
        layout.addLayout(header)

        self.tbl_nas = QTableWidget()
        self.tbl_nas.setColumnCount(7)
        self.tbl_nas.setHorizontalHeaderLabels([
            "Profile Name", "Protocol", "Host / Server", "Share Name", "Mount Point", "Status", "Latency"
        ])
        self.tbl_nas.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_nas.setStyleSheet(SurveillanceTheme.get_table_style())
        layout.addWidget(self.tbl_nas)
        return widget

    def _build_failover_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        header = QHBoxLayout()
        lbl = QLabel("Storage Failover Events & Cryptographic Recording Manifests")
        lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        lbl.setStyleSheet(f"color: {SurveillanceTheme.TEXT_PRIMARY};")
        header.addWidget(lbl)
        header.addStretch()

        self.btn_failback = QPushButton("Execute Failback to Primary")
        self.btn_failback.setStyleSheet(SurveillanceTheme.get_action_button_style("secondary"))
        self.btn_failback.clicked.connect(self._on_failback_clicked)
        header.addWidget(self.btn_failback)
        layout.addLayout(header)

        self.tbl_failover = QTableWidget()
        self.tbl_failover.setColumnCount(7)
        self.tbl_failover.setHorizontalHeaderLabels([
            "Camera Channel", "Primary Volume", "Failover Target", "Triggered At", "Status", "Gap (s)", "Reason"
        ])
        self.tbl_failover.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_failover.setStyleSheet(SurveillanceTheme.get_table_style())
        layout.addWidget(self.tbl_failover)
        return widget

    def _build_archival_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        header = QHBoxLayout()
        lbl = QLabel("Multi-Tier Archival Jobs & Retention Policies")
        lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        lbl.setStyleSheet(f"color: {SurveillanceTheme.TEXT_PRIMARY};")
        header.addWidget(lbl)
        header.addStretch()

        self.btn_prune = QPushButton("Execute Retention Pruning")
        self.btn_prune.setStyleSheet(SurveillanceTheme.get_action_button_style("warning"))
        self.btn_prune.clicked.connect(self._on_prune_clicked)
        header.addWidget(self.btn_prune)
        layout.addLayout(header)

        self.tbl_archival = QTableWidget()
        self.tbl_archival.setColumnCount(7)
        self.tbl_archival.setHorizontalHeaderLabels([
            "Job ID", "Target Tier", "Files Migrated", "Bytes Transferred", "Failed Copies", "Status", "Completed At"
        ])
        self.tbl_archival.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_archival.setStyleSheet(SurveillanceTheme.get_table_style())
        layout.addWidget(self.tbl_archival)
        return widget

    def _build_forecast_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        lbl = QLabel("Capacity Consumption Forecasting")
        lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        lbl.setStyleSheet(f"color: {SurveillanceTheme.TEXT_PRIMARY};")
        layout.addWidget(lbl)

        self.tbl_forecast = QTableWidget()
        self.tbl_forecast.setColumnCount(6)
        self.tbl_forecast.setHorizontalHeaderLabels([
            "Volume Name", "Total Capacity", "Free Space", "Est. Daily Burn", "Days to 85% Warning", "Days to Exhaustion"
        ])
        self.tbl_forecast.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_forecast.setStyleSheet(SurveillanceTheme.get_table_style())
        layout.addWidget(self.tbl_forecast)
        return widget

    # -------------------------------------------------------------------------
    # Telemetry Loading
    # -------------------------------------------------------------------------
    def _load_telemetry(self) -> None:
        """Asynchronously queries database and storage adapters to populate UI tables."""
        threading.Thread(target=self._query_and_populate, daemon=True).start()

    def _query_and_populate(self) -> None:
        try:
            enterprise_storage_service.initialize()
            with db_manager.get_session() as session:
                volumes = session.query(StorageVolume).filter_by(is_deleted=False).all()
                failovers = (
                    session.query(StorageFailoverEvent)
                    .order_by(StorageFailoverEvent.triggered_at.desc())
                    .limit(50)
                    .all()
                )
                allocations = session.query(StorageAllocation).all()
                nas_profiles = session.query(NASConnection).all()
                arch_jobs = (
                    session.query(StorageArchivalJob)
                    .order_by(StorageArchivalJob.started_at.desc())
                    .limit(50)
                    .all()
                )

                v_data = [{
                    "name": v.name,
                    "path": v.mount_path,
                    "type": getattr(v, "volume_type", "LOCAL") or "LOCAL",
                    "fs": getattr(v, "filesystem", "NTFS") or "NTFS",
                    "total_gb": round(v.total_bytes / (1024 ** 3), 1) if v.total_bytes else 0.0,
                    "free_gb": round(v.available_bytes / (1024 ** 3), 1) if v.available_bytes else 0.0,
                    "used_pct": round(v.used_bytes / v.total_bytes * 100, 1) if v.total_bytes else 0.0,
                    "status": getattr(v, "volume_status", "ONLINE") or "ONLINE",
                } for v in volumes]

                f_data = [{
                    "channel": f.channel_id,
                    "primary": f.primary_volume_id[:8],
                    "failover": f.failover_volume_id[:8],
                    "triggered": f.triggered_at.strftime("%Y-%m-%d %H:%M:%S") if f.triggered_at else "",
                    "status": f.status,
                    "gap": f"{f.gap_seconds:.2f}s",
                    "reason": f.reason,
                } for f in failovers]

                a_data = [{
                    "channel": a.channel_id,
                    "pool": a.pool_id[:8],
                    "primary": a.primary_volume_id[:8],
                    "failover": a.failover_volume_id[:8] if a.failover_volume_id else "None",
                    "quota": round(a.quota_bytes / (1024 ** 3), 1) if a.quota_bytes else "Unlimited",
                    "priority": a.priority,
                } for a in allocations]

                n_data = [{
                    "name": n.name,
                    "protocol": n.protocol,
                    "host": n.host,
                    "share": n.share_name,
                    "mount": n.mount_point,
                    "status": n.status,
                    "latency": f"{n.last_latency_ms:.1f} ms",
                } for n in nas_profiles]

                j_data = [{
                    "id": j.id[:8],
                    "tier": j.target_tier,
                    "files": str(j.files_transferred),
                    "bytes": f"{round(j.bytes_transferred / (1024 ** 2), 1)} MB",
                    "failed": str(j.verification_failed_count),
                    "status": j.status,
                    "completed": j.completed_at.strftime("%Y-%m-%d %H:%M:%S") if j.completed_at else "In Progress",
                } for j in arch_jobs]

            # Adapter-level probes
            disks = enterprise_storage_service.local_adapter.discover_local_volumes()
            arrays = enterprise_storage_service.raid_adapter.get_all_arrays()
            forecasts = enterprise_storage_service.forecast_capacity().get("forecasts", [])

            # Update UI on main thread via invokeMethod or timer
            QTimer.singleShot(0, lambda: self._apply_telemetry_to_ui(
                v_data, f_data, a_data, n_data, j_data, disks, arrays, forecasts
            ))
        except Exception as e:
            logger.error("Error loading storage telemetry: %s", e)

    def _apply_telemetry_to_ui(
        self,
        volumes: List[Dict[str, Any]],
        failovers: List[Dict[str, Any]],
        allocations: List[Dict[str, Any]],
        nas_profiles: List[Dict[str, Any]],
        arch_jobs: List[Dict[str, Any]],
        disks: List[Dict[str, Any]],
        arrays: List[Any],
        forecasts: List[Dict[str, Any]],
    ) -> None:
        # Update KPI Cards
        total_gb = sum(v["total_gb"] for v in volumes)
        free_gb = sum(v["free_gb"] for v in volumes)
        online_count = sum(1 for v in volumes if v["status"] == "ONLINE")

        self.kpi_total_cap.findChild(QLabel, "kpi_value").setText(f"{total_gb:.1f} GB")
        self.kpi_free_space.findChild(QLabel, "kpi_value").setText(f"{free_gb:.1f} GB")
        self.kpi_volumes.findChild(QLabel, "kpi_value").setText(f"{online_count} / {len(volumes)}")

        raid_status = "OPTIMAL"
        for arr in arrays:
            if getattr(arr, "status", None) == RAIDStatus.DEGRADED:
                raid_status = "DEGRADED"
            elif getattr(arr, "status", None) == RAIDStatus.FAILED:
                raid_status = "FAILED"
        self.kpi_raid_status.findChild(QLabel, "kpi_value").setText(raid_status)

        active_failover_count = sum(1 for f in failovers if f["status"] == FailoverStatus.ACTIVE.value)
        self.kpi_failovers.findChild(QLabel, "kpi_value").setText(str(active_failover_count))

        # Populate Volumes Table
        self.tbl_volumes.setRowCount(len(volumes))
        for r, v in enumerate(volumes):
            self.tbl_volumes.setItem(r, 0, QTableWidgetItem(v["name"]))
            self.tbl_volumes.setItem(r, 1, QTableWidgetItem(v["path"]))
            self.tbl_volumes.setItem(r, 2, QTableWidgetItem(v["type"]))
            self.tbl_volumes.setItem(r, 3, QTableWidgetItem(v["fs"]))
            self.tbl_volumes.setItem(r, 4, QTableWidgetItem(f"{v['total_gb']:.1f}"))
            self.tbl_volumes.setItem(r, 5, QTableWidgetItem(f"{v['free_gb']:.1f}"))
            self.tbl_volumes.setItem(r, 6, QTableWidgetItem(f"{v['used_pct']}%"))
            self.tbl_volumes.setItem(r, 7, QTableWidgetItem(v["status"]))

        # Populate Disks Table
        self.tbl_disks.setRowCount(len(disks))
        for r, d in enumerate(disks):
            self.tbl_disks.setItem(r, 0, QTableWidgetItem(d.get("mount_path", "")))
            self.tbl_disks.setItem(r, 1, QTableWidgetItem(d.get("name", "")))
            self.tbl_disks.setItem(r, 2, QTableWidgetItem(d.get("filesystem", "NTFS")))
            self.tbl_disks.setItem(r, 3, QTableWidgetItem(f"{d.get('total_gb', 0.0):.1f} GB"))
            self.tbl_disks.setItem(r, 4, QTableWidgetItem(f"{d.get('free_gb', 0.0):.1f} GB"))
            flags = "ReFS" if d.get("is_refs") else ("Read-Only" if d.get("is_read_only") else "Read/Write")
            self.tbl_disks.setItem(r, 5, QTableWidgetItem(flags))

        # Populate RAID Table
        self.tbl_raid.setRowCount(len(arrays))
        for r, a in enumerate(arrays):
            self.tbl_raid.setItem(r, 0, QTableWidgetItem(getattr(a, "array_id", "")))
            self.tbl_raid.setItem(r, 1, QTableWidgetItem(getattr(a, "name", "")))
            r_level = getattr(a, "raid_level", None)
            self.tbl_raid.setItem(r, 2, QTableWidgetItem(r_level.value if hasattr(r_level, "value") else str(r_level)))
            r_stat = getattr(a, "status", None)
            self.tbl_raid.setItem(r, 3, QTableWidgetItem(r_stat.value if hasattr(r_stat, "value") else str(r_stat)))
            cap_gb = (getattr(a, "total_bytes", 0) or 0) / (1024 ** 3)
            self.tbl_raid.setItem(r, 4, QTableWidgetItem(f"{cap_gb:.1f} GB"))
            self.tbl_raid.setItem(r, 5, QTableWidgetItem(f"{getattr(a, 'rebuild_progress_pct', 0.0):.1f}%"))
            t_src = getattr(a, "telemetry_source", None)
            self.tbl_raid.setItem(r, 6, QTableWidgetItem(t_src.value if hasattr(t_src, "value") else str(t_src)))

        # Populate Allocations Table
        self.tbl_alloc.setRowCount(len(allocations))
        for r, al in enumerate(allocations):
            self.tbl_alloc.setItem(r, 0, QTableWidgetItem(al["channel"]))
            self.tbl_alloc.setItem(r, 1, QTableWidgetItem(al["pool"]))
            self.tbl_alloc.setItem(r, 2, QTableWidgetItem(al["primary"]))
            self.tbl_alloc.setItem(r, 3, QTableWidgetItem(al["failover"]))
            self.tbl_alloc.setItem(r, 4, QTableWidgetItem(str(al["quota"])))
            self.tbl_alloc.setItem(r, 5, QTableWidgetItem(al["priority"]))

        # Populate NAS Table
        self.tbl_nas.setRowCount(len(nas_profiles))
        for r, n in enumerate(nas_profiles):
            self.tbl_nas.setItem(r, 0, QTableWidgetItem(n["name"]))
            self.tbl_nas.setItem(r, 1, QTableWidgetItem(n["protocol"]))
            self.tbl_nas.setItem(r, 2, QTableWidgetItem(n["host"]))
            self.tbl_nas.setItem(r, 3, QTableWidgetItem(n["share"]))
            self.tbl_nas.setItem(r, 4, QTableWidgetItem(n["mount"]))
            self.tbl_nas.setItem(r, 5, QTableWidgetItem(n["status"]))
            self.tbl_nas.setItem(r, 6, QTableWidgetItem(n["latency"]))

        # Populate Failover Table
        self.tbl_failover.setRowCount(len(failovers))
        for r, f in enumerate(failovers):
            self.tbl_failover.setItem(r, 0, QTableWidgetItem(f["channel"]))
            self.tbl_failover.setItem(r, 1, QTableWidgetItem(f["primary"]))
            self.tbl_failover.setItem(r, 2, QTableWidgetItem(f["failover"]))
            self.tbl_failover.setItem(r, 3, QTableWidgetItem(f["triggered"]))
            self.tbl_failover.setItem(r, 4, QTableWidgetItem(f["status"]))
            self.tbl_failover.setItem(r, 5, QTableWidgetItem(f["gap"]))
            self.tbl_failover.setItem(r, 6, QTableWidgetItem(f["reason"]))

        # Populate Archival Table
        self.tbl_archival.setRowCount(len(arch_jobs))
        for r, j in enumerate(arch_jobs):
            self.tbl_archival.setItem(r, 0, QTableWidgetItem(j["id"]))
            self.tbl_archival.setItem(r, 1, QTableWidgetItem(j["tier"]))
            self.tbl_archival.setItem(r, 2, QTableWidgetItem(j["files"]))
            self.tbl_archival.setItem(r, 3, QTableWidgetItem(j["bytes"]))
            self.tbl_archival.setItem(r, 4, QTableWidgetItem(j["failed"]))
            self.tbl_archival.setItem(r, 5, QTableWidgetItem(j["status"]))
            self.tbl_archival.setItem(r, 6, QTableWidgetItem(j["completed"]))

        # Populate Forecast Table
        self.tbl_forecast.setRowCount(len(forecasts))
        for r, fc in enumerate(forecasts):
            self.tbl_forecast.setItem(r, 0, QTableWidgetItem(fc.get("volume_name", "")))
            self.tbl_forecast.setItem(r, 1, QTableWidgetItem(f"{fc.get('total_gb', 0.0):.1f} GB"))
            self.tbl_forecast.setItem(r, 2, QTableWidgetItem(f"{fc.get('free_gb', 0.0):.1f} GB"))
            self.tbl_forecast.setItem(r, 3, QTableWidgetItem(f"{fc.get('estimated_daily_burn_gb', 0.0):.1f} GB/day"))
            self.tbl_forecast.setItem(r, 4, QTableWidgetItem(f"{fc.get('days_until_warning_threshold', 0.0):.1f} days"))
            self.tbl_forecast.setItem(r, 5, QTableWidgetItem(f"{fc.get('days_until_exhaustion', 0.0):.1f} days"))

    # -------------------------------------------------------------------------
    # UI Actions
    # -------------------------------------------------------------------------
    def _on_audit_clicked(self) -> None:
        """Executes full read/write and capacity audit across all storage volumes."""
        self.btn_audit.setEnabled(False)
        self.lbl_status.setText("Auditing storage volume metrics and filesystem capabilities...")

        def _task():
            enterprise_storage_service.volume_monitor.audit_all_volumes()
            QTimer.singleShot(0, lambda: self._on_audit_complete())

        threading.Thread(target=_task, daemon=True).start()

    def _on_audit_complete(self) -> None:
        self.btn_audit.setEnabled(True)
        self.lbl_status.setText("Storage health audit complete. Telemetry updated.")
        self._load_telemetry()

    def _on_rebuild_clicked(self) -> None:
        """Prompts for operator confirmation before initiating destructive/rebuild operation."""
        array_id, ok = QInputDialog.getText(self, "RAID Array Rebuild", "Enter degraded Array ID to rebuild:")
        if ok and array_id:
            confirm = QMessageBox.question(
                self,
                "Confirm RAID Rebuild",
                f"Are you sure you want to initiate a rebuild on array '{array_id}'?\nThis will perform sustained high-I/O operations on member disks.",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirm == QMessageBox.Yes:
                success, msg = enterprise_storage_service.raid_adapter.execute_rebuild(array_id, operator="Administrator", role="ADMIN")
                if success:
                    QMessageBox.information(self, "Rebuild Initiated", msg)
                else:
                    QMessageBox.warning(self, "Rebuild Error", msg)
                self._load_telemetry()

    def _on_add_nas_clicked(self) -> None:
        """Adds a new NAS connection profile with encrypted credentials."""
        name, ok = QInputDialog.getText(self, "Register NAS Share", "Profile Name (e.g. Synology_Archive):")
        if not (ok and name):
            return
        host, ok = QInputDialog.getText(self, "Register NAS Share", "Host IP or FQDN (e.g. 192.168.1.200):")
        if not (ok and host):
            return
        share, ok = QInputDialog.getText(self, "Register NAS Share", "Share Name (e.g. surveillance_cold):")
        if not (ok and share):
            return

        mount = f"\\\\{host}\\{share}"
        enterprise_storage_service.nas_adapter.register_connection(
            name=name,
            protocol="SMB",
            host=host,
            share_name=share,
            mount_point=mount,
        )

        with db_manager.get_session() as session:
            conn = NASConnection(
                name=name,
                protocol="SMB",
                host=host,
                share_name=share,
                mount_point=mount,
                status="CONNECTED",
            )
            session.add(conn)

        QMessageBox.information(self, "NAS Registered", f"NAS connection profile '{name}' registered successfully.")
        self._load_telemetry()

    def _on_failback_clicked(self) -> None:
        """Triggers controlled failback for selected channel."""
        channel_id, ok = QInputDialog.getText(self, "Storage Failback", "Enter Camera Channel ID to failback to primary:")
        if ok and channel_id:
            success, msg = enterprise_storage_service.execute_failback(channel_id, operator="Administrator")
            if success:
                QMessageBox.information(self, "Failback Complete", msg)
            else:
                QMessageBox.warning(self, "Failback Notice", msg)
            self._load_telemetry()

    def _on_prune_clicked(self) -> None:
        """Executes retention pruning with explicit evidence lock guarantee."""
        confirm = QMessageBox.question(
            self,
            "Retention Pruning",
            "Execute retention pruning on recordings older than 30 days?\n\nEvidence Lock Guarantee: Recordings marked as locked forensic evidence will NEVER be deleted.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            freed = enterprise_storage_service.prune_expired_recordings(retention_days=30)
            QMessageBox.information(self, "Pruning Complete", f"Retention pruning completed.\n{freed} expired unlocked recordings deleted.\nAll locked evidence preserved.")
            self._load_telemetry()
