"""
Evidence Locker & Append-Only Chain-of-Custody Ledger (Phase 10 & 10.1 - F-023).
Provides secure evidence vaulting, 5-tier role-based access control, cryptographic
manifest signing, blockchain/Merkle-style hash-chained custody ledgers, periodic
digitally signed ledger checkpoints, independent external checkpoint verification,
and strict non-destructive provenance tracking for original and derived recordings.
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
from core.events.event_bus import bus
from engines.forensic_engine.authenticity import (
    VideoAuthenticityAnalyzer,
    ForensicAnalysisReport,
    IntegrityStatus,
)
from engines.forensic_engine.crypto_signer import (
    ForensicSigner,
    TrustedKeyStore,
    KeyStatus,
    compute_key_fingerprint,
)

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
    action: str  # INGEST, ACCESS, VIEW, VERIFY, EXPORT, CHECKPOINT, LOCK, ATTEMPTED_TAMPER, UNAUTHORIZED_ACCESS
    details: Dict[str, Any]
    prev_hash: str
    record_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CustodyCheckpoint:
    """
    Represents an independently signed checkpoint of the custody ledger.
    Protects against malicious administrators or compromised processes attempting
    to rewrite earlier ledger history and recompute Merkle hashes.
    """
    checkpoint_id: str
    evidence_id: str
    record_index: int
    record_hash: str
    timestamp_utc: str
    signer_identity: str
    key_id: str
    key_fingerprint: str
    signature_hex: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def canonical_bytes_for_signing(self) -> bytes:
        d = {
            "checkpoint_id": self.checkpoint_id,
            "evidence_id": self.evidence_id,
            "record_index": self.record_index,
            "record_hash": self.record_hash,
            "timestamp_utc": self.timestamp_utc,
            "signer_identity": self.signer_identity,
            "key_id": self.key_id,
            "key_fingerprint": self.key_fingerprint,
        }
        return json.dumps(d, sort_keys=True).encode("utf-8")


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
    key_id: str = "KEY-2026-PRIMARY-01"
    key_fingerprint: str = ""
    trust_status: str = "TRUSTED_AUTHORITY"
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
            "signer_identity": self.signer_identity,
            "key_id": self.key_id,
            "key_fingerprint": self.key_fingerprint,
            "signing_time_utc": self.signing_time_utc,
        }
        return json.dumps(d, sort_keys=True).encode("utf-8")


class EvidenceLocker:
    """
    Controlled Evidence Locker with Windows DPAPI-protected asymmetric signing,
    5-Tier Role-Based Access Control, append-only chain of custody, periodic
    signed checkpoints stored independently of the locker, and support
    for both original recordings and derived enhancements.

    Storage Immutability Notice:
    Filesystem attributes (such as Windows FILE_ATTRIBUTE_READONLY) provide basic
    safeguards against accidental user deletion or modification. However, local
    administrators and privileged processes can remove these attributes. For
    high-assurance judicial environments, external WORM (Write Once, Read Many)
    storage, AWS S3 Object Lock in Compliance Mode, or physically immutable
    media must be deployed in tandem with this software-level cryptographic chain.
    """

    # 5-Tier Forensic Role-Based Access Control (RBAC)
    # Tier 1: ADMIN - Full configuration, ingestion, export, checkpoints, auditing
    # Tier 2: INVESTIGATOR - Ingestion, packaging, verification, full case access
    # Tier 3: SUPERVISOR - Ingestion, review, verification, export approval
    # Tier 4: OPERATOR - Evidence viewing, stream verification, live audit checks
    # Tier 5: VIEWER - Read-only inspection of verified evidence manifests
    ALLOWED_ROLES_INGEST = {"ADMIN", "INVESTIGATOR", "SUPERVISOR"}
    ALLOWED_ROLES_EXPORT = {"ADMIN", "INVESTIGATOR", "SUPERVISOR"}
    ALLOWED_ROLES_CHECKPOINT = {"ADMIN", "INVESTIGATOR", "SUPERVISOR"}
    ALLOWED_ROLES_VIEW = {"ADMIN", "INVESTIGATOR", "SUPERVISOR", "OPERATOR", "VIEWER"}
    ALL_ROLES = {"ADMIN", "INVESTIGATOR", "SUPERVISOR", "OPERATOR", "VIEWER"}

    def __init__(
        self,
        locker_dir: Optional[str] = None,
        checkpoints_dir: Optional[str] = None,
        signer: Optional[ForensicSigner] = None,
    ) -> None:
        if locker_dir is None:
            self.base_dir = Path(settings.storage.evidence_dir) / "locker"
        else:
            self.base_dir = Path(locker_dir)

        if checkpoints_dir is None:
            self.checkpoints_dir = Path(settings.storage.evidence_dir) / "checkpoints"
        else:
            self.checkpoints_dir = Path(checkpoints_dir)

        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

        self.analyzer = VideoAuthenticityAnalyzer()
        self.signer = signer or ForensicSigner()

    def _check_permission(self, role: str, allowed_set: set, action_name: str) -> None:
        """Enforces 5-Tier Role-Based Access Control."""
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

    def create_signed_checkpoint(
        self,
        evidence_id: str,
        operator_username: str,
        operator_role: str,
    ) -> CustodyCheckpoint:
        """
        Creates and signs a periodic checkpoint of the custody ledger.
        Saves checkpoint copy inside the evidence locker AND independently in the
        external checkpoints store (preventing malicious admin re-write attacks).
        """
        self._check_permission(operator_role, self.ALLOWED_ROLES_CHECKPOINT, "CREATE_CHECKPOINT")

        item_dir = self.base_dir / evidence_id
        if not item_dir.exists():
            raise FileNotFoundError(f"Evidence '{evidence_id}' does not exist.")

        ledger = ChainOfCustodyLedger(item_dir / "chain_of_custody.jsonl")
        events = ledger.get_all_events()
        if not events:
            raise ValueError(f"Cannot checkpoint empty custody ledger for evidence '{evidence_id}'.")

        last_idx = len(events) - 1
        last_hash = events[-1].record_hash
        checkpoint_id = str(uuid.uuid4())
        timestamp_utc = datetime.now(timezone.utc).isoformat()

        checkpoint = CustodyCheckpoint(
            checkpoint_id=checkpoint_id,
            evidence_id=evidence_id,
            record_index=last_idx,
            record_hash=last_hash,
            timestamp_utc=timestamp_utc,
            signer_identity=self.signer.identity,
            key_id=self.signer.key_id,
            key_fingerprint=self.signer.key_fingerprint,
            signature_hex="",
        )

        canonical_bytes = checkpoint.canonical_bytes_for_signing()
        signature_hex = self.signer.sign_payload(canonical_bytes)
        checkpoint.signature_hex = signature_hex

        # 1. Store in local evidence folder
        local_checkpoints_file = item_dir / "checkpoints.json"
        checkpoints_list = []
        if local_checkpoints_file.exists():
            try:
                with open(local_checkpoints_file, "r", encoding="utf-8") as f:
                    checkpoints_list = json.load(f)
            except Exception:
                checkpoints_list = []

        checkpoints_list.append(checkpoint.to_dict())
        with open(local_checkpoints_file, "w", encoding="utf-8") as f:
            json.dump(checkpoints_list, f, indent=2)

        # 2. Store in independent external checkpoints directory
        external_file = self.checkpoints_dir / f"{evidence_id}_checkpoints.json"
        ext_list = []
        if external_file.exists():
            try:
                with open(external_file, "r", encoding="utf-8") as f:
                    ext_list = json.load(f)
            except Exception:
                ext_list = []

        ext_list.append(checkpoint.to_dict())
        with open(external_file, "w", encoding="utf-8") as f:
            json.dump(ext_list, f, indent=2)

        logger.info(
            "Created signed custody checkpoint '%s' for evidence '%s' at record index %d.",
            checkpoint_id,
            evidence_id,
            last_idx,
        )
        return checkpoint

    def verify_checkpoints(self, evidence_id: str) -> Tuple[bool, int, List[str]]:
        """
        Verifies all independent signed checkpoints for an evidence item.
        Detects rewritten, truncated, reordered, or deleted audit entries.
        Returns: (is_valid, checkpoints_verified_count, errors_list)
        """
        item_dir = self.base_dir / evidence_id
        if not item_dir.exists():
            return False, 0, [f"Evidence '{evidence_id}' does not exist."]

        ledger = ChainOfCustodyLedger(item_dir / "chain_of_custody.jsonl")
        events = ledger.get_all_events()

        external_file = self.checkpoints_dir / f"{evidence_id}_checkpoints.json"
        local_file = item_dir / "checkpoints.json"

        # Prefer external independent file, fallback to local
        checkpoint_source = external_file if external_file.exists() else local_file
        if not checkpoint_source.exists():
            return True, 0, []

        try:
            with open(checkpoint_source, "r", encoding="utf-8") as f:
                checkpoints_raw = json.load(f)
        except Exception as e:
            return False, 0, [f"Failed to read checkpoints file: {e}"]

        errors: List[str] = []
        valid_count = 0

        for c_dict in checkpoints_raw:
            cp = CustodyCheckpoint(**c_dict)

            # 1. Verify Checkpoint Signature
            canonical_bytes = cp.canonical_bytes_for_signing()
            # Lookup key in trust store
            is_sig_valid = False
            for k_entry in self.signer.trust_store.get_all_keys():
                if k_entry.get("fingerprint") == cp.key_fingerprint:
                    if self.signer.verify_signature(canonical_bytes, cp.signature_hex, k_entry["public_key_pem"]):
                        is_sig_valid = True
                        break

            # If not found by fingerprint, try active signer's public key
            if not is_sig_valid:
                is_sig_valid = self.signer.verify_signature(
                    canonical_bytes, cp.signature_hex, self.signer.get_public_key_pem()
                )

            if not is_sig_valid:
                errors.append(f"Checkpoint '{cp.checkpoint_id}' signature verification FAILED!")
                continue

            # 2. Verify Ledger Record Match
            if cp.record_index >= len(events):
                errors.append(
                    f"Ledger truncated! Checkpoint '{cp.checkpoint_id}' requires index {cp.record_index}, "
                    f"but ledger only contains {len(events)} records."
                )
                continue

            event_at_idx = events[cp.record_index]
            if event_at_idx.record_hash != cp.record_hash:
                errors.append(
                    f"Ledger history rewritten! Record {cp.record_index} hash '{event_at_idx.record_hash[:16]}' "
                    f"does not match signed checkpoint hash '{cp.record_hash[:16]}'."
                )
                continue

            valid_count += 1

        is_all_valid = (len(errors) == 0) and (valid_count > 0 or len(checkpoints_raw) == 0)
        return is_all_valid, valid_count, errors

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
        Computes SHA-256, runs authenticity analysis, binds DPAPI key fingerprint,
        digitally signs manifest, creates genesis checkpoint, and records custody event.
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

        # 2. Build signed manifest with key identity and fingerprint binding
        manifest = SignedEvidenceManifest(
            manifest_version="1.1",
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
            signer_identity=self.signer.identity,
            key_id=self.signer.key_id,
            key_fingerprint=self.signer.key_fingerprint,
            trust_status="TRUSTED_AUTHORITY",
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

        # 4. Chain of custody ledger - Genesis Record
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
                "key_id": self.signer.key_id,
                "key_fingerprint": self.signer.key_fingerprint,
            },
        )

        # 5. Create Genesis Checkpoint (Record Index 0)
        self.create_signed_checkpoint(evidence_id, operator_username, operator_role)

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
        2. Validates ECDSA digital signature and verifies public key in TrustedKeyStore.
        3. Validates custody ledger hash-chain.
        4. Validates independent external custody checkpoints.
        """
        self._check_permission(operator_role, self.ALLOWED_ROLES_VIEW, "VERIFY_EVIDENCE")

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

        # 1. Check media SHA-256
        current_sha256 = self.analyzer.compute_file_sha256(str(media_file))
        sha_valid = (current_sha256 == m_dict["file_sha256"])

        # 2. Check Key Trust and Digital Signature
        manifest_obj = SignedEvidenceManifest(**m_dict)
        pub_key_pem = manifest_obj.public_key_pem

        is_key_trusted, key_entry, trust_reason = self.signer.trust_store.is_key_trusted(pub_key_pem)

        canonical_bytes = manifest_obj.canonical_bytes_for_signing()
        sig_cryptographically_valid = self.signer.verify_signature(
            payload=canonical_bytes,
            signature_hex=manifest_obj.signature_hex,
            public_key_pem=pub_key_pem,
        )

        sig_valid = sig_cryptographically_valid and is_key_trusted

        # 3. Check Custody Chain
        chain_valid, chain_len, chain_err = ledger.verify_chain()

        # 4. Check External Checkpoints
        checkpoints_valid, cp_count, cp_errors = self.verify_checkpoints(evidence_id)

        overall_valid = sha_valid and sig_valid and chain_valid and checkpoints_valid

        # Publish forensic integrity failure to EventBus if tamper detected
        if not overall_valid:
            bus.publish(
                "forensic.integrity_failure",
                {
                    "evidence_id": evidence_id,
                    "sha256_match": sha_valid,
                    "signature_valid": sig_valid,
                    "custody_chain_valid": chain_valid,
                    "checkpoints_valid": checkpoints_valid,
                    "details": f"Evidence {evidence_id} verification failed: sha={sha_valid}, sig={sig_valid}, chain={chain_valid}",
                },
                source="evidence_locker",
            )

        # Record verification event in custody ledger
        action_name = "VERIFY" if overall_valid else "TAMPER_DETECTED"
        ledger.append_event(
            evidence_id=evidence_id,
            operator_username=operator_username,
            operator_role=operator_role,
            action=action_name,
            details={
                "sha256_match": sha_valid,
                "signature_valid": sig_valid,
                "key_trusted": is_key_trusted,
                "custody_chain_valid": chain_valid,
                "checkpoints_valid": checkpoints_valid,
                "records_inspected": chain_len,
                "checkpoints_inspected": cp_count,
            },
        )

        return {
            "evidence_id": evidence_id,
            "is_valid": overall_valid,
            "sha256_match": sha_valid,
            "signature_valid": sig_valid,
            "key_trusted": is_key_trusted,
            "trust_reason": trust_reason,
            "custody_chain_valid": chain_valid,
            "checkpoints_valid": checkpoints_valid,
            "checkpoint_errors": cp_errors,
            "records_count": chain_len,
            "evidence_type": manifest_obj.evidence_type,
            "file_name": manifest_obj.file_name,
            "source_sha256": manifest_obj.source_sha256,
        }

    def scan_locker_integrity(self, evidence_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Active integrity monitor: Scans evidence items in locker, verifies files,
        manifests, signatures, key trust, ledger chains, and external checkpoints.
        Logs any detected tamper events and returns audit findings.
        """
        targets = []
        if evidence_id:
            targets.append(self.base_dir / evidence_id)
        else:
            if self.base_dir.exists():
                for item_dir in self.base_dir.iterdir():
                    if item_dir.is_dir() and (item_dir / "manifest.json").exists():
                        targets.append(item_dir)

        audit_results = []
        for t in targets:
            eid = t.name
            try:
                res = self.verify_evidence(eid, "INTEGRITY_DAEMON", "ADMIN")
                audit_results.append(res)
            except Exception as e:
                audit_results.append({
                    "evidence_id": eid,
                    "is_valid": False,
                    "error": str(e),
                })
        return audit_results

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
