"""
Performance and Scalability Benchmarks for Behaviour Analytics (Phase 8).
Measures evaluation latency, throughput scaling across 1, 4, 9, 16, and 64 simulated channels,
and memory stability under continuous workload.
"""

from dataclasses import dataclass
from typing import Tuple, List
import time
import pytest
import psutil

from engines.analytics_engine.behaviour_detectors import BehaviourAnalyticsManager
from engines.analytics_engine.rule_evaluator import ZoneConfig


@dataclass
class MockTrack:
    track_id: int
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]


def _generate_scene_tracks(num_tracks: int = 10) -> List[MockTrack]:
    tracks = []
    classes = ["person", "car", "backpack", "suitcase", "bicycle"]
    for i in range(num_tracks):
        c = classes[i % len(classes)]
        x = 0.10 + (i * 0.05) % 0.80
        y = 0.20 + (i * 0.04) % 0.60
        w = 0.08 if c != "person" else 0.10
        h = 0.08 if c != "person" else 0.30
        tracks.append(MockTrack(track_id=i + 1, class_name=c, confidence=0.88, bbox=(x, y, w, h)))
    return tracks


@pytest.mark.parametrize("channel_count", [1, 4, 9, 16])
def test_behaviour_multi_channel_throughput(channel_count: int):
    managers = [BehaviourAnalyticsManager(f"CAM-{i:02d}") for i in range(channel_count)]
    zone = ZoneConfig("Z1", "Monitored Area", "CROWD", [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
    setattr(zone, "surface_area_m2", 25.0)

    tracks = _generate_scene_tracks(12)
    t_now = time.time()

    # Warmup
    for mgr in managers:
        mgr.evaluate_frame([zone], tracks, t_now)

    # Benchmark 20 iterations across all channels
    start_time = time.perf_counter()
    iterations = 20
    for iter_idx in range(iterations):
        ts = t_now + (iter_idx * 0.1)
        for mgr in managers:
            mgr.evaluate_frame([zone], tracks, ts)
    elapsed = time.perf_counter() - start_time

    total_evals = channel_count * iterations
    avg_latency_ms = (elapsed / total_evals) * 1000.0

    print(f"\n[{channel_count} Channels] Total time: {elapsed:.4f}s | Avg latency: {avg_latency_ms:.3f} ms/eval")
    # Average latency must be < 2.0 ms per channel
    assert avg_latency_ms < 2.0, f"Average latency {avg_latency_ms:.3f} ms exceeded 2.0 ms budget"


def test_behaviour_64_channel_burst_benchmark():
    managers = [BehaviourAnalyticsManager(f"CAM-{i:02d}") for i in range(64)]
    zone = ZoneConfig("Z_GLOBAL", "Global Zone", "CROWD", [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
    setattr(zone, "surface_area_m2", 50.0)

    tracks = _generate_scene_tracks(8)
    t_now = time.time()

    # Measure single burst evaluation time across all 64 channels simultaneously
    start_time = time.perf_counter()
    for mgr in managers:
        mgr.evaluate_frame([zone], tracks, t_now)
    burst_elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    print(f"\n[64 Channels Simultaneous Burst] Elapsed: {burst_elapsed_ms:.2f} ms")
    # All 64 channels must evaluate in under 100 ms total
    assert burst_elapsed_ms < 100.0, f"64-channel burst {burst_elapsed_ms:.2f} ms exceeded 100 ms ceiling"


def test_behaviour_memory_stability():
    mgr = BehaviourAnalyticsManager("CAM-MEM")
    zone = ZoneConfig("Z_MEM", "Memory Zone", "CROWD", [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
    setattr(zone, "surface_area_m2", 20.0)

    tracks = _generate_scene_tracks(15)
    t_base = time.time()

    proc = psutil.Process()
    # Baseline
    for i in range(10):
        mgr.evaluate_frame([zone], tracks, t_base + i * 0.1)
    rss_start = proc.memory_info().rss / (1024 * 1024)

    # 100 continuous iterations
    for i in range(100):
        mgr.evaluate_frame([zone], tracks, t_base + (i + 10) * 0.1)
    rss_end = proc.memory_info().rss / (1024 * 1024)

    mem_growth_mb = rss_end - rss_start
    print(f"\n[Memory Stability] Start: {rss_start:.2f} MB | End: {rss_end:.2f} MB | Growth: {mem_growth_mb:.2f} MB")
    # Memory growth over 100 iterations must be bounded < 25 MB
    assert mem_growth_mb < 25.0
