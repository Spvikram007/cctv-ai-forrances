"""
Performance and Scalability Benchmarks for Multi-Stream Engine (1 to 64 Channels).
Evaluates memory stability, queue occupancy, frame dispatch latency, and backpressure.

NOTE: 64-channel tests are synthetic software benchmarks measuring thread/queue/memory
scalability without physical RTSP network bottlenecks. Physical deployment readiness
depends on host NIC bandwidth and camera stream configurations.
"""

import os
import time
import pytest
import numpy as np
import psutil

from engines.video_engine.stream_manager import StreamManager
from engines.video_engine.rtsp_streamer import RTSPStreamWorker


class TestStreamScale64Channels:
    """Benchmark suite evaluating stream manager and worker performance up to 64 channels."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        self.mgr = StreamManager(max_channels=64)
        yield
        self.mgr.stop_all()

    @pytest.mark.parametrize("channel_count", [1, 4, 16])
    def test_multichannel_sustained_workload(self, channel_count):
        """Measures multi-channel decoding and queuing across standard multi-view layouts."""
        for i in range(1, channel_count + 1):
            ch_id = f"bench_cam_{i}"
            self.mgr.start_stream(
                channel_id=ch_id,
                rtsp_url=f"test://bench_{i}",
                channel_name=f"Bench Cam {i}",
                is_test_stream=True,
            )

        # Allow streams to run for 0.5s
        time.sleep(0.5)

        # Verify all started streams are online
        telemetry_map = self.mgr.get_all_telemetry()
        assert len(telemetry_map) == channel_count

        for ch_id, data in telemetry_map.items():
            assert data["state"] == "ONLINE"
            assert data["frames_received"] > 0

    def test_simulated_64_channel_frame_distribution_and_memory(self):
        """
        Benchmarks 64 concurrent streams under simulated surveillance workload.
        Evaluates queue stability, frame dispatch overhead, and memory consumption.
        """
        process = psutil.Process(os.getpid())
        initial_mem_mb = process.memory_info().rss / (1024 * 1024)

        start_time = time.perf_counter()

        # Start 64 simulated streams with substream bounded queue (maxlen=5)
        for i in range(1, 65):
            ch_id = f"sim_64_cam_{i}"
            self.mgr.start_stream(
                channel_id=ch_id,
                rtsp_url=f"test://sim_64_{i}",
                channel_name=f"Camera {i:02d}",
                max_buffer_size=5,
                is_test_stream=True,
            )

        startup_elapsed = time.perf_counter() - start_time
        # Starting 64 worker threads should take less than 2.0 seconds
        assert startup_elapsed < 2.0, f"Startup took {startup_elapsed:.2f}s, expected < 2.0s"

        # Run 64 streams for 0.5 second (~800 frames total across all streams)
        time.sleep(0.5)

        # Collect diagnostics
        report = self.mgr.get_diagnostics_report()
        assert report["total_channels_registered"] == 64
        assert report["active_online_streams"] == 64

        # Verify queues remain bounded and healthy
        for ch_id, ch_data in report["channels"].items():
            assert ch_data["queue_occupancy"] <= ch_data["queue_capacity"]
            assert ch_data["decoder_errors"] == 0
            assert ch_data["is_frozen"] is False

        # Memory stability check: 64 bounded queues storing numpy ndarrays should consume < 1000 MB delta
        final_mem_mb = process.memory_info().rss / (1024 * 1024)
        mem_growth_mb = final_mem_mb - initial_mem_mb
        assert mem_growth_mb < 1000.0, f"Memory growth {mem_growth_mb:.1f}MB exceeded 1000MB budget"

        # Graceful shutdown benchmark
        stop_start = time.perf_counter()
        self.mgr.stop_all()
        stop_elapsed = time.perf_counter() - stop_start
        assert stop_elapsed < 2.5, f"Stopping 64 streams took {stop_elapsed:.2f}s, expected < 2.5s"
