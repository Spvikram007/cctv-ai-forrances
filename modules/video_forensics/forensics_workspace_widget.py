"""
Digital Forensics & Evidence Integrity Workspace (Phase 10 & 10.1 - F-018 & F-023).
Provides evidence locker browser, SHA-256 verification, discontinuity inspection,
append-only chain of custody audits, independent signed checkpoints, trusted keystore
validation, 5-tier RBAC enforcement, and standalone .cctvevid package export.
"""

import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTabWidget,
    QGroupBox,
    QFormLayout,
    QFileDialog,
    QMessageBox,
    QLineEdit,
    QComboBox,
    QTextEdit,
    QFrame,
)

from core.logging.logger import get_logger
from core.config.settings import settings
from engines.forensic_engine.authenticity import (
    VideoAuthenticityAnalyzer,
    ForensicAnalysisReport,
    IntegrityStatus,
)
from engines.forensic_engine.crypto_signer import ForensicSigner, TrustedKeyStore
from engines.forensic_engine.evidence_locker import (
    EvidenceLocker,
    SignedEvidenceManifest,
    EvidenceType,
    ChainOfCustodyLedger,
    CustodyCheckpoint,
    ForensicAccessDeniedError,
)
from engines.forensic_engine.evidence_packager import EvidencePackager

logger = get_logger("forensics_widget")


class VideoForensicsWidget(QWidget):
    """
    Primary workspace widget for digital video forensics, 5-Tier RBAC evidence locker
    management, trusted keystore inspection, and cryptographic audit logging.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.locker = EvidenceLocker()
        self.packager = EvidencePackager(self.locker)
        self.analyzer = VideoAuthenticityAnalyzer()

        self._current_operator = "SYSTEM_ADMIN"
        self._current_role = "INVESTIGATOR"
        self._active_manifest: Optional[SignedEvidenceManifest] = None

        self._init_ui()
        self._refresh_evidence_list()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        # 1. Header Toolbar
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        lbl_title = QLabel("DIGITAL FORENSICS, AUTHENTICITY & EVIDENCE INTEGRITY")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #58a6ff;")
        lbl_sub = QLabel("Evidence Locker, Trusted Keystore, Signed Checkpoints & 5-Tier RBAC | Phase 10.1")
        lbl_sub.setStyleSheet("font-size: 11px; color: #8b949e;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        btn_ingest = QPushButton("Ingest Recording...")
        btn_ingest.setStyleSheet("background-color: #1f6feb; color: white; padding: 6px 12px; border-radius: 4px; font-weight: 600;")
        btn_ingest.clicked.connect(self._on_ingest_clicked)
        header_layout.addWidget(btn_ingest)

        btn_verify = QPushButton("Verify Selected")
        btn_verify.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 6px 12px; border-radius: 4px;")
        btn_verify.clicked.connect(self._on_verify_clicked)
        header_layout.addWidget(btn_verify)

        btn_scan_all = QPushButton("Scan Locker Integrity")
        btn_scan_all.setStyleSheet("background-color: #388bfd1a; border: 1px solid #1f6feb; color: #58a6ff; padding: 6px 12px; border-radius: 4px; font-weight: 600;")
        btn_scan_all.clicked.connect(self._on_scan_integrity_clicked)
        header_layout.addWidget(btn_scan_all)

        btn_export_pkg = QPushButton("Export Evidence Package")
        btn_export_pkg.setStyleSheet("background-color: #238636; color: white; padding: 6px 12px; border-radius: 4px; font-weight: 600;")
        btn_export_pkg.clicked.connect(self._on_export_package_clicked)
        header_layout.addWidget(btn_export_pkg)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 6px 12px; border-radius: 4px;")
        btn_refresh.clicked.connect(self._refresh_evidence_list)
        header_layout.addWidget(btn_refresh)

        main_layout.addLayout(header_layout)

        # 2. Main Workspace Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(4)

        # Left: Evidence Locker Browser
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        lbl_browser = QLabel("EVIDENCE LOCKER ITEMS")
        lbl_browser.setStyleSheet("color: #8b949e; font-weight: 600; font-size: 12px;")
        left_layout.addWidget(lbl_browser)

        self.tbl_evidence = QTableWidget()
        self.tbl_evidence.setColumnCount(4)
        self.tbl_evidence.setHorizontalHeaderLabels(["Case #", "Type", "File Name", "SHA-256 (Preview)"])
        self.tbl_evidence.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_evidence.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_evidence.setStyleSheet("background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;")
        self.tbl_evidence.itemSelectionChanged.connect(self._on_evidence_selected)
        left_layout.addWidget(self.tbl_evidence)

        splitter.addWidget(left_widget)

        # Right: Tabbed Detail View
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #30363d; background-color: #0d1117; }
            QTabBar::tab { background-color: #161b22; color: #8b949e; padding: 6px 14px; border: 1px solid #30363d; }
            QTabBar::tab:selected { background-color: #21262d; color: #58a6ff; font-weight: bold; }
        """)

        # Tab 1: Integrity & Authenticity Analysis
        self.tab_authenticity = QWidget()
        self._init_authenticity_tab()
        self.tabs.addTab(self.tab_authenticity, "Integrity & Discontinuity Audit")

        # Tab 2: Chain of Custody & Checkpoints
        self.tab_custody = QWidget()
        self._init_custody_tab()
        self.tabs.addTab(self.tab_custody, "Chain of Custody & Checkpoints")

        # Tab 3: Digital Signature & Trusted Keystore
        self.tab_signature = QWidget()
        self._init_signature_tab()
        self.tabs.addTab(self.tab_signature, "Digital Signature & Key Trust")

        # Tab 4: Legal & Forensic Disclaimer
        self.tab_legal = QWidget()
        self._init_legal_tab()
        self.tabs.addTab(self.tab_legal, "Legal Notice & Standards")

        right_layout.addWidget(self.tabs)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        main_layout.addWidget(splitter)

    def _init_authenticity_tab(self) -> None:
        layout = QVBoxLayout(self.tab_authenticity)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Overview Box
        box_overview = QGroupBox("Cryptographic File Integrity")
        box_overview.setStyleSheet("QGroupBox { color: #58a6ff; font-weight: 600; border: 1px solid #30363d; border-radius: 4px; padding: 10px; margin-top: 6px; }")
        fl_over = QFormLayout(box_overview)

        self.lbl_sha256 = QLabel("Select an evidence item to inspect")
        self.lbl_sha256.setStyleSheet("color: #3fb950; font-family: monospace; font-size: 11px;")
        fl_over.addRow("SHA-256 Hash:", self.lbl_sha256)

        self.lbl_status_badge = QLabel("UNVERIFIED")
        self.lbl_status_badge.setStyleSheet("color: #8b949e; font-weight: bold;")
        fl_over.addRow("Forensic Status:", self.lbl_status_badge)

        self.lbl_container_meta = QLabel("-")
        self.lbl_container_meta.setStyleSheet("color: #c9d1d9; font-size: 11px;")
        fl_over.addRow("Container & Codec:", self.lbl_container_meta)

        self.lbl_source_link = QLabel("Original Capture")
        self.lbl_source_link.setStyleSheet("color: #58a6ff; font-size: 11px;")
        fl_over.addRow("Provenance:", self.lbl_source_link)

        layout.addWidget(box_overview)

        # Anomaly Summary Table
        lbl_anomalies = QLabel("Detected Discontinuities & Sequence Irregularities:")
        lbl_anomalies.setStyleSheet("color: #c9d1d9; font-weight: 600;")
        layout.addWidget(lbl_anomalies)

        self.tbl_discontinuities = QTableWidget()
        self.tbl_discontinuities.setColumnCount(4)
        self.tbl_discontinuities.setHorizontalHeaderLabels(["Frame #", "Time (sec)", "Type", "Description"])
        self.tbl_discontinuities.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_discontinuities.setStyleSheet("background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;")
        layout.addWidget(self.tbl_discontinuities)

    def _init_custody_tab(self) -> None:
        layout = QVBoxLayout(self.tab_custody)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Chain Status Bar
        status_bar = QHBoxLayout()
        self.lbl_chain_status = QLabel("Chain Integrity: UNVERIFIED")
        self.lbl_chain_status.setStyleSheet("color: #8b949e; font-weight: bold;")
        status_bar.addWidget(self.lbl_chain_status)

        self.lbl_checkpoint_status = QLabel("Checkpoints: UNVERIFIED")
        self.lbl_checkpoint_status.setStyleSheet("color: #8b949e; font-size: 11px;")
        status_bar.addWidget(self.lbl_checkpoint_status)
        status_bar.addStretch()

        btn_create_cp = QPushButton("Create Signed Checkpoint")
        btn_create_cp.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; color: #58a6ff; padding: 4px 10px; border-radius: 4px;")
        btn_create_cp.clicked.connect(self._create_checkpoint_clicked)
        status_bar.addWidget(btn_create_cp)

        btn_verify_chain = QPushButton("Verify Hash-Chain")
        btn_verify_chain.setStyleSheet("background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 4px 10px; border-radius: 4px;")
        btn_verify_chain.clicked.connect(self._verify_custody_chain)
        status_bar.addWidget(btn_verify_chain)
        layout.addLayout(status_bar)

        self.tbl_custody = QTableWidget()
        self.tbl_custody.setColumnCount(5)
        self.tbl_custody.setHorizontalHeaderLabels(["Timestamp (UTC)", "Operator", "Role", "Action", "Hash Link"])
        self.tbl_custody.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_custody.setStyleSheet("background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d;")
        layout.addWidget(self.tbl_custody)

    def _init_signature_tab(self) -> None:
        layout = QVBoxLayout(self.tab_signature)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        box_sig = QGroupBox("Asymmetric Digital Signature & Trust Infrastructure")
        box_sig.setStyleSheet("QGroupBox { color: #58a6ff; font-weight: 600; border: 1px solid #30363d; border-radius: 4px; padding: 10px; margin-top: 6px; }")
        fl = QFormLayout(box_sig)

        lbl_algo = QLabel("ECDSA (SECP256R1 / NIST P-256) with SHA-256")
        lbl_algo.setStyleSheet("color: #c9d1d9;")
        fl.addRow("Algorithm:", lbl_algo)

        lbl_key_prot = QLabel("Windows DPAPI (CryptProtectData with Hardware Entropy)")
        lbl_key_prot.setStyleSheet("color: #3fb950; font-weight: 600;")
        fl.addRow("Key Protection:", lbl_key_prot)

        self.lbl_key_id = QLabel("-")
        self.lbl_key_id.setStyleSheet("color: #79c0ff; font-weight: 600; font-family: monospace;")
        fl.addRow("Key ID:", self.lbl_key_id)

        self.lbl_fingerprint = QLabel("-")
        self.lbl_fingerprint.setStyleSheet("color: #79c0ff; font-family: monospace; font-size: 11px;")
        fl.addRow("Key Fingerprint:", self.lbl_fingerprint)

        self.lbl_trust_status = QLabel("CHECKING...")
        self.lbl_trust_status.setStyleSheet("color: #8b949e; font-weight: bold;")
        fl.addRow("Identity Trust:", self.lbl_trust_status)

        self.txt_signature = QTextEdit()
        self.txt_signature.setReadOnly(True)
        self.txt_signature.setMaximumHeight(55)
        self.txt_signature.setStyleSheet("background-color: #161b22; color: #79c0ff; font-family: monospace; font-size: 10px;")
        fl.addRow("Signature (Hex):", self.txt_signature)

        self.txt_pubkey = QTextEdit()
        self.txt_pubkey.setReadOnly(True)
        self.txt_pubkey.setMaximumHeight(85)
        self.txt_pubkey.setStyleSheet("background-color: #161b22; color: #8b949e; font-family: monospace; font-size: 10px;")
        fl.addRow("Public Key (PEM):", self.txt_pubkey)

        layout.addWidget(box_sig)
        layout.addStretch()

    def _init_legal_tab(self) -> None:
        layout = QVBoxLayout(self.tab_legal)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        notice_text = (
            "FORENSIC INTEGRITY NOTICE & LEGAL GUIDELINES (PHASE 10.1 HARDENED)\n"
            "===================================================================\n\n"
            "1. HASH INTEGRITY != SCENE TRUTHFULNESS:\n"
            "A valid SHA-256 hash and ECDSA digital signature prove strictly that the acquired digital file "
            "has not been modified, altered, truncated, or tampered with since acquisition. "
            "It does NOT prove that the recorded physical events were authentic or un-staged prior to capture.\n\n"
            "2. AUTHORITATIVE TRUST STORE VS SELF-SUPPLIED KEYS:\n"
            "An evidence package includes its public key for convenience, but trust CANNOT be established by the "
            "package alone. Authoritative third-party verification requires comparing key fingerprints against an "
            "independent external Trusted Keystore or trusted root certificate.\n\n"
            "3. INDEPENDENT SIGNED CHECKPOINTS:\n"
            "Periodic signed ledger checkpoints are stored outside the evidence locker. Even if an attacker "
            "with full local filesystem access rewrites the custody ledger and re-computes Merkle hashes, the "
            "mismatch against external signed checkpoints exposes the alteration immediately.\n\n"
            "4. 5-TIER FORENSIC ROLE-BASED ACCESS CONTROL (5-TIER RBAC):\n"
            "  - ADMIN: Full configuration, ingestion, export, checkpoints, auditing\n"
            "  - INVESTIGATOR: Ingestion, packaging, verification, full case access\n"
            "  - SUPERVISOR: Ingestion, review, verification, export approval\n"
            "  - OPERATOR: Evidence viewing, stream verification, live audit checks\n"
            "  - VIEWER: Read-only inspection of verified evidence manifests\n\n"
            "5. DERIVED ENHANCEMENT PROVENANCE:\n"
            "If an evidence item is classified as 'DERIVED_ENHANCEMENT', the file represents an algorithmic "
            "or deep-learned restoration (e.g. low-light amplification, dehazing, super-resolution). "
            "Under criminal and civil court admissibility rules, derived footage MUST NOT be presented as raw "
            "original evidence without disclosing the companion original capture and full parameter manifest.\n"
        )

        txt_notice = QTextEdit()
        txt_notice.setReadOnly(True)
        txt_notice.setText(notice_text)
        txt_notice.setStyleSheet("background-color: #161b22; color: #c9d1d9; font-size: 11px; line-height: 1.4;")
        layout.addWidget(txt_notice)

    def _refresh_evidence_list(self) -> None:
        """Reloads evidence items from the locker."""
        items = self.locker.list_evidence(self._current_role)
        self.tbl_evidence.setRowCount(len(items))

        for row, item in enumerate(items):
            self.tbl_evidence.setItem(row, 0, QTableWidgetItem(item.get("case_number", "CASE-001")))
            type_item = QTableWidgetItem(item.get("evidence_type", "ORIGINAL_CAPTURE"))
            if item.get("evidence_type") == EvidenceType.DERIVED_ENHANCEMENT.value:
                type_item.setForeground(QColor("#d2a8ff"))
            else:
                type_item.setForeground(QColor("#58a6ff"))
            self.tbl_evidence.setItem(row, 1, type_item)
            self.tbl_evidence.setItem(row, 2, QTableWidgetItem(item.get("file_name", "")))
            sha_pref = (item.get("file_sha256", "")[:16] + "...") if item.get("file_sha256") else "-"
            self.tbl_evidence.setItem(row, 3, QTableWidgetItem(sha_pref))

    def _on_evidence_selected(self) -> None:
        """Handles selection of an evidence item."""
        selected = self.tbl_evidence.selectedItems()
        if not selected:
            return

        row = self.tbl_evidence.currentRow()
        items = self.locker.list_evidence(self._current_role)
        if 0 <= row < len(items):
            manifest_dict = items[row]
            self._active_manifest = SignedEvidenceManifest(**manifest_dict)
            self._display_manifest_details(self._active_manifest)

    def _display_manifest_details(self, manifest: SignedEvidenceManifest) -> None:
        """Populates detail tabs with active manifest."""
        self.lbl_sha256.setText(manifest.file_sha256)
        self.lbl_container_meta.setText(
            f"Codec: {manifest.codec} | Res: {manifest.resolution[0]}x{manifest.resolution[1]} | "
            f"FPS: {manifest.nominal_fps} | Dur: {manifest.duration_sec:.1f}s | Size: {manifest.file_size_bytes:,} bytes"
        )

        if manifest.evidence_type == EvidenceType.DERIVED_ENHANCEMENT.value:
            self.lbl_source_link.setText(
                f"DERIVED AI ENHANCEMENT (Source SHA-256: {manifest.source_sha256[:16]}...)"
            )
            self.lbl_source_link.setStyleSheet("color: #d2a8ff; font-weight: 600;")
        else:
            self.lbl_source_link.setText("ORIGINAL SENSOR CAPTURE (Raw Evidence)")
            self.lbl_source_link.setStyleSheet("color: #58a6ff; font-weight: 600;")

        summary = manifest.forensic_analysis_summary
        st = summary.get("status", "AUTHENTIC")
        self.lbl_status_badge.setText(st)
        if st in ("AUTHENTIC", "VALID"):
            self.lbl_status_badge.setStyleSheet("color: #3fb950; font-weight: bold;")
        elif st in ("ANOMALOUS", "SUSPICIOUS"):
            self.lbl_status_badge.setStyleSheet("color: #d29922; font-weight: bold;")
        else:
            self.lbl_status_badge.setStyleSheet("color: #f85149; font-weight: bold;")

        # Signatures & Trust
        self.lbl_key_id.setText(manifest.key_id or "KEY-2026-PRIMARY-01")
        self.lbl_fingerprint.setText(manifest.key_fingerprint or "-")
        is_trusted, _, reason = self.locker.signer.trust_store.is_key_trusted(manifest.public_key_pem)
        if is_trusted:
            self.lbl_trust_status.setText("TRUSTED (Authoritative Keystore)")
            self.lbl_trust_status.setStyleSheet("color: #3fb950; font-weight: bold;")
        else:
            self.lbl_trust_status.setText(f"UNTRUSTED ({reason})")
            self.lbl_trust_status.setStyleSheet("color: #f85149; font-weight: bold;")

        self.txt_signature.setText(manifest.signature_hex)
        self.txt_pubkey.setText(manifest.public_key_pem)

        # Populate custody table
        item_dir = self.locker.base_dir / manifest.evidence_id
        ledger = ChainOfCustodyLedger(item_dir / "chain_of_custody.jsonl")
        events = ledger.get_all_events()

        self.tbl_custody.setRowCount(len(events))
        for r, ev in enumerate(events):
            self.tbl_custody.setItem(r, 0, QTableWidgetItem(ev.timestamp_utc[:19]))
            self.tbl_custody.setItem(r, 1, QTableWidgetItem(ev.operator_username))
            self.tbl_custody.setItem(r, 2, QTableWidgetItem(ev.operator_role))
            self.tbl_custody.setItem(r, 3, QTableWidgetItem(ev.action))
            self.tbl_custody.setItem(r, 4, QTableWidgetItem(ev.record_hash[:16] + "..."))

        is_valid, count, err = ledger.verify_chain()
        if is_valid:
            self.lbl_chain_status.setText(f"Chain Integrity: VERIFIED ({count} events linked)")
            self.lbl_chain_status.setStyleSheet("color: #3fb950; font-weight: bold;")
        else:
            self.lbl_chain_status.setText(f"Chain Integrity: TAMPERED! ({err})")
            self.lbl_chain_status.setStyleSheet("color: #f85149; font-weight: bold;")

        # Checkpoints status
        cp_valid, cp_count, cp_errs = self.locker.verify_checkpoints(manifest.evidence_id)
        if cp_valid:
            self.lbl_checkpoint_status.setText(f"Checkpoints: VERIFIED ({cp_count} signed)")
            self.lbl_checkpoint_status.setStyleSheet("color: #3fb950; font-size: 11px;")
        else:
            self.lbl_checkpoint_status.setText("Checkpoints: TAMPER DETECTED!")
            self.lbl_checkpoint_status.setStyleSheet("color: #f85149; font-weight: bold; font-size: 11px;")

    def _on_ingest_clicked(self) -> None:
        """Opens dialog to select a video file to ingest into evidence locker."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video Recording for Forensic Ingestion",
            settings.storage.recordings_dir,
            "Video Files (*.mp4 *.avi *.mkv *.ts)",
        )
        if not path:
            return

        try:
            case_no = "CASE-2026-001"
            channel_id = "CAM-01"
            manifest = self.locker.ingest_recording(
                source_file_path=path,
                case_number=case_no,
                channel_id=channel_id,
                operator_username=self._current_operator,
                operator_role=self._current_role,
            )
            QMessageBox.information(
                self,
                "Evidence Ingested",
                f"Successfully ingested:\n{Path(path).name}\n\nEvidence ID: {manifest.evidence_id}\nSHA-256: {manifest.file_sha256[:16]}...\nKey ID: {manifest.key_id}\nSigned and locked.",
            )
            self._refresh_evidence_list()
        except Exception as e:
            logger.error("Ingestion error: %s", e, exc_info=True)
            QMessageBox.critical(self, "Ingestion Failed", str(e))

    def _on_verify_clicked(self) -> None:
        """Runs full cryptographic and hash verification on the selected evidence item."""
        if self._active_manifest is None:
            QMessageBox.information(self, "Select Item", "Please select an evidence item first.")
            return

        res = self.locker.verify_evidence(
            evidence_id=self._active_manifest.evidence_id,
            operator_username=self._current_operator,
            operator_role=self._current_role,
        )

        msg = (
            f"Evidence ID: {res['evidence_id']}\n"
            f"SHA-256 Match: {'PASSED' if res['sha256_match'] else 'FAILED'}\n"
            f"Key Identity Trust: {'PASSED (TRUSTED)' if res['key_trusted'] else 'UNTRUSTED'}\n"
            f"Digital Signature: {'PASSED' if res['signature_valid'] else 'FAILED'}\n"
            f"Custody Chain: {'PASSED' if res['custody_chain_valid'] else 'FAILED'}\n"
            f"Signed Checkpoints: {'PASSED' if res['checkpoints_valid'] else 'FAILED'}\n"
            f"Overall Verdict: {'AUTHENTIC & UNALTERED' if res['is_valid'] else 'TAMPERED / ALTERED'}"
        )

        if res["is_valid"]:
            QMessageBox.information(self, "Verification Succeeded", msg)
        else:
            QMessageBox.warning(self, "Verification Warning", msg)

        self._display_manifest_details(self._active_manifest)

    def _on_scan_integrity_clicked(self) -> None:
        """Scans all evidence items in locker for tampering."""
        results = self.locker.scan_locker_integrity()
        total = len(results)
        valid = sum(1 for r in results if r.get("is_valid"))
        tampered = total - valid

        if tampered == 0:
            QMessageBox.information(
                self,
                "Locker Integrity Scan Clean",
                f"Scanned {total} evidence items.\nAll items verified cryptographically valid with zero tampering detected.",
            )
        else:
            QMessageBox.critical(
                self,
                "TAMPER DETECTED",
                f"Scanned {total} evidence items.\n{tampered} items failed verification!\nCheck audit logs immediately.",
            )
        self._refresh_evidence_list()

    def _on_export_package_clicked(self) -> None:
        """Exports the active evidence item as a standalone .cctvevid package."""
        if self._active_manifest is None:
            QMessageBox.information(self, "Select Item", "Please select an evidence item first.")
            return

        default_dir = Path(settings.storage.evidence_dir) / "exports"
        default_dir.mkdir(parents=True, exist_ok=True)
        pkg_name = f"evidence_{self._active_manifest.case_number}_{self._active_manifest.evidence_id[:8]}.cctvevid"

        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Standalone Forensic Package",
            str(default_dir / pkg_name),
            "Forensic Evidence Package (*.cctvevid *.zip)",
        )
        if not out_path:
            return

        try:
            created_pkg = self.packager.create_export_package(
                evidence_id=self._active_manifest.evidence_id,
                export_destination_path=out_path,
                operator_username=self._current_operator,
                operator_role=self._current_role,
            )
            QMessageBox.information(
                self,
                "Package Export Complete",
                f"Standalone forensic package created:\n{created_pkg}\n\nIncludes media, signed manifest, public key, signed checkpoints, and verification utility.",
            )
            self._display_manifest_details(self._active_manifest)
        except Exception as e:
            logger.error("Package export failed: %s", e, exc_info=True)
            QMessageBox.critical(self, "Export Failed", str(e))

    def _create_checkpoint_clicked(self) -> None:
        """Creates a signed periodic checkpoint for the active evidence."""
        if self._active_manifest is None:
            return
        try:
            cp = self.locker.create_signed_checkpoint(
                evidence_id=self._active_manifest.evidence_id,
                operator_username=self._current_operator,
                operator_role=self._current_role,
            )
            QMessageBox.information(
                self,
                "Checkpoint Created",
                f"Signed checkpoint created at record {cp.record_index}:\nHash: {cp.record_hash[:16]}...\nStored independently.",
            )
            self._display_manifest_details(self._active_manifest)
        except Exception as e:
            QMessageBox.critical(self, "Checkpoint Failed", str(e))

    def _verify_custody_chain(self) -> None:
        """Verifies the hash chain of the active ledger."""
        if self._active_manifest is None:
            return
        item_dir = self.locker.base_dir / self._active_manifest.evidence_id
        ledger = ChainOfCustodyLedger(item_dir / "chain_of_custody.jsonl")
        is_valid, count, err = ledger.verify_chain()

        if is_valid:
            QMessageBox.information(self, "Chain Verified", f"All {count} custody events verified intact.")
        else:
            QMessageBox.critical(self, "Tamper Detected", f"Chain verification failed:\n{err}")
