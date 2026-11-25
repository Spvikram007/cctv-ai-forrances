"""
Evidence Locker & Append-Only Chain-of-Custody Ledger (Phase 10 - F-023).
Provides secure evidence vaulting, role-based access control, cryptographic
manifest signing, blockchain/Merkle-style hash-chained custody ledgers, and
strict non-destructive provenance tracking for original and derived recordings.
"""

import os
import sys
import json
import uuid
import shutil
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum

from core.logging.logger import get_logger
from core.config.settings import settings
from engines.forensic_engine.authenticity import (
    VideoAuthenticityAnalyzer,
    ForensicAnalysisReport,
    IntegrityStatus,
)
from engines.forensic_engine.crypto_signer import ForensicSigner

logger = get_logger("evidence_locker")


class ForensicAccessDeniedError(PermissionError):
    """Raised when an operator attempts an unauthorized evidence action."""
    pass


class EvidenceType(str, Enum):
    ORIGINAL_CAPTURE = "ORIGINAL_CAPTURE"
    DERIVED_ENHANCEMENT = "DERIVED_ENHANCEMENT"
    EXPORTED_CLIP = "EXPORTED_CLIP"


@dataclass
class CustodyEvent:
    """Represents a single immutable entry in the chain-of-custody ledger."""
    event_id: str
    evidence_id: str
    timestamp_utc: str
    operator_username: str
    operator_role: str
    action: str  # INGEST, ACCESS, VIEW, VERIFY, EXPORT, LOCK, ATTEMPTED_TAMPER, UNAUTHORIZED_ACCESS
    details: Dict[str, Any]
    prev_hash: str
    record_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ChainOfCustodyLedger:
    """
    Append-only cryptographic chain-of-custody ledger.
    Every record is linked to the previous record hash via SHA-256.
    Any deletion, insertion, or modification breaks the cryptographic verification.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self, ledger_file: Path) -> None:
        self.ledger_file = ledger_file
        self.ledger_file.parent.mkdir(parents=True, exist_ok=True)

    def get_latest_hash(self) -> str:
        """Returns the hash of the most recent record or GENESIS_HASH."""
        if not self.ledger_file.exists() or self.ledger_file.stat().st_size == 0:
            return self.GENESIS_HASH

        last_hash = self.GENESIS_HASH
        with open(self.ledger_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        last_hash = record.get("record_hash", self.GENESIS_HASH)
                    except json.JSONDecodeError:
                        pass
        return last_hash

    def append_event(
        self,
        evidence_id: str,
        operator_username: str,
        operator_role: str,
        action: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> CustodyEvent:
        """Appends a cryptographically linked custody event to the ledger."""
        prev_hash = self.get_latest_hash()
        event_id = str(uuid.uuid4())
        timestamp_utc = datetime.now(timezone.utc).isoformat()
        details_dict = details or {}

        # Canonical payload for hashing
        payload = {
            "event_id": event_id,
            "evidence_id": evidence_id,
            "timestamp_utc": timestamp_utc,
            "operator_username": operator_username,
            "operator_role": operator_role,
            "action": action,
            "details": details_dict,
            "prev_hash": prev_hash,
        }
        canonical_str = json.dumps(payload, sort_keys=True)
        record_hash = hashlib.sha256((prev_hash + canonical_str).encode("utf-8")).hexdigest()

        event = CustodyEvent(
            event_id=event_id,
            evidence_id=evidence_id,
            timestamp_utc=timestamp_utc,
            operator_username=operator_username,
            operator_role=operator_role,
            action=action,
            details=details_dict,
            prev_hash=prev_hash,
            record_hash=record_hash,
        )

        with open(self.ledger_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

        return event

    def get_all_events(self) -> List[CustodyEvent]:
        """Reads all events from the ledger."""
        if not self.ledger_file.exists():
            return []

        events: List[CustodyEvent] = []
        with open(self.ledger_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    d = json.loads(line)
                    events.append(CustodyEvent(**d))
        return events

    def verify_chain(self) -> Tuple[bool, int, Optional[str]]:
        """
        Verifies the cryptographic integrity of the entire chain.
        Returns: (is_valid, record_count, error_message).
        """
        if not self.ledger_file.exists():
            return True, 0, None

        events = self.get_all_events()
        if not events:
            return True, 0, None

        expected_prev = self.GENESIS_HASH
        for idx, event in enumerate(events):
            if event.prev_hash != expected_prev:
                return (
                    False,
                    idx,
                    f"Hash break at record {idx}: prev_hash '{event.prev_hash[:16]}' != expected '{expected_prev[:16]}'",
                )

            payload = {
                "event_id": event.event_id,
                "evidence_id": event.evidence_id,
                "timestamp_utc": event.timestamp_utc,
                "operator_username": event.operator_username,
                "operator_role": event.operator_role,
                "action": event.action,
                "details": event.details,
                "prev_hash": event.prev_hash,
            }
            canonical_str = json.dumps(payload, sort_keys=True)
            recalculated_hash = hashlib.sha256((expected_prev + canonical_str).encode("utf-8")).hexdigest()

            if recalculated_hash != event.record_hash:
                return (
                    False,
                    idx,
                    f"Content alteration at record {idx}: record_hash '{event.record_hash[:16]}' != recalculated '{recalculated_hash[:16]}'",
                )

            expected_prev = event.record_hash

        return True, len(events), None


@dataclass
class SignedEvidenceManifest:
    """Standardized cryptographically signed forensic evidence manifest."""
    manifest_version: str
    evidence_id: str
    case_number: str
    channel_id: str
    evidence_type: str  # ORIGINAL_CAPTURE or DERIVED_ENHANCEMENT
    file_name: str
    file_size_bytes: int
    file_sha256: str
    duration_sec: float
    nominal_fps: float
    resolution: Tuple[int, int]
    codec: str
    source_evidence_id: Optional[str] = None
    source_sha256: Optional[str] = None
    enhancement_metadata: Optional[Dict[str, Any]] = None
    forensic_analysis_summary: Dict[str, Any] = field(default_factory=dict)
    signer_identity: str = "SYSTEM_FORENSIC_ENGINE"
    signing_time_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    public_key_pem: str = ""
    signature_hex: str = ""
    is_sealed: bool = True
    legal_disclaimer: str = (
        "JUDICIAL NOTICE: This evidence package was ingested, hashed, and cryptographically signed "
        "under controlled chain-of-custody protocols. Cryptographic validation proves the file has remained "
        "byte-identical since ingestion. If labeled 'DERIVED_ENHANCEMENT', the contents represent algorithmically "
        "clarified media and MUST NOT be presented as original evidence without the companion source capture."
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def canonical_bytes_for_signing(self) -> bytes:
        """Produces deterministic canonical representation for digital signing."""
        d = {
            "manifest_version": self.manifest_version,
            "evidence_id": self.evidence_id,
            "case_number": self.case_number,
            "channel_id": self.channel_id,
            "evidence_type": self.evidence_type,
            "file_name": self.file_name,
            "file_size_bytes": self.file_size_bytes,
            "file_sha256": self.file_sha256,
            "duration_sec": self.duration_sec,
            "nominal_fps": self.nominal_fps,
            "resolution": list(self.resolution),
            "codec": self.codec,
            "source_evidence_id": self.source_evidence_id,
            "source_sha256": self.source_sha256,
            "enhancement_metadata": self.enhancement_metadata,
            "signing_time_utc": self.signing_time_utc,
            "signer_identity": self.signer_identity,
        }
        return json.dumps(d, sort_keys=True).encode("utf-8")


class EvidenceLocker:
    """
    Controlled Evidence Locker with Windows DPAPI-protected asymmetric signing,
    strict Role-Based Access Control, append-only chain of custody, and support
    for both original recordings and derived enhancements.
    """

    ALLOWED_ROLES_INGEST = {"ADMIN", "INVESTIGATOR", "SUPERVISOR"}
    ALLOWED_ROLES_EXPORT = {"ADMIN", "INVESTIGATOR", "SUPERVISOR"}
    ALLOWED_ROLES_VIEW = {"ADMIN", "INVESTIGATOR", "SUPERVISOR", "OPERATOR", "VIEWER"}

    def __init__(self, locker_dir: Optional[str] = None) -> None:
        if locker_dir is None:
            self.base_dir = Path(settings.storage.evidence_dir) / "locker"
        else:
            self.base_dir = Path(locker_dir)

        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.analyzer = VideoAuthenticityAnalyzer()
        self.signer = ForensicSigner()

    def _check_permission(self, role: str, allowed_set: set, action_name: str) -> None:
        """Enforces Role-Based Access Control."""
        normalized_role = (role or "").strip().upper()
        if normalized_role not in allowed_set:
            logger.warning("Access denied: role '%s' attempted '%s'", normalized_role, action_name)
            raise ForensicAccessDeniedError(
                f"Unauthorized: Role '{normalized_role}' does not have permission to perform '{action_name}'."
            )

    @staticmethod
    def _apply_filesystem_lock(file_path: Path) -> None:
        """Applies read-only attributes to locked evidence files."""
        try:
            if sys.platform == "win32":
                import ctypes
                # FILE_ATTRIBUTE_READONLY = 0x1
                ctypes.windll.kernel32.SetFileAttributesW(str(file_path), 0x1)
            else:
                os.chmod(str(file_path), 0o444)
        except Exception as e:
            logger.warning("Could not set filesystem read-only lock on %s: %s", file_path, e)

    def ingest_recording(
        self,
        source_file_path: str,
        case_number: str,
        channel_id: str,
        operator_username: str,
        operator_role: str,
        is_enhanced: bool = False,
        source_evidence_id: Optional[str] = None,
        source_sha256: Optional[str] = None,
        enhancement_metadata: Optional[Dict[str, Any]] = None,
    ) -> SignedEvidenceManifest:
        """
        Ingests a video recording or enhanced clip into the Evidence Locker.
        Computes SHA-256, runs authenticity analysis, digitally signs manifest,
        and records the event in the append-only custody ledger.
        """
        self._check_permission(operator_role, self.ALLOWED_ROLES_INGEST, "INGEST_EVIDENCE")

        src_p = Path(source_file_path)
        if not src_p.exists():
            raise FileNotFoundError(f"Source file not found: {source_file_path}")

        # Auto-detect Phase 9 enhancement sidecar manifest if present
        sidecar_manifest_p = Path(f"{source_file_path}.manifest.json")
        if sidecar_manifest_p.exists() and not is_enhanced:
            try:
                with open(sidecar_manifest_p, "r", encoding="utf-8") as f:
                    sidecar_data = json.load(f)
                is_enhanced = True
                source_sha256 = sidecar_data.get("source_sha256")
                enhancement_metadata = sidecar_data.get("config_applied")
            except Exception as e:
                logger.warning("Failed to parse Phase 9 sidecar manifest: %s", e)

        evidence_id = str(uuid.uuid4())
        item_dir = self.base_dir / evidence_id
        item_dir.mkdir(parents=True, exist_ok=True)

        dest_file = item_dir / src_p.name
        shutil.copy2(str(src_p), str(dest_file))
        self._apply_filesystem_lock(dest_file)

        # 1. Run authenticity audit
        audit_report = self.analyzer.audit_video(str(dest_file))

        evidence_type = EvidenceType.DERIVED_ENHANCEMENT.value if is_enhanced else EvidenceType.ORIGINAL_CAPTURE.value

        # 2. Build signed manifest
        manifest = SignedEvidenceManifest(
            manifest_version="1.0",
            evidence_id=evidence_id,
            case_number=case_number,
            channel_id=channel_id,
            evidence_type=evidence_type,
            file_name=src_p.name,
            file_size_bytes=dest_file.stat().st_size,
            file_sha256=audit_report.sha256_hash,
            duration_sec=audit_report.container_info.duration_sec,
            nominal_fps=audit_report.container_info.nominal_fps,
            resolution=audit_report.container_info.resolution,
            codec=audit_report.container_info.codec_fourcc,
            source_evidence_id=source_evidence_id,
            source_sha256=source_sha256,
            enhancement_metadata=enhancement_metadata,
            forensic_analysis_summary={
                "status": audit_report.status.value,
                "confidence_score": audit_report.confidence_score,
                "discontinuities_count": len(audit_report.discontinuities),
                "duplicate_clusters_count": len(audit_report.duplicate_clusters),
                "timestamp_anomalies_count": len(audit_report.timestamp_anomalies),
                "missing_frames_estimated": audit_report.missing_frames_estimated,
            },
            public_key_pem=self.signer.get_public_key_pem(),
        )

        # 3. Digitally sign manifest payload
        canonical_bytes = manifest.canonical_bytes_for_signing()
        signature_hex = self.signer.sign_payload(canonical_bytes)
        manifest.signature_hex = signature_hex

        manifest_file = item_dir / "manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2)

        sig_file = item_dir / "manifest.sig"
        with open(sig_file, "w", encoding="utf-8") as f:
            f.write(signature_hex)

        # 4. Chain of custody ledger
        ledger = ChainOfCustodyLedger(item_dir / "chain_of_custody.jsonl")
        ledger.append_event(
            evidence_id=evidence_id,
            operator_username=operator_username,
            operator_role=operator_role,
            action="INGEST",
            details={
                "source_file": str(src_p.name),
                "file_sha256": audit_report.sha256_hash,
                "evidence_type": evidence_type,
                "case_number": case_number,
            },
        )

        logger.info("Successfully ingested evidence '%s' (Type=%s) into locker.", evidence_id, evidence_type)
        return manifest

    def verify_evidence(
        self,
        evidence_id: str,
        operator_username: str,
        operator_role: str,
    ) -> Dict[str, Any]:
        """
        Verifies the integrity of locked evidence:
        1. Validates current media SHA-256 against manifest.
        2. Validates ECDSA digital signature.
        3. Validates custody ledger hash-chain.
        """
        item_dir = self.base_dir / evidence_id
        if not item_dir.exists():
            raise FileNotFoundError(f"Evidence '{evidence_id}' not found in locker.")

        ledger = ChainOfCustodyLedger(item_dir / "chain_of_custody.jsonl")
        manifest_file = item_dir / "manifest.json"

        if not manifest_file.exists():
            raise FileNotFoundError(f"Manifest missing for evidence '{evidence_id}'.")

        with open(manifest_file, "r", encoding="utf-8") as f:
            m_dict = json.load(f)

        media_file = item_dir / m_dict["file_name"]
        if not media_file.exists():
            ledger.append_event(
                evidence_id=evidence_id,
                operator_username=operator_username,
                operator_role=operator_role,
                action="TAMPER_DETECTED",
                details={"error": "Media file missing from vault folder"},
            )
            return {
                "evidence_id": evidence_id,
                "is_valid": False,
                "error": "Media file is missing.",
            }

        # Check media SHA-256
        current_sha256 = self.analyzer.compute_file_sha256(str(media_file))
        sha_valid = (current_sha256 == m_dict["file_sha256"])

        # Check Digital Signature
        manifest_obj = SignedEvidenceManifest(**m_dict)
        canonical_bytes = manifest_obj.canonical_bytes_for_signing()
        sig_valid = self.signer.verify_signature(
            payload=canonical_bytes,
            signature_hex=manifest_obj.signature_hex,
            public_key_pem=manifest_obj.public_key_pem,
        )

        # Check Custody Chain
        chain_valid, chain_len, chain_err = ledger.verify_chain()

        overall_valid = sha_valid and sig_valid and chain_valid

        # Record access / verification in custody ledger
        action_name = "VERIFY" if overall_valid else "TAMPER_DETECTED"
        ledger.append_event(
            evidence_id=evidence_id,
            operator_username=operator_username,
            operator_role=operator_role,
            action=action_name,
            details={
                "sha256_match": sha_valid,
                "signature_valid": sig_valid,
                "custody_chain_valid": chain_valid,
                "records_inspected": chain_len,
            },
        )

        return {
            "evidence_id": evidence_id,
            "is_valid": overall_valid,
            "sha256_match": sha_valid,
            "signature_valid": sig_valid,
            "custody_chain_valid": chain_valid,
            "records_count": chain_len,
            "evidence_type": manifest_obj.evidence_type,
            "file_name": manifest_obj.file_name,
            "source_sha256": manifest_obj.source_sha256,
        }

    def list_evidence(self, operator_role: str = "INVESTIGATOR") -> List[Dict[str, Any]]:
        """Lists all evidence items in the locker."""
        self._check_permission(operator_role, self.ALLOWED_ROLES_VIEW, "LIST_EVIDENCE")

        results = []
        if not self.base_dir.exists():
            return results

        for item_dir in self.base_dir.iterdir():
            if item_dir.is_dir():
                manifest_file = item_dir / "manifest.json"
                if manifest_file.exists():
                    try:
                        with open(manifest_file, "r", encoding="utf-8") as f:
                            m_dict = json.load(f)
                        results.append(m_dict)
                    except Exception:
                        pass
        return results

    def get_manifest(self, evidence_id: str, operator_role: str = "INVESTIGATOR") -> SignedEvidenceManifest:
        """Retrieves the manifest for an evidence item."""
        self._check_permission(operator_role, self.ALLOWED_ROLES_VIEW, "VIEW_MANIFEST")
        manifest_file = self.base_dir / evidence_id / "manifest.json"
        if not manifest_file.exists():
            raise FileNotFoundError(f"Manifest not found for evidence '{evidence_id}'.")
        with open(manifest_file, "r", encoding="utf-8") as f:
            d = json.load(f)
        return SignedEvidenceManifest(**d)
