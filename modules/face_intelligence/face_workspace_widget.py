"""
Authorized Face Intelligence and Biometric Privacy Workspace.
Implements authorized identity enrollment, biometric quality checks,
candidate match review with human verification, watchlist administration, and audit logs.
"""

import time
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QGroupBox,
    QFormLayout,
    QTabWidget,
    QFileDialog,
    QMessageBox,
)

import cv2
import numpy as np

from database.database_manager import db_manager
from database.models.biometrics import (
    FaceIdentity,
    FaceMatchEvent,
    BiometricAuditLog,
)
from engines.face_engine.face_service import face_intelligence_service
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("face_workspace")


class FaceWorkspaceWidget(QWidget):
    """
    Authorized Face Intelligence Workspace with Biometric Privacy Controls.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._init_ui()
        self._load_candidate_matches()
        self._load_identities()
        self._load_audit_logs()
        self._subscribe_events()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header with Privacy Notice Alert
        header_layout = QHBoxLayout()
        lbl_title = QLabel("AUTHORIZED FACE INTELLIGENCE & BIOMETRIC VERIFICATION")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #58a6ff;")
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()

        lbl_privacy = QLabel("🔒 Privacy Shield: AES-256-GCM Encrypted | Authorized Identities Only")
        lbl_privacy.setStyleSheet("color: #3fb950; font-size: 12px; font-weight: 600;")
        header_layout.addWidget(lbl_privacy)
        main_layout.addLayout(header_layout)

        # Main Workspace Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab { background: #161b22; color: #8b949e; padding: 8px 18px; border: 1px solid #30363d; font-weight: 600; }
            QTabBar::tab:selected { background: #21262d; color: #58a6ff; }
        """)

        # Tab 1: Candidate Matches & Verification
        self.tab_matches = self._create_matches_tab()
        self.tabs.addTab(self.tab_matches, "Candidate Matches & Review")

        # Tab 2: Identity Enrollment
        self.tab_enroll = self._create_enrollment_tab()
        self.tabs.addTab(self.tab_enroll, "Authorized Enrollment")

        # Tab 3: Catalog & Watchlists
        self.tab_catalog = self._create_catalog_tab()
        self.tabs.addTab(self.tab_catalog, "Identity Catalog & Watchlists")

        # Tab 4: Biometric Audit Logs
        self.tab_audit = self._create_audit_tab()
        self.tabs.addTab(self.tab_audit, "Biometric Audit Trail")

        main_layout.addWidget(self.tabs, stretch=1)

    def _create_matches_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        notice_box = QLabel("⚠️ IMPORTANT: Similarity scores are mathematical correlations, NOT proof of identity. Human verification required.")
        notice_box.setStyleSheet("background-color: #2b1d0c; border: 1px solid #bb8009; color: #d29922; padding: 8px; border-radius: 4px; font-size: 12px;")
        layout.addWidget(notice_box)

        splitter = QSplitter(Qt.Horizontal)

        # Matches Table
        self.tbl_matches = QTableWidget(0, 7)
        self.tbl_matches.setHorizontalHeaderLabels([
            "Timestamp", "Camera", "Candidate Name", "Watchlist Category", "Similarity", "Verification", "Actions"
        ])
        self.tbl_matches.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_matches.setStyleSheet("background-color: #0d1117; color: #c9d1d9; gridline-color: #21262d;")
        splitter.addWidget(self.tbl_matches)

        # Inspector Panel
        inspector = QFrame()
        inspector.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 12px;")
        ins_layout = QVBoxLayout(inspector)

        lbl_ins = QLabel("MATCH INSPECTOR & HUMAN VERIFICATION")
        lbl_ins.setStyleSheet("font-size: 13px; font-weight: bold; color: #58a6ff;")
        ins_layout.addWidget(lbl_ins)

        self.lbl_match_snap = QLabel("Select candidate match to inspect.")
        self.lbl_match_snap.setAlignment(Qt.AlignCenter)
        self.lbl_match_snap.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; min-height: 140px; color: #8b949e;")
        ins_layout.addWidget(self.lbl_match_snap)

        self.lbl_match_details = QLabel("No candidate selected.")
        self.lbl_match_details.setStyleSheet("color: #c9d1d9; font-size: 12px; margin-top: 8px;")
        self.lbl_match_details.setWordWrap(True)
        ins_layout.addWidget(self.lbl_match_details)

        ins_layout.addStretch()
        splitter.addWidget(inspector)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, stretch=1)
        return widget

    def _create_enrollment_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)

        # Left: Enrollment Form
        form_box = QGroupBox("Authorized Identity Enrollment Form")
        form_box.setStyleSheet("QGroupBox { color: #8b949e; font-weight: 600; border: 1px solid #30363d; border-radius: 6px; padding-top: 16px; }")
        form_layout = QFormLayout(form_box)

        self.edit_enroll_name = QLineEdit()
        self.edit_enroll_name.setPlaceholderText("Full Legal Name")
        form_layout.addRow("Full Name:", self.edit_enroll_name)

        self.edit_enroll_code = QLineEdit()
        self.edit_enroll_code.setPlaceholderText("e.g. EMP-10492 or BADGE-551")
        form_layout.addRow("Identity / Badge ID:", self.edit_enroll_code)

        self.combo_enroll_cat = QComboBox()
        self.combo_enroll_cat.addItems(["AUTHORIZED_STAFF", "VIP", "WATCHLIST_ALERT", "CONTRACTOR"])
        form_layout.addRow("Category / List:", self.combo_enroll_cat)

        self.edit_enroll_dept = QLineEdit()
        self.edit_enroll_dept.setPlaceholderText("e.g. Security Operations / Engineering")
        form_layout.addRow("Department:", self.edit_enroll_dept)

        self.edit_enroll_auth_ref = QLineEdit()
        self.edit_enroll_auth_ref.setPlaceholderText("Consent form / Access Authorization Policy #")
        form_layout.addRow("Authorization Ref:", self.edit_enroll_auth_ref)

        btn_select_img = QPushButton("Select Face Image (.jpg, .png)")
        btn_select_img.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; color: #58a6ff; padding: 6px 12px; border-radius: 4px;")
        btn_select_img.clicked.connect(self._select_enrollment_image)
        form_layout.addRow("Face Image:", btn_select_img)

        self.btn_submit_enroll = QPushButton("Submit & Encrypt Biometric Enrollment")
        self.btn_submit_enroll.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 8px 16px; border-radius: 4px; margin-top: 12px;")
        self.btn_submit_enroll.clicked.connect(self._submit_enrollment)
        form_layout.addRow(self.btn_submit_enroll)

        layout.addWidget(form_box, stretch=2)

        # Right: Image & Quality Assessment Preview
        quality_box = QGroupBox("Biometric Quality Assessment")
        quality_box.setStyleSheet("QGroupBox { color: #8b949e; font-weight: 600; border: 1px solid #30363d; border-radius: 6px; padding-top: 16px; }")
        q_layout = QVBoxLayout(quality_box)

        self.lbl_enroll_img_preview = QLabel("No image loaded.")
        self.lbl_enroll_img_preview.setAlignment(Qt.AlignCenter)
        self.lbl_enroll_img_preview.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 4px; min-height: 180px; color: #8b949e;")
        q_layout.addWidget(self.lbl_enroll_img_preview)

        self.lbl_quality_metrics = QLabel("Quality Status: Pending image selection.")
        self.lbl_quality_metrics.setStyleSheet("color: #8b949e; font-size: 12px; margin-top: 8px;")
        self.lbl_quality_metrics.setWordWrap(True)
        q_layout.addWidget(self.lbl_quality_metrics)

        q_layout.addStretch()
        layout.addWidget(quality_box, stretch=1)

        return widget

    def _create_catalog_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        # Toolbar
        bar = QHBoxLayout()
        btn_refresh = QPushButton("Refresh Catalog")
        btn_refresh.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 4px 10px; border-radius: 4px;")
        btn_refresh.clicked.connect(self._load_identities)
        bar.addWidget(btn_refresh)
        bar.addStretch()
        layout.addLayout(bar)

        self.tbl_identities = QTableWidget(0, 6)
        self.tbl_identities.setHorizontalHeaderLabels([
            "Identity Code", "Full Name", "Category", "Department", "Status", "Actions"
        ])
        self.tbl_identities.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_identities.setStyleSheet("background-color: #0d1117; color: #c9d1d9; gridline-color: #21262d;")
        layout.addWidget(self.tbl_identities)

        return widget

    def _create_audit_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        bar = QHBoxLayout()
        lbl_info = QLabel("Immutable Cryptographic Biometric Access & Matching Audit Trail")
        lbl_info.setStyleSheet("color: #8b949e; font-size: 12px;")
        bar.addWidget(lbl_info)
        bar.addStretch()

        btn_refresh = QPushButton("Refresh Audit Logs")
        btn_refresh.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 4px 10px; border-radius: 4px;")
        btn_refresh.clicked.connect(self._load_audit_logs)
        bar.addWidget(btn_refresh)
        layout.addLayout(bar)

        self.tbl_audit = QTableWidget(0, 5)
        self.tbl_audit.setHorizontalHeaderLabels([
            "Timestamp (UTC)", "Action", "Operator / User", "Identity ID", "Details"
        ])
        self.tbl_audit.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_audit.setStyleSheet("background-color: #0d1117; color: #c9d1d9; gridline-color: #21262d;")
        layout.addWidget(self.tbl_audit)

        return widget

    def _subscribe_events(self) -> None:
        bus.subscribe("face.candidate_match", self._on_live_candidate_match)

    def _on_live_candidate_match(self, data: Dict[str, Any]) -> None:
        try:
            row = 0
            self.tbl_matches.insertRow(row)
            dt_str = datetime.fromtimestamp(data.get("timestamp", time.time()), tz=timezone.utc).strftime("%H:%M:%S")
            self.tbl_matches.setItem(row, 0, QTableWidgetItem(dt_str))
            self.tbl_matches.setItem(row, 1, QTableWidgetItem(data.get("channel_id", "")))
            self.tbl_matches.setItem(row, 2, QTableWidgetItem(data.get("candidate_name", "")))
            self.tbl_matches.setItem(row, 3, QTableWidgetItem(data.get("category", "")))

            sim = data.get("similarity", 0.0)
            self.tbl_matches.setItem(row, 4, QTableWidgetItem(f"{sim:.1%}"))

            status_item = QTableWidgetItem("Review Required")
            status_item.setForeground(QColor("#f85149"))
            self.tbl_matches.setItem(row, 5, status_item)

            btn_verify = QPushButton("Verify")
            btn_verify.setStyleSheet("background-color: #1f6feb; color: white; font-size: 11px;")
            self.tbl_matches.setCellWidget(row, 6, btn_verify)
        except RuntimeError:
            pass

    def _load_candidate_matches(self) -> None:
        try:
            with db_manager.get_session() as session:
                matches = session.query(FaceMatchEvent).order_by(FaceMatchEvent.timestamp.desc()).limit(50).all()
                self.tbl_matches.setRowCount(len(matches))
                for idx, m in enumerate(matches):
                    self.tbl_matches.setItem(idx, 0, QTableWidgetItem(m.timestamp.strftime("%Y-%m-%d %H:%M:%S") if m.timestamp else ""))
                    self.tbl_matches.setItem(idx, 1, QTableWidgetItem(m.channel_id))
                    self.tbl_matches.setItem(idx, 2, QTableWidgetItem(m.candidate_name))
                    self.tbl_matches.setItem(idx, 3, QTableWidgetItem(m.category))
                    self.tbl_matches.setItem(idx, 4, QTableWidgetItem(f"{m.similarity_score:.1%}"))

                    status = "Confirmed" if m.is_verified else "Review Required"
                    item_s = QTableWidgetItem(status)
                    item_s.setForeground(QColor("#3fb950" if m.is_verified else "#f85149"))
                    self.tbl_matches.setItem(idx, 5, item_s)

                    if not m.is_verified:
                        btn_v = QPushButton("Verify")
                        btn_v.setStyleSheet("background-color: #238636; color: white; font-size: 11px;")
                        mid = m.id
                        btn_v.clicked.connect(lambda _, ev_id=mid: self._verify_match(ev_id))
                        self.tbl_matches.setCellWidget(idx, 6, btn_v)
        except Exception as e:
            logger.error("Failed to load match events: %s", e)

    def _verify_match(self, event_id: str) -> None:
        face_intelligence_service.verify_match_event(event_id, verified_by_user_id="offline_admin", is_confirmed=True)
        self._load_candidate_matches()
        self._load_audit_logs()

    def _select_enrollment_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Face Image", "", "Image Files (*.jpg *.png *.jpeg)")
        if path:
            img = cv2.imread(path)
            if img is not None:
                self._current_enroll_img = img
                # Quality check
                quality = face_intelligence_service.detector.assess_quality(img)
                rgb = cv2.cvtColor(cv2.resize(img, (140, 140)), cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                q_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
                self.lbl_enroll_img_preview.setPixmap(QPixmap.fromImage(q_img))

                status_color = "#3fb950" if quality.is_acceptable else "#f85149"
                status_text = "APPROVED" if quality.is_acceptable else "REJECTED"
                self.lbl_quality_metrics.setText(
                    f"Status: <b style='color:{status_color}'>{status_text}</b><br>"
                    f"Sharpness: {quality.sharpness_score:.1f}<br>"
                    f"Illumination: {quality.illumination_score:.1f}<br>"
                    f"Overall Quality: {quality.overall_quality:.1%}"
                    + (f"<br><span style='color:#f85149'>Reason: {quality.rejection_reason}</span>" if not quality.is_acceptable else "")
                )

    def _submit_enrollment(self) -> None:
        name = self.edit_enroll_name.text().strip()
        code = self.edit_enroll_code.text().strip()
        cat = self.combo_enroll_cat.currentText()
        dept = self.edit_enroll_dept.text().strip() or None
        auth_ref = self.edit_enroll_auth_ref.text().strip() or None

        if not name or not code:
            QMessageBox.warning(self, "Validation Error", "Name and Identity Code are required.")
            return

        if not getattr(self, "_current_enroll_img", None) is not None:
            QMessageBox.warning(self, "Validation Error", "Please select a valid facial image.")
            return

        success, msg = face_intelligence_service.enroll_identity(
            name=name,
            identity_code=code,
            category=cat,
            face_image_bgr=self._current_enroll_img,
            enrolled_by_user_id="offline_admin",
            department=dept,
            authorization_ref=auth_ref,
        )

        if success:
            QMessageBox.information(self, "Enrollment Success", f"Identity '{name}' successfully enrolled and encrypted.")
            self.edit_enroll_name.clear()
            self.edit_enroll_code.clear()
            self._load_identities()
            self._load_audit_logs()
        else:
            QMessageBox.critical(self, "Enrollment Failed", msg)

    def _load_identities(self) -> None:
        try:
            with db_manager.get_session() as session:
                identities = session.query(FaceIdentity).filter_by(is_deleted=False).all()
                self.tbl_identities.setRowCount(len(identities))

                for row, ident in enumerate(identities):
                    self.tbl_identities.setItem(row, 0, QTableWidgetItem(ident.identity_code))
                    self.tbl_identities.setItem(row, 1, QTableWidgetItem(ident.name))
                    self.tbl_identities.setItem(row, 2, QTableWidgetItem(ident.category))
                    self.tbl_identities.setItem(row, 3, QTableWidgetItem(ident.department or "—"))

                    status = "Active" if ident.is_active else "Revoked"
                    status_item = QTableWidgetItem(status)
                    status_item.setForeground(QColor("#3fb950" if ident.is_active else "#f85149"))
                    self.tbl_identities.setItem(row, 4, status_item)

                    if ident.is_active:
                        btn_revoke = QPushButton("Revoke")
                        btn_revoke.setStyleSheet("background-color: #da3633; color: white; font-size: 11px;")
                        iid = ident.id
                        btn_revoke.clicked.connect(lambda _, target_id=iid: self._revoke_identity(target_id))
                        self.tbl_identities.setCellWidget(row, 5, btn_revoke)
        except Exception as e:
            logger.error("Failed to load identities: %s", e)

    def _revoke_identity(self, identity_id: str) -> None:
        face_intelligence_service.revoke_identity(identity_id, reason="Operator revocation", revoked_by_user_id="offline_admin")
        self._load_identities()
        self._load_audit_logs()

    def _load_audit_logs(self) -> None:
        try:
            with db_manager.get_session() as session:
                logs = session.query(BiometricAuditLog).order_by(BiometricAuditLog.timestamp.desc()).limit(50).all()
                self.tbl_audit.setRowCount(len(logs))
                for row, l in enumerate(logs):
                    self.tbl_audit.setItem(row, 0, QTableWidgetItem(l.timestamp.strftime("%Y-%m-%d %H:%M:%S") if l.timestamp else ""))
                    self.tbl_audit.setItem(row, 1, QTableWidgetItem(l.action))
                    self.tbl_audit.setItem(row, 2, QTableWidgetItem(l.user_id or "system"))
                    self.tbl_audit.setItem(row, 3, QTableWidgetItem(l.identity_id or "—"))
                    self.tbl_audit.setItem(row, 4, QTableWidgetItem(l.details_json or "—"))
        except Exception as e:
            logger.error("Failed to load audit logs: %s", e)
