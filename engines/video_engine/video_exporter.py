"""
Video Export Engine.
Extracts time-bounded MP4 video clips across single or multiple recording segments,
computes cryptographic SHA-256 hashes, generates audit metadata manifests,
and locks source footage when exported as legal/forensic evidence.
"""

import os
import json
import hashlib
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Dict, Any, List
import cv2

from database.database_manager import db_manager
from database.models.recordings import Recording, RecordingSegment, ExportJob
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("video_exporter")


def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensures datetime object is UTC timezone-aware."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class VideoExporter:
    """Manages MP4 clip extraction, forensic verification, and export metadata generation."""

    @staticmethod
    def _calculate_sha256(file_path: str) -> str:
        """Computes SHA-256 hash of a file using chunked streaming."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def export_clip(
        self,
        channel_id: str,
        start_time: datetime,
        end_time: datetime,
        output_path: str,
        is_evidence: bool = False,
        created_by: Optional[str] = None,
        notes: Optional[str] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> ExportJob:
        """
        Exports a video clip between start_time and end_time for the specified channel.
        Creates an ExportJob record, writes the concatenated MP4, calculates the SHA-256
        audit hash, generates a forensic JSON manifest, and preserves evidence if requested.
        """
        start_time = to_utc(start_time)
        end_time = to_utc(end_time)

        if end_time <= start_time:
            raise ValueError(f"end_time ({end_time}) must be after start_time ({start_time})")

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # 1. Create ExportJob record
        with db_manager.get_session() as session:
            job = ExportJob(
                channel_id=channel_id,
                start_time=start_time,
                end_time=end_time,
                destination_path=output_path,
                is_evidence=is_evidence,
                created_by=created_by,
                status="PROCESSING",
                progress_pct=0.0,
            )
            session.add(job)
            session.flush()
            job_id = job.id

        logger.info("Starting video export job %s for [%s] (%s to %s)", job_id, channel_id, start_time, end_time)

        # 2. Query source recording segments
        source_segments_info: List[Dict[str, Any]] = []
        with db_manager.get_session() as session:
            all_segments = (
                session.query(RecordingSegment)
                .join(Recording)
                .filter(Recording.channel_id == channel_id)
                .order_by(RecordingSegment.start_time.asc())
                .all()
            )

            segments = []
            for seg in all_segments:
                s_start = to_utc(seg.start_time)
                s_end = to_utc(seg.end_time)
                if s_start and s_end and s_start <= end_time and s_end >= start_time:
                    segments.append(seg)

            if not segments:
                with db_manager.get_session() as upd_session:
                    db_job = upd_session.query(ExportJob).filter_by(id=job_id).first()
                    if db_job:
                        db_job.status = "FAILED"
                        db_job.error_message = "No recording segments found in selected time range."
                logger.warning("Export job %s failed: No footage found for [%s]", job_id, channel_id)
                raise RuntimeError(f"No recording segments found for channel '{channel_id}' in selected time range.")

            for seg in segments:
                source_segments_info.append({
                    "id": seg.id,
                    "recording_id": seg.recording_id,
                    "file_path": seg.file_path,
                    "start_time": seg.start_time.isoformat() if seg.start_time else None,
                    "end_time": seg.end_time.isoformat() if seg.end_time else None,
                    "sha256": seg.sha256_hash,
                })

                if is_evidence and seg.recording:
                    # Lock parent recording to prevent automatic retention deletion
                    seg.recording.is_locked = True

        # 3. Process video extraction
        writer: Optional[cv2.VideoWriter] = None
        total_frames_written = 0
        total_segments = len(source_segments_info)

        try:
            for seg_idx, seg_meta in enumerate(source_segments_info):
                if cancel_event and cancel_event.is_set():
                    logger.info("Export job %s cancelled by user request.", job_id)
                    with db_manager.get_session() as session:
                        db_job = session.query(ExportJob).filter_by(id=job_id).first()
                        if db_job:
                            db_job.status = "CANCELLED"
                            db_job.error_message = "Export cancelled by user."
                            session.commit()
                            _ = (db_job.id, db_job.status)
                            session.expunge(db_job)
                    if writer:
                        writer.release()
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    return db_job

                fpath = seg_meta["file_path"]
                if not os.path.exists(fpath):
                    logger.warning("Segment file missing during export: %s", fpath)
                    continue

                cap = cv2.VideoCapture(fpath)
                if not cap.isOpened():
                    continue

                fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

                if writer is None:
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

                seg_start = to_utc(datetime.fromisoformat(seg_meta["start_time"])) if seg_meta["start_time"] else start_time

                frame_idx = 0
                while True:
                    if cancel_event and cancel_event.is_set():
                        break

                    ret, frame = cap.read()
                    if not ret or frame is None:
                        break

                    frame_time = seg_start + timedelta(seconds=frame_idx / fps)
                    frame_idx += 1

                    if start_time <= frame_time <= end_time:
                        if frame.shape[1] != width or frame.shape[0] != height:
                            frame = cv2.resize(frame, (width, height))
                        writer.write(frame)
                        total_frames_written += 1

                cap.release()

                # Report progress
                pct = round(((seg_idx + 1) / total_segments) * 90.0, 1)
                if progress_callback:
                    progress_callback(pct)

                with db_manager.get_session() as session:
                    db_job = session.query(ExportJob).filter_by(id=job_id).first()
                    if db_job:
                        db_job.progress_pct = pct

            if writer:
                writer.release()
                writer = None

            if total_frames_written == 0:
                raise RuntimeError("No matching frames found within requested bounds.")

            # 4. Compute file hash and metadata manifest
            file_size = os.path.getsize(output_path)
            sha256_hash = self._calculate_sha256(output_path)

            manifest = {
                "export_id": job_id,
                "channel_id": channel_id,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": round(total_frames_written / 25.0, 2),
                "total_frames": total_frames_written,
                "file_path": output_path,
                "file_size_bytes": file_size,
                "sha256_hash": sha256_hash,
                "is_evidence": is_evidence,
                "notes": notes or "",
                "created_by": created_by or "SYSTEM",
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "source_segments": source_segments_info,
            }

            manifest_path = f"{os.path.splitext(output_path)[0]}_manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)

            # 5. Mark ExportJob COMPLETED
            with db_manager.get_session() as session:
                db_job = session.query(ExportJob).filter_by(id=job_id).first()
                if db_job:
                    db_job.status = "COMPLETED"
                    db_job.progress_pct = 100.0
                    db_job.file_size_bytes = file_size
                    db_job.sha256_hash = sha256_hash

            if progress_callback:
                progress_callback(100.0)

            bus.publish("export.completed", {
                "job_id": job_id,
                "channel_id": channel_id,
                "output_path": output_path,
                "sha256": sha256_hash,
                "is_evidence": is_evidence,
            })
            logger.info("Export job %s completed successfully: %s (SHA-256: %s)", job_id, output_path, sha256_hash)

            # Re-read final job
            with db_manager.get_session() as session:
                final_job = session.query(ExportJob).filter_by(id=job_id).first()
                if final_job:
                    _ = (final_job.id, final_job.channel_id, final_job.status, final_job.file_size_bytes,
                         final_job.sha256_hash, final_job.destination_path, final_job.progress_pct)
                    session.expunge(final_job)
                return final_job

        except Exception as exc:
            if writer:
                writer.release()
            logger.error("Export job %s encountered error: %s", job_id, exc)
            with db_manager.get_session() as session:
                db_job = session.query(ExportJob).filter_by(id=job_id).first()
                if db_job:
                    db_job.status = "FAILED"
                    db_job.error_message = str(exc)
            raise


# Global exporter instance
video_exporter = VideoExporter()
