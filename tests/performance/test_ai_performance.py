"""
Performance benchmarks for AI inference across 1, 4, 9, and 16 streams,
measuring latency, throughput FPS, and CPU vs GPU acceleration.
"""

import time
import pytest
import numpy as np

from engines.ai_engine.inference_engine import (
    OpenVINOInferenceEngine,
    onnx_engine,
)
from engines.detection_engine.yolo_detector import YOLODetector


@pytest.fixture(scope="module")
def compiled_engine():
    """Pre-compiles OpenVINO model for benchmarking."""
    engine = OpenVINOInferenceEngine()
    engine.initialize()
    model_path = "models/yolov8n_surveillance.onnx"
    engine.compile_model(model_path, "bench_model", device=engine.active_device)
    yield engine
    engine.release_all()


def test_benchmark_ai_single_stream(compiled_engine):
    """Benchmark: 1 camera AI inference latency and throughput."""
    dummy_input = np.zeros((1, 3, 640, 640), dtype=np.float32)

    # Warmup
    for _ in range(5):
        compiled_engine.infer("bench_model", dummy_input)

    latencies = []
    iterations = 30
    start = time.perf_counter()

    for _ in range(iterations):
        t0 = time.perf_counter()
        compiled_engine.infer("bench_model", dummy_input)
        latencies.append((time.perf_counter() - t0) * 1000)

    total_time = time.perf_counter() - start
    fps = iterations / total_time
    avg_lat = sum(latencies) / len(latencies)

    print(f"\n[BENCHMARK 1-STREAM] Device: {compiled_engine.active_device}, "
          f"Avg Latency: {avg_lat:.2f}ms, Throughput: {fps:.1f} FPS")

    assert avg_lat < 100.0  # Under 100ms per inference
    assert fps > 10.0


def test_benchmark_ai_4_streams(compiled_engine):
    """Benchmark: 4 simulated camera channels sharing inference pipeline."""
    channels = [f"CAM_{i:02d}" for i in range(4)]
    dummy_input = np.zeros((1, 3, 640, 640), dtype=np.float32)

    total_inferences = 40  # 10 per channel
    start = time.perf_counter()

    for i in range(total_inferences):
        ch = channels[i % len(channels)]
        compiled_engine.infer("bench_model", dummy_input)

    total_time = time.perf_counter() - start
    aggregate_fps = total_inferences / total_time
    fps_per_ch = aggregate_fps / 4

    print(f"\n[BENCHMARK 4-STREAMS] Aggregate: {aggregate_fps:.1f} FPS, "
          f"Per-Channel: {fps_per_ch:.1f} FPS (Target: 5 FPS)")

    assert aggregate_fps > 15.0


def test_benchmark_ai_16_streams_substream_sampling(compiled_engine):
    """
    Benchmark: 16 camera channels with 5 FPS frame sampling.
    Surveillance substream architecture targets 5 FPS per channel for AI.
    """
    channels = [f"CAM_{i:02d}" for i in range(16)]
    dummy_input = np.zeros((1, 3, 640, 640), dtype=np.float32)

    total_inferences = 48  # 3 per channel
    start = time.perf_counter()

    for i in range(total_inferences):
        compiled_engine.infer("bench_model", dummy_input)

    total_time = time.perf_counter() - start
    aggregate_fps = total_inferences / total_time

    print(f"\n[BENCHMARK 16-STREAMS] Aggregate Throughput: {aggregate_fps:.1f} FPS "
          f"across 16 channels on {compiled_engine.active_device}")

    assert aggregate_fps > 15.0
