"""
Multi-Tier Archival and Evidentiary Protection Manager.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

import os
import shutil
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from database.database_manager import db_manager
from database.models.recordings import Recording, RecordingSegment, StorageVolume
from database.models.storage import StorageArchivalJob, StorageArchivalCopy
from engines.storage_engine.enums import ArchivalTier, ArchivalJobStatus
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("storage_archival")


def compute_file_sha256(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class StorageArchivalManager:
    """
    Manages multi-tier lifecycle migration (Hot -> Warm -> Cold), copy verification,
    restoration, and strict evidentiary hold preservation.
    """

    def create_archival_job(
        self,
        source_volume_id: str,
        target_volume_id: str,
        target_tier: ArchivalTier = ArchivalTier.COLD,
        min_age_days: int = 14,
        max_files: int = 50,
    ) -> Dict[str, Any]:
        """
        Executes a scheduled tier migration job with end-to-end cryptographic verification.
        NEVER deletes source recordings until destination hash match is verified.
        NEVER deletes or invalidates locked forensic evidence (is_locked=True).
        """
        now = datetime.now(timezone.utc)
        cutoff_date = now - timedelta(days=min_age_days)

        with db_manager.get_session() as session:
            job = StorageArchivalJob(
                source_volume_id=source_volume_id,
                target_volume_id=target_volume_id,
                target_tier=target_tier.value,
                status=ArchivalJobStatus.IN_PROGRESS.value,
                started_at=now,
            )
            session.add(job)
            session.flush()
            job_id = str(job.id)

            target_vol = session.query(StorageVolume).filter_by(id=target_volume_id).first()
            if not target_vol or not os.path.exists(target_vol.mount_path):
                job.status = ArchivalJobStatus.FAILED.value
                job.error_message = f"Target archival volume [{target_volume_id}] is missing or offline."
                job.completed_at = datetime.now(timezone.utc)
                bus.publish("storage.archival_failure", {
                    "job_id": job_id,
                    "error": job.error_message,
                }, source="archival_manager")
                return {"status": "FAILED", "error": job.error_message}

            target_mount = target_vol.mount_path

            # Query candidate recordings older than cutoff
            candidates = (
                session.query(Recording)
                .filter(
                    Recording.volume_id == source_volume_id,
                    Recording.end_time != None,
                    Recording.end_time < cutoff_date,
                    Recording.status == "COMPLETED",
                )
                .order_by(Recording.end_time.asc())
                .limit(max_files)
                .all()
            )

            job.total_files = len(candidates)
            transferred_count = 0
            transferred_bytes = 0
            failed_count = 0

            for rec in candidates:
                src_path = rec.file_path
                if not os.path.exists(src_path):
                    continue

                src_hash = rec.sha256_hash or compute_file_sha256(src_path)
                file_size = os.path.getsize(src_path)

                # Determine relative path structure
                rel_path = os.path.relpath(src_path, start=os.path.dirname(os.path.dirname(src_path)))
                dest_path = os.path.join(target_mount, target_tier.value.lower(), rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)

                try:
                    # Stream copy to archive tier
                    shutil.copy2(src_path, dest_path)
                    dest_hash = compute_file_sha256(dest_path)

                    # Cryptographic verification check
                    if dest_hash != src_hash:
                        failed_count += 1
                        if os.path.exists(dest_path):
                            os.remove(dest_path)
                        logger.error("Archival copy failed hash check for %s (src=%s, dst=%s)", src_path, src_hash, dest_hash)
                        continue

                    # Record verified archival copy
                    arch_copy = StorageArchivalCopy(
                        recording_id=str(rec.id),
                        job_id=job_id,
                        target_volume_id=target_volume_id,
                        archive_path=dest_path,
                        tier=target_tier.value,
                        sha256_hash=dest_hash,
                        status="VERIFIED",
                    )
                    session.add(arch_copy)

                    # Evidence protection guarantee:
                    # If recording is NOT locked, we can update volume and remove hot source
                    if not rec.is_locked:
                        rec.volume_id = target_volume_id
                        rec.file_path = dest_path
                        try:
                            os.remove(src_path)
                        except Exception as e:
                            logger.warning("Could not prune source after archival: %s", e)
                    else:
                        # LOCKED FORENSIC EVIDENCE: retain original source and leave lock intact!
                        logger.info("Preserving original source for locked evidence recording [%s]", rec.id)

                    transferred_count += 1
                    transferred_bytes += file_size
                except Exception as e:
                    failed_count += 1
                    logger.error("Error migrating recording %s: %s", src_path, e)

            job.files_transferred = transferred_count
            job.bytes_transferred = transferred_bytes
            job.verification_failed_count = failed_count
            job.status = ArchivalJobStatus.COMPLETED.value if failed_count == 0 else ArchivalJobStatus.FAILED.value
            job.completed_at = datetime.now(timezone.utc)

        logger.info("Archival job %s finished: %d transferred, %d failed (%.2f MB)",
                    job_id, transferred_count, failed_count, transferred_bytes / (1024 * 1024))
        return {
            "job_id": job_id,
            "status": "COMPLETED" if failed_count == 0 else "PARTIAL",
            "files_transferred": transferred_count,
            "bytes_transferred": transferred_bytes,
            "verification_failed_count": failed_count,
        }

    def restore_archival_copy(
        self,
        recording_id: str,
        destination_volume_id: str,
        operator: str = "INVESTIGATOR",
    ) -> Tuple[bool, str]:
        """Restores an archived copy from cold/warm tier back to hot playback storage."""
        with db_manager.get_session() as session:
            arch_copy = (
                session.query(StorageArchivalCopy)
                .filter_by(recording_id=recording_id, status="VERIFIED")
                .first()
            )
            if not arch_copy or not os.path.exists(arch_copy.archive_path):
                return False, f"Archived copy not found for recording [{recording_id}]."

            dest_vol = session.query(StorageVolume).filter_by(id=destination_volume_id).first()
            if not dest_vol or not os.path.exists(dest_vol.mount_path):
                return False, f"Restore destination volume [{destination_volume_id}] is unavailable."

            # Verify archive copy checksum before restore
            curr_hash = compute_file_sha256(arch_copy.archive_path)
            if curr_hash != arch_copy.sha256_hash:
                return False, "Archival copy checksum mismatch: archive media corruption detected."

            # Copy back to destination volume
            filename = os.path.basename(arch_copy.archive_path)
            restore_dir = os.path.join(dest_vol.mount_path, "restored")
            os.makedirs(restore_dir, exist_ok=True)
            restored_path = os.path.join(restore_dir, filename)

            shutil.copy2(arch_copy.archive_path, restored_path)

            # Update recording record
            rec = session.query(Recording).filter_by(id=recording_id).first()
            if rec:
                rec.file_path = restored_path
                rec.volume_id = destination_volume_id

        logger.info("Restored recording [%s] to hot storage: %s by %s", recording_id, restored_path, operator)
        return True, f"Recording successfully restored to [{restored_path}]."
