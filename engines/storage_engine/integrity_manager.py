"""
Storage Integrity and Recording Manifest Verification Manager.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

import os
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from database.database_manager import db_manager
from database.models.storage import StorageRecordingManifest
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("storage_integrity")


def compute_sha256(file_path: str) -> str:
    """Computes SHA-256 hash of a file on disk."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class StorageIntegrityManager:
    """
    Generates and verifies cryptographic manifests for recording segments,
    detects recording gaps and file corruption, and audits database-to-disk consistency.
    """

    def create_segment_manifest(
        self,
        channel_id: str,
        destination_volume_id: str,
        file_path: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        recording_id: Optional[str] = None,
        segment_id: Optional[str] = None,
        stream_id: str = "MAIN",
        sha256_hash: Optional[str] = None,
        file_size_bytes: int = 0,
        duration_sec: int = 0,
        is_failover: bool = False,
        failover_event_id: Optional[str] = None,
    ) -> StorageRecordingManifest:
        """Creates and stores an authoritative cryptographic manifest entry for a recording segment."""
        computed_hash = sha256_hash
        actual_size = file_size_bytes
        if os.path.exists(file_path):
            if actual_size == 0:
                actual_size = os.path.getsize(file_path)
            if not computed_hash and actual_size > 0:
                computed_hash = compute_sha256(file_path)

        manifest = StorageRecordingManifest(
            recording_id=recording_id,
            segment_id=segment_id,
            channel_id=channel_id,
            stream_id=stream_id,
            start_time=start_time,
            end_time=end_time or datetime.now(timezone.utc),
            destination_volume_id=destination_volume_id,
            file_path=file_path,
            sha256_hash=computed_hash,
            file_size_bytes=actual_size,
            duration_sec=duration_sec,
            is_failover=is_failover,
            failover_event_id=failover_event_id,
            verification_status="VERIFIED" if computed_hash else "UNVERIFIED",
        )

        with db_manager.get_session() as session:
            session.add(manifest)
            session.flush()
            _ = (manifest.id, manifest.channel_id, manifest.sha256_hash)
            session.expunge(manifest)

        logger.debug("Created recording manifest for [%s]: %s (Hash: %s)",
                     channel_id, file_path, computed_hash[:12] if computed_hash else "None")
        return manifest

    def verify_segment_manifest(self, manifest_id: str) -> Dict[str, Any]:
        """
        Cryptographically verifies a segment on disk against its stored manifest hash.
        Emits an alarm if tamper or file corruption is detected.
        """
        with db_manager.get_session() as session:
            manifest = session.query(StorageRecordingManifest).filter_by(id=manifest_id).first()
            if not manifest:
                return {"valid": False, "error": f"Manifest ID [{manifest_id}] not found."}

            if not os.path.exists(manifest.file_path):
                manifest.verification_status = "CORRUPT"
                bus.publish("storage.integrity_failure", {
                    "manifest_id": manifest.id,
                    "channel_id": manifest.channel_id,
                    "file_path": manifest.file_path,
                    "error": "File missing on disk",
                }, source="integrity_manager")
                return {"valid": False, "error": f"File missing on disk: {manifest.file_path}"}

            current_hash = compute_sha256(manifest.file_path)
            if current_hash != manifest.sha256_hash:
                manifest.verification_status = "CORRUPT"
                bus.publish("storage.integrity_failure", {
                    "manifest_id": manifest.id,
                    "channel_id": manifest.channel_id,
                    "file_path": manifest.file_path,
                    "stored_hash": manifest.sha256_hash,
                    "computed_hash": current_hash,
                    "error": "Cryptographic checksum mismatch",
                }, source="integrity_manager")
                logger.error("Integrity check failed for manifest %s: stored=%s, current=%s",
                             manifest.id, manifest.sha256_hash, current_hash)
                return {
                    "valid": False,
                    "stored_hash": manifest.sha256_hash,
                    "computed_hash": current_hash,
                    "details": "Cryptographic digest mismatch: file has been modified or corrupted.",
                }

            manifest.verification_status = "VERIFIED"
            return {
                "valid": True,
                "stored_hash": manifest.sha256_hash,
                "computed_hash": current_hash,
                "details": "Cryptographic digest match verified.",
            }

    def detect_recording_gaps(
        self,
        channel_id: str,
        start_time: datetime,
        end_time: datetime,
        max_allowed_gap_sec: float = 2.0,
    ) -> List[Dict[str, Any]]:
        """
        Scans chronological segment manifests for a camera and calculates timestamp discontinuities.
        Returns a list of detected recording gaps.
        """
        gaps = []
        with db_manager.get_session() as session:
            manifests = (
                session.query(StorageRecordingManifest)
                .filter(
                    StorageRecordingManifest.channel_id == channel_id,
                    StorageRecordingManifest.start_time >= start_time,
                    StorageRecordingManifest.start_time <= end_time,
                )
                .order_by(StorageRecordingManifest.start_time.asc())
                .all()
            )

            prev_end = None
            for m in manifests:
                if prev_end is not None:
                    delta = (m.start_time - prev_end).total_seconds()
                    if delta > max_allowed_gap_sec:
                        gaps.append({
                            "channel_id": channel_id,
                            "gap_start": prev_end.isoformat(),
                            "gap_end": m.start_time.isoformat(),
                            "gap_seconds": round(delta, 2),
                        })
                prev_end = m.end_time or (m.start_time + timedelta(seconds=m.duration_sec))

        return gaps
