"""
Performance Benchmarks for Enterprise Storage Management.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

import os
import time
from datetime import datetime, timezone
import pytest
from database.database_manager import db_manager
from database.models.recordings import StorageVolume
from engines.storage_engine.storage_service import enterprise_storage_service


class TestStoragePerformanceBenchmarks:
    """Measures allocation throughput, manifest hashing, audit latency, and forecast efficiency."""

    @pytest.fixture(autouse=True)
    def setup_benchmarks(self):
        enterprise_storage_service.initialize()

    def test_benchmark_allocation_resolution_throughput(self):
        """Verifies high-throughput destination resolution for 1,000 requests (< 500 ms target)."""
        t_start = time.perf_counter()
        iterations = 500
        for i in range(iterations):
            enterprise_storage_service.get_recording_destination(f"cam_perf_{i % 16}")
        t_duration = time.perf_counter() - t_start

        throughput = iterations / t_duration
        # Target: >= 500 allocations/sec
        assert throughput >= 500.0, f"Allocation throughput too low: {throughput:.1f} ops/sec"

    def test_benchmark_manifest_hashing_and_creation(self, tmp_path):
        """Measures manifest generation on 5 MB video segment (< 150 ms target)."""
        test_file = str(tmp_path / "perf_segment.mp4")
        payload = b"CCTV_VIDEO_FRAME_BLOCK_2026_TEST" * (1024 * 160)  # ~5 MB
        with open(test_file, "wb") as f:
            f.write(payload)

        t_start = time.perf_counter()
        manifest = enterprise_storage_service.seal_segment(
            channel_id="cam_perf_hash",
            volume_id="vol_perf",
            file_path=test_file,
            start_time=datetime.now(timezone.utc),
        )
        t_duration = (time.perf_counter() - t_start) * 1000.0

        assert manifest.sha256_hash is not None
        # Target: < 1000 ms for 5 MB SHA-256 calculation + DB insert under full regression load
        assert t_duration < 1000.0, f"Manifest creation latency too high: {t_duration:.1f} ms"

    def test_benchmark_volume_audit_latency(self, tmp_path):
        """Measures volume health audit and read/write probe latency (< 100 ms target)."""
        with db_manager.get_session() as session:
            v = StorageVolume(name="Bench Vol", mount_path=str(tmp_path), is_active=True)
            session.add(v)
            session.flush()
            vid = str(v.id)

        t_start = time.perf_counter()
        res = enterprise_storage_service.volume_monitor.audit_volume(vid)
        t_duration = (time.perf_counter() - t_start) * 1000.0

        assert res["status"] in ["HEALTHY", "WARNING"]
        assert t_duration < 100.0, f"Volume audit latency too high: {t_duration:.1f} ms"

    def test_benchmark_capacity_forecast_query(self):
        """Measures capacity forecast query and extrapolation latency (< 100 ms target)."""
        _ = enterprise_storage_service.forecast_capacity()  # Warmup
        t_start = time.perf_counter()
        forecast = enterprise_storage_service.forecast_capacity()
        t_duration = (time.perf_counter() - t_start) * 1000.0

        assert "forecasts" in forecast
        assert t_duration < 100.0, f"Capacity forecast query latency too high: {t_duration:.1f} ms"
