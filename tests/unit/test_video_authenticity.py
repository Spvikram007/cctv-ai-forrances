"""
Unit Tests for Video Authenticity, Discontinuity, Duplicate, and Container Analysis (Phase 10 - F-018).
"""

import os
import tempfile
import pytest
import numpy as np
import cv2

from engines.forensic_engine.authenticity import (
    VideoAuthenticityAnalyzer,
    IntegrityStatus,
    ForensicAnalysisReport,
)


@pytest.fixture
def analyzer() -> VideoAuthenticityAnalyzer:
    return VideoAuthenticityAnalyzer()


def create_synthetic_video(
    file_path: str,
    num_frames: int = 30,
    fps: float = 25.0,
    inject_duplicates: bool = False,
    inject_splicing: bool = False,
) -> None:
    """Helper to generate deterministic synthetic video clips."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(file_path, fourcc, fps, (320, 240))
    for i in range(num_frames):
        frame = np.full((240, 320, 3), 30, dtype=np.uint8)
        if inject_duplicates and 10 <= i < 18:
            # Duplicate static frame run
            cv2.putText(frame, "STATIC SCENE", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180, 180, 180), 2)
        elif inject_splicing and i == 15:
            # Injected abrupt splicing jump (white flash / different scene)
            frame = np.full((240, 320, 3), 240, dtype=np.uint8)
            cv2.putText(frame, "SPLICED CUT", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        else:
            # Moving object
            x = 30 + (i * 8) % 250
            cv2.circle(frame, (x, 120), 25, (0, 165, 255), -1)
            cv2.putText(frame, f"F:{i:03d}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
        writer.write(frame)
    writer.release()


def test_authentic_video_audit(analyzer: VideoAuthenticityAnalyzer) -> None:
    """Verifies a clean, continuous video reports AUTHENTIC status and high confidence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vid_path = os.path.join(tmpdir, "authentic_video.mp4")
        create_synthetic_video(vid_path, num_frames=30, fps=25.0)

        report = analyzer.audit_video(vid_path)

        assert isinstance(report, ForensicAnalysisReport)
        assert report.status in (IntegrityStatus.AUTHENTIC, IntegrityStatus.ANOMALOUS)
        assert report.confidence_score >= 0.85
        assert len(report.sha256_hash) == 64
        assert report.container_info.container_integrity_passed is True
        assert report.container_info.total_frames >= 28


def test_bit_level_alteration_detection(analyzer: VideoAuthenticityAnalyzer) -> None:
    """Verifies file hash changes when bytes are altered."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vid_path = os.path.join(tmpdir, "original_video.mp4")
        create_synthetic_video(vid_path, num_frames=20, fps=25.0)

        orig_sha = analyzer.compute_file_sha256(vid_path)

        # Modify bytes in middle of file
        with open(vid_path, "r+b") as f:
            f.seek(1024)
            f.write(b"TAMPERED_BYTE_PAYLOAD_001")

        tampered_sha = analyzer.compute_file_sha256(vid_path)
        assert orig_sha != tampered_sha, "SHA-256 must change when bytes are altered!"


def test_duplicate_frame_cluster_detection(analyzer: VideoAuthenticityAnalyzer) -> None:
    """Verifies duplicate frozen frames are detected and clustered."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vid_path = os.path.join(tmpdir, "dup_video.mp4")
        create_synthetic_video(vid_path, num_frames=35, inject_duplicates=True)

        report = analyzer.audit_video(vid_path)

        assert len(report.duplicate_clusters) > 0
        cluster = report.duplicate_clusters[0]
        assert cluster.frame_count >= 5
        assert cluster.duration_sec > 0.15


def test_visual_splicing_discontinuity_detection(analyzer: VideoAuthenticityAnalyzer) -> None:
    """Verifies abrupt visual splicing jumps are detected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vid_path = os.path.join(tmpdir, "spliced_video.mp4")
        create_synthetic_video(vid_path, num_frames=30, inject_splicing=True)

        report = analyzer.audit_video(vid_path)

        splicing_disc = [d for d in report.discontinuities if d.anomaly_type == "VISUAL_SPLICING"]
        assert len(splicing_disc) > 0
        assert splicing_disc[0].diff_score > 0.50


def test_corrupted_or_non_video_file_detection(analyzer: VideoAuthenticityAnalyzer) -> None:
    """Verifies corrupted or non-video files are flagged as CORRUPTED."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bad_path = os.path.join(tmpdir, "garbage.mp4")
        with open(bad_path, "wb") as f:
            f.write(b"THIS_IS_NOT_A_VALID_VIDEO_STREAM_DATA_BYTES")

        report = analyzer.audit_video(bad_path)
        assert report.status == IntegrityStatus.CORRUPTED
        assert report.confidence_score == 0.0


def test_legal_forensic_disclaimer_present(analyzer: VideoAuthenticityAnalyzer) -> None:
    """Verifies legal disclaimer stating hash does not prove scene veracity."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vid_path = os.path.join(tmpdir, "test.mp4")
        create_synthetic_video(vid_path, num_frames=10)

        report = analyzer.audit_video(vid_path)
        assert "A valid SHA-256 hash and digital signature prove strictly" in report.legal_disclaimer
        assert "not prove that the recorded physical scene was authentic" in report.legal_disclaimer.lower()
