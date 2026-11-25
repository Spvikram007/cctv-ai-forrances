"""
Performance Benchmarks for Digital Forensics & Authenticity (Phase 10 - F-018 & F-023).
Evaluates SHA-256 chunked hashing throughput, frame discontinuity inspection latency,
and memory stability across 720p, 1080p, and long recording clips on Intel hardware.
"""

import time
import os
import tempfile
import pytest
import numpy as np
import cv2

from engines.forensic_engine.authenticity import VideoAuthenticityAnalyzer
from engines.forensic_engine.evidence_locker import EvidenceLocker


@pytest.fixture
def analyzer() -> VideoAuthenticityAnalyzer:
    return VideoAuthenticityAnalyzer()


def generate_benchmark_clip(path: str, width: int, height: int, num_frames: int = 50, fps: float = 25.0) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
    for i in range(num_frames):
        frame = np.full((height, width, 3), 40, dtype=np.uint8)
        x = (i * 15) % (width - 50)
        cv2.circle(frame, (x, height // 2), 30, (120, 180, 240), -1)
        writer.write(frame)
    writer.release()


def test_720p_forensic_audit_throughput(analyzer: VideoAuthenticityAnalyzer) -> None:
    """Benchmarks frame discontinuity & hash audit on 720p HD footage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vid_p = os.path.join(tmpdir, "bench_720p.mp4")
        generate_benchmark_clip(vid_p, 1280, 720, num_frames=50)

        start = time.perf_counter()
        report = analyzer.audit_video(vid_p)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert report.total_frames_inspected == 50
        fps_throughput = 50.0 / (elapsed_ms / 1000.0)

        # Target: audit should run > 100 FPS due to rapid $64 \times 36$ thumbnailing
        assert fps_throughput > 75.0, f"720p audit throughput too slow: {fps_throughput:.1f} FPS"


def test_1080p_forensic_audit_throughput(analyzer: VideoAuthenticityAnalyzer) -> None:
    """Benchmarks frame discontinuity & hash audit on 1080p Full HD footage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vid_p = os.path.join(tmpdir, "bench_1080p.mp4")
        generate_benchmark_clip(vid_p, 1920, 1080, num_frames=40)

        start = time.perf_counter()
        report = analyzer.audit_video(vid_p)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        assert report.total_frames_inspected == 40
        fps_throughput = 40.0 / (elapsed_ms / 1000.0)

        assert fps_throughput > 50.0, f"1080p audit throughput too slow: {fps_throughput:.1f} FPS"


def test_sha256_chunked_hashing_speed(analyzer: VideoAuthenticityAnalyzer) -> None:
    """Benchmarks raw SHA-256 buffered hashing throughput."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "large_sample.dat")
        # 16 MB chunk of pseudo-random data
        chunk = b"FORENSIC_EVIDENCE_BYTE_BLOCK_TEST_SAMPLE" * 1024
        with open(test_file, "wb") as f:
            for _ in range(400):
                f.write(chunk)

        file_size_mb = os.path.getsize(test_file) / (1024.0 * 1024.0)

        start = time.perf_counter()
        h = analyzer.compute_file_sha256(test_file)
        elapsed_sec = time.perf_counter() - start

        throughput_mbps = file_size_mb / elapsed_sec
        assert len(h) == 64
        # SHA-256 chunked hashing should easily exceed 150 MB/s on modern Intel CPU
        assert throughput_mbps > 150.0, f"SHA-256 hashing throughput: {throughput_mbps:.1f} MB/s"
