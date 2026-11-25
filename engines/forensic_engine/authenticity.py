"""
Video Authenticity, Discontinuity, Duplicate, and Container Analysis (Phase 10 - F-018).
Performs file SHA-256 integrity verification, frame discontinuity and duplicate detection,
missing-frame & timestamp anomaly analysis, container/codec atom inspection, and generates
standardized forensic authenticity reports.
"""

import os
import hashlib
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum

import cv2
import numpy as np

from core.logging.logger import get_logger

logger = get_logger("forensic_authenticity")


class IntegrityStatus(str, Enum):
    AUTHENTIC = "AUTHENTIC"
    ANOMALOUS = "ANOMALOUS"
    SUSPICIOUS = "SUSPICIOUS"
    TAMPERED = "TAMPERED"
    CORRUPTED = "CORRUPTED"


@dataclass
class FrameDiscontinuity:
    """Represents a detected visual or sequence discontinuity."""
    frame_index: int
    timestamp_sec: float
    gap_sec: float
    diff_score: float
    anomaly_type: str  # "VISUAL_SPLICING", "DROPPED_FRAMES", "TIMELINE_GAP"
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DuplicateFrameCluster:
    """Represents a cluster of identical or frozen consecutive frames."""
    start_frame: int
    end_frame: int
    frame_count: int
    start_sec: float
    end_sec: float
    duration_sec: float
    avg_diff: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TimestampAnomaly:
    """Represents an anomaly in Presentation Time Stamp (PTS) cadence."""
    frame_index: int
    expected_pts: float
    actual_pts: float
    deviation_sec: float
    anomaly_type: str  # "TIMESTAMP_GAP", "TIMESTAMP_REVERSAL", "CLOCK_DRIFT"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ContainerMetadata:
    """Extracted container, codec, and header atom metadata."""
    file_format: str
    codec_fourcc: str
    duration_sec: float
    nominal_fps: float
    resolution: Tuple[int, int]
    total_frames: int
    bitrate_kbps: int
    atoms_found: List[str]
    container_integrity_passed: bool
    container_notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ForensicAnalysisReport:
    """Comprehensive forensic report covering file integrity, frames, and container."""
    file_path: str
    file_size_bytes: int
    sha256_hash: str
    container_info: ContainerMetadata
    status: IntegrityStatus
    confidence_score: float
    total_frames_inspected: int
    discontinuities: List[FrameDiscontinuity]
    duplicate_clusters: List[DuplicateFrameCluster]
    timestamp_anomalies: List[TimestampAnomaly]
    missing_frames_estimated: int
    analyzed_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    legal_disclaimer: str = (
        "FORENSIC INTEGRITY NOTICE: A valid SHA-256 hash and digital signature prove strictly "
        "that the acquired digital file has not been altered, truncated, or tampered with since acquisition. "
        "Cryptographic verification does NOT prove that the recorded physical scene was authentic or un-staged "
        "prior to sensor capture."
    )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class VideoAuthenticityAnalyzer:
    """
    Forensic engine analyzing digital video authenticity, container structure,
    frame continuity, duplicate runs, and timestamp cadences.
    """

    def __init__(
        self,
        duplicate_threshold: float = 0.002,
        duplicate_min_frames: int = 5,
        discontinuity_diff_threshold: float = 0.65,
        timestamp_gap_factor: float = 1.5,
    ) -> None:
        self.duplicate_threshold = duplicate_threshold
        self.duplicate_min_frames = duplicate_min_frames
        self.discontinuity_diff_threshold = discontinuity_diff_threshold
        self.timestamp_gap_factor = timestamp_gap_factor

    @staticmethod
    def compute_file_sha256(file_path: str, chunk_size: int = 1048576) -> str:
        """Computes SHA-256 digest of a file in buffered chunks or using optimized file_digest."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if hasattr(hashlib, "file_digest"):
            with open(p, "rb") as f:
                return hashlib.file_digest(f, "sha256").hexdigest()

        hasher = hashlib.sha256()
        with open(p, "rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()

    def inspect_container(self, file_path: str) -> ContainerMetadata:
        """Inspects container header atoms, file signature, and codec metadata."""
        p = Path(file_path)
        file_size = p.stat().st_size
        notes: List[str] = []
        atoms_found: List[str] = []
        file_format = p.suffix.lower().replace(".", "").upper()
        container_passed = True

        # Binary header inspection
        with open(p, "rb") as f:
            header_sample = f.read(min(file_size, 4096))

        # Check standard container signatures
        if header_sample.startswith(b"\x1a\x45\xdf\xa3"):
            file_format = "MKV/WEBM"
            atoms_found.append("EBML_HEADER")
        elif b"ftyp" in header_sample[:32]:
            file_format = "MP4/MOV"
            atoms_found.append("ftyp")
            # Parse major brand
            idx = header_sample.find(b"ftyp")
            if idx + 8 <= len(header_sample):
                brand = header_sample[idx + 4 : idx + 8].decode("latin-1", errors="ignore")
                notes.append(f"MP4 Major Brand: {brand}")
        elif header_sample.startswith(b"RIFF") and b"AVI " in header_sample[8:16]:
            file_format = "AVI"
            atoms_found.append("RIFF_AVI")
        elif header_sample.startswith(b"\x00\x00\x01\xba") or header_sample.startswith(b"G"):
            file_format = "MPEG_TS"
            atoms_found.append("TS_SYNC")
        else:
            notes.append("Non-standard or unrecognized container header signature.")
            container_passed = False

        # OpenCV inspection for stream tracks
        cap = cv2.VideoCapture(str(p))
        if not cap.isOpened():
            notes.append("Video stream could not be opened by media decoder.")
            return ContainerMetadata(
                file_format=file_format,
                codec_fourcc="UNKNOWN",
                duration_sec=0.0,
                nominal_fps=0.0,
                resolution=(0, 0),
                total_frames=0,
                bitrate_kbps=0,
                atoms_found=atoms_found,
                container_integrity_passed=False,
                container_notes=notes,
            )

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
        cap.release()

        codec_str = "".join([chr((fourcc_int >> (8 * i)) & 0xFF) for i in range(4)]).strip()
        if not codec_str or any(ord(c) < 32 or ord(c) > 126 for c in codec_str):
            codec_str = "H264/AVC"

        duration_sec = (total_frames / fps) if (fps > 0 and total_frames > 0) else 0.0
        bitrate_kbps = int((file_size * 8.0) / (duration_sec * 1000.0)) if duration_sec > 0 else 0

        # Check for truncated or empty video stream
        if total_frames <= 0 or w <= 0 or h <= 0:
            notes.append("Zero frame count or invalid dimensions reported.")
            container_passed = False

        return ContainerMetadata(
            file_format=file_format,
            codec_fourcc=codec_str,
            duration_sec=round(duration_sec, 2),
            nominal_fps=round(fps, 2),
            resolution=(w, h),
            total_frames=total_frames,
            bitrate_kbps=bitrate_kbps,
            atoms_found=atoms_found,
            container_integrity_passed=container_passed,
            container_notes=notes,
        )

    def audit_video(
        self,
        video_path: str,
        max_frames: Optional[int] = None,
        sample_stride: int = 1,
    ) -> ForensicAnalysisReport:
        """
        Runs comprehensive forensic audit on a video file.
        Detects hash, container metadata, frame discontinuities, duplicate runs,
        and timestamp cadence anomalies.
        """
        p = Path(video_path)
        if not p.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        file_size = p.stat().st_size
        sha256_hash = self.compute_file_sha256(str(p))
        container_info = self.inspect_container(str(p))

        if not container_info.container_integrity_passed and container_info.total_frames == 0:
            return ForensicAnalysisReport(
                file_path=str(p.resolve()),
                file_size_bytes=file_size,
                sha256_hash=sha256_hash,
                container_info=container_info,
                status=IntegrityStatus.CORRUPTED,
                confidence_score=0.0,
                total_frames_inspected=0,
                discontinuities=[],
                duplicate_clusters=[],
                timestamp_anomalies=[],
                missing_frames_estimated=0,
            )

        cap = cv2.VideoCapture(str(p))
        fps = container_info.nominal_fps if container_info.nominal_fps > 0 else 25.0
        expected_dt = 1.0 / fps

        discontinuities: List[FrameDiscontinuity] = []
        duplicate_clusters: List[DuplicateFrameCluster] = []
        timestamp_anomalies: List[TimestampAnomaly] = []

        prev_gray_thumb: Optional[np.ndarray] = None
        prev_pts: float = -1.0
        frame_idx = 0
        inspected_count = 0
        missing_frames_total = 0

        # Duplicate tracking state
        dup_start_frame = -1
        dup_start_sec = 0.0
        dup_count = 0
        dup_diff_sum = 0.0

        thumb_w, thumb_h = 64, 36

        while True:
            if max_frames is not None and inspected_count >= max_frames:
                break

            ret, frame = cap.read()
            if not ret or frame is None:
                break

            # Current timestamp in seconds
            pts_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
            pts_sec = (pts_msec / 1000.0) if pts_msec >= 0 else (frame_idx * expected_dt)

            # Rapid downscaled thumbnail for perceptual difference ($64 \times 36$)
            small = cv2.resize(frame, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

            if prev_gray_thumb is not None:
                # 1. Perceptual normalized mean absolute difference
                diff_score = float(np.mean(np.abs(gray.astype(np.float32) - prev_gray_thumb.astype(np.float32))) / 255.0)

                # 2. Duplicate Frame Analysis
                if diff_score < self.duplicate_threshold:
                    if dup_count == 0:
                        dup_start_frame = frame_idx - 1
                        dup_start_sec = prev_pts
                        dup_count = 2
                        dup_diff_sum = diff_score
                    else:
                        dup_count += 1
                        dup_diff_sum += diff_score
                else:
                    if dup_count >= self.duplicate_min_frames:
                        duplicate_clusters.append(
                            DuplicateFrameCluster(
                                start_frame=dup_start_frame,
                                end_frame=frame_idx - 1,
                                frame_count=dup_count,
                                start_sec=round(dup_start_sec, 3),
                                end_sec=round(prev_pts, 3),
                                duration_sec=round(prev_pts - dup_start_sec, 3),
                                avg_diff=round(dup_diff_sum / (dup_count - 1), 5),
                            )
                        )
                    dup_count = 0

                # 3. Timestamp Cadence Analysis
                dt = pts_sec - prev_pts

                # Check timestamp reversal
                if dt < -0.005:
                    timestamp_anomalies.append(
                        TimestampAnomaly(
                            frame_index=frame_idx,
                            expected_pts=round(prev_pts + expected_dt, 3),
                            actual_pts=round(pts_sec, 3),
                            deviation_sec=round(dt, 3),
                            anomaly_type="TIMESTAMP_REVERSAL",
                        )
                    )
                # Check timestamp gap (dropped / missing frames)
                elif dt > (expected_dt * self.timestamp_gap_factor):
                    gap_sec = dt
                    dropped_count = max(1, int(round(gap_sec / expected_dt)) - 1)
                    missing_frames_total += dropped_count

                    timestamp_anomalies.append(
                        TimestampAnomaly(
                            frame_index=frame_idx,
                            expected_pts=round(prev_pts + expected_dt, 3),
                            actual_pts=round(pts_sec, 3),
                            deviation_sec=round(gap_sec, 3),
                            anomaly_type="TIMESTAMP_GAP",
                        )
                    )

                    # Also classify as frame discontinuity
                    discontinuities.append(
                        FrameDiscontinuity(
                            frame_index=frame_idx,
                            timestamp_sec=round(pts_sec, 3),
                            gap_sec=round(gap_sec, 3),
                            diff_score=round(diff_score, 4),
                            anomaly_type="DROPPED_FRAMES",
                            description=f"Timeline gap of {gap_sec:.3f}s detected (~{dropped_count} missing frames).",
                        )
                    )

                # 4. Abrupt Visual Splicing Jump (without timeline gap, indicates spliced content)
                elif diff_score > self.discontinuity_diff_threshold:
                    discontinuities.append(
                        FrameDiscontinuity(
                            frame_index=frame_idx,
                            timestamp_sec=round(pts_sec, 3),
                            gap_sec=round(dt, 3),
                            diff_score=round(diff_score, 4),
                            anomaly_type="VISUAL_SPLICING",
                            description=f"Abrupt visual scene jump (diff={diff_score:.3f}) without timestamp omission.",
                        )
                    )

            prev_gray_thumb = gray
            prev_pts = pts_sec
            frame_idx += 1
            inspected_count += 1

        cap.release()

        # Flush any trailing duplicate cluster
        if dup_count >= self.duplicate_min_frames:
            duplicate_clusters.append(
                DuplicateFrameCluster(
                    start_frame=dup_start_frame,
                    end_frame=frame_idx - 1,
                    frame_count=dup_count,
                    start_sec=round(dup_start_sec, 3),
                    end_sec=round(prev_pts, 3),
                    duration_sec=round(prev_pts - dup_start_sec, 3),
                    avg_diff=round(dup_diff_sum / (dup_count - 1), 5),
                )
            )

        # Compute overall forensic confidence and status
        status, confidence = self._evaluate_status(
            container_info=container_info,
            discontinuities=discontinuities,
            duplicate_clusters=duplicate_clusters,
            timestamp_anomalies=timestamp_anomalies,
            total_frames=inspected_count,
        )

        return ForensicAnalysisReport(
            file_path=str(p.resolve()),
            file_size_bytes=file_size,
            sha256_hash=sha256_hash,
            container_info=container_info,
            status=status,
            confidence_score=confidence,
            total_frames_inspected=inspected_count,
            discontinuities=discontinuities,
            duplicate_clusters=duplicate_clusters,
            timestamp_anomalies=timestamp_anomalies,
            missing_frames_estimated=missing_frames_total,
        )

    @staticmethod
    def _evaluate_status(
        container_info: ContainerMetadata,
        discontinuities: List[FrameDiscontinuity],
        duplicate_clusters: List[DuplicateFrameCluster],
        timestamp_anomalies: List[TimestampAnomaly],
        total_frames: int,
    ) -> Tuple[IntegrityStatus, float]:
        """Evaluates integrity status and confidence score."""
        if not container_info.container_integrity_passed or total_frames == 0:
            return IntegrityStatus.CORRUPTED, 0.0

        # Check for timestamp reversals (severe indicator of tampering / incorrect remux)
        reversals = [a for a in timestamp_anomalies if a.anomaly_type == "TIMESTAMP_REVERSAL"]
        if reversals:
            return IntegrityStatus.TAMPERED, 0.35

        # Check for visual splicing jumps
        splicing_jumps = [d for d in discontinuities if d.anomaly_type == "VISUAL_SPLICING"]
        if len(splicing_jumps) >= 3:
            return IntegrityStatus.SUSPICIOUS, 0.50

        # Check for extensive frozen frame clusters
        total_dup_frames = sum(c.frame_count for c in duplicate_clusters)
        dup_ratio = (total_dup_frames / float(total_frames)) if total_frames > 0 else 0.0

        if dup_ratio > 0.40:
            return IntegrityStatus.SUSPICIOUS, 0.60

        # Dropped frames / network jitter anomalies
        if len(discontinuities) > 0 or len(timestamp_anomalies) > 0 or dup_ratio > 0.10:
            confidence = max(0.65, 1.0 - (len(discontinuities) * 0.05) - (dup_ratio * 0.2))
            return IntegrityStatus.ANOMALOUS, round(confidence, 2)

        return IntegrityStatus.AUTHENTIC, 0.99
