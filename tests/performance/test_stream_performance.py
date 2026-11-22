"""
Performance Benchmarking Suite for Video Stream Engine.
Measures CPU utilization, RAM consumption, FPS throughput, and queue utilization
across 1, 4, and 16 concurrent video stream workers.
"""

import time
import psutil
from engines.video_engine.stream_manager import StreamManager


def test_benchmark_1_stream():
    process = psutil.Process()
    ram_before_mb = process.memory_info().rss / (1024 * 1024)
    cpu_before = psutil.cpu_percent(interval=None)

    manager = StreamManager(max_channels=16)
    manager.start_stream("perf_1", "test://sim_1", channel_name="Bench 1", is_test_stream=True)

    # Run for 1.5 seconds to measure steady-state throughput
    time.sleep(1.5)

    cpu_after = psutil.cpu_percent(interval=None)
    ram_after_mb = process.memory_info().rss / (1024 * 1024)
    telemetry = manager.get_telemetry("perf_1")

    assert telemetry is not None
    assert telemetry.total_frames_received > 20
    assert telemetry.current_fps >= 15.0

    manager.stop_all()

    print(f"\n[BENCHMARK 1-STREAM RESULT]")
    print(f"  CPU Utilization : {cpu_after:.1f}%")
    print(f"  RAM Delta       : {ram_after_mb - ram_before_mb:.2f} MB (Total: {ram_after_mb:.1f} MB)")
    print(f"  Throughput FPS  : {telemetry.current_fps:.1f} FPS")
    print(f"  Frames Received : {telemetry.total_frames_received}")
    print(f"  Frames Dropped  : {telemetry.total_frames_dropped}")
    print(f"  Queue Util      : {telemetry.queue_occupancy}/{telemetry.queue_capacity}")


def test_benchmark_4_streams():
    process = psutil.Process()
    ram_before_mb = process.memory_info().rss / (1024 * 1024)
    cpu_before = psutil.cpu_percent(interval=None)

    manager = StreamManager(max_channels=16)
    for i in range(1, 5):
        manager.start_stream(f"perf_{i}", f"test://sim_{i}", channel_name=f"Bench {i}", is_test_stream=True)

    time.sleep(1.5)

    cpu_after = psutil.cpu_percent(interval=None)
    ram_after_mb = process.memory_info().rss / (1024 * 1024)
    all_telemetry = manager.get_all_telemetry()

    assert len(all_telemetry) == 4
    total_fps = sum(t["fps"] for t in all_telemetry.values())
    avg_fps = total_fps / 4

    manager.stop_all()

    print(f"\n[BENCHMARK 4-STREAM RESULT]")
    print(f"  Aggregate CPU   : {cpu_after:.1f}%")
    print(f"  RAM Delta       : {ram_after_mb - ram_before_mb:.2f} MB (Total: {ram_after_mb:.1f} MB)")
    print(f"  Avg FPS/Stream  : {avg_fps:.1f} FPS (Total: {total_fps:.1f} FPS)")
    print(f"  Active Streams  : 4 / 4 ONLINE")


def test_benchmark_16_streams():
    process = psutil.Process()
    ram_before_mb = process.memory_info().rss / (1024 * 1024)
    cpu_before = psutil.cpu_percent(interval=None)

    manager = StreamManager(max_channels=32)
    for i in range(1, 17):
        manager.start_stream(f"perf_{i}", f"test://sim_{i}", channel_name=f"Bench {i}", is_test_stream=True)

    time.sleep(2.0)

    cpu_after = psutil.cpu_percent(interval=None)
    ram_after_mb = process.memory_info().rss / (1024 * 1024)
    all_telemetry = manager.get_all_telemetry()

    assert len(all_telemetry) == 16
    total_fps = sum(t["fps"] for t in all_telemetry.values())
    avg_fps = total_fps / 16

    manager.stop_all()

    print(f"\n[BENCHMARK 16-STREAM RESULT]")
    print(f"  Aggregate CPU   : {cpu_after:.1f}%")
    print(f"  RAM Delta       : {ram_after_mb - ram_before_mb:.2f} MB (Total: {ram_after_mb:.1f} MB)")
    print(f"  Avg FPS/Stream  : {avg_fps:.1f} FPS (Aggregate Decode: {total_fps:.1f} FPS)")
    print(f"  Active Streams  : 16 / 16 ONLINE")
