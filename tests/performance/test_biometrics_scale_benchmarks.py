"""
Performance & Scale Benchmark Test Suite for Biometrics & ANPR:
Evaluates sustained throughput, per-frame latency, and memory stability across 1, 4, 9, and 16 channels.
"""

import time
import os
import psutil
import pytest
import numpy as np
import cv2

from engines.anpr_engine.ocr_recognizer import PlateOCRRecognizer
from engines.face_engine.face_embedder import FaceEmbedder
from engines.face_engine.face_detector import FaceDetector


class TestBiometricsScaleBenchmarks:
    @pytest.fixture
    def plate_sample(self):
        img = np.full((50, 200), 240, dtype=np.uint8)
        cv2.putText(img, "KA01AB1234", (10, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 10, 2)
        return img

    @pytest.fixture
    def face_sample(self):
        img = np.full((112, 112, 3), 160, dtype=np.uint8)
        cv2.circle(img, (56, 56), 40, (200, 200, 200), -1)
        cv2.rectangle(img, (28, 40), (84, 52), (60, 60, 60), -1)
        cv2.circle(img, (40, 46), 5, (20, 20, 20), -1)
        cv2.circle(img, (72, 46), 5, (20, 20, 20), -1)
        return img

    @pytest.mark.parametrize("channels", [1, 4, 9, 16])
    def test_sustained_channel_throughput(self, channels, plate_sample, face_sample):
        """
        Benchmarks multi-channel sustained throughput.
        Simulates 2 vehicle detections and 2 face evaluations per channel.
        Total operations = channels * 4.
        """
        ocr = PlateOCRRecognizer()
        embedder = FaceEmbedder()

        # Warmup
        ocr.recognize(plate_sample)
        embedder.extract_embedding(face_sample)

        start = time.perf_counter()
        for _ in range(channels):
            ocr.recognize(plate_sample)
            ocr.recognize(plate_sample)
            embedder.extract_embedding(face_sample)
            embedder.extract_embedding(face_sample)
        duration = time.perf_counter() - start

        total_ops = channels * 4
        ops_per_sec = total_ops / duration
        latency_per_channel_ms = (duration / channels) * 1000.0

        print(f"\n[BENCHMARK] {channels} Channels: Total {duration*1000:.1f}ms | Per-Channel: {latency_per_channel_ms:.2f}ms | Rate: {ops_per_sec:.1f} ops/sec")
        # Every channel must complete within real-time frame period with desktop scheduling tolerance (< 90ms)
        assert latency_per_channel_ms < 90.0

    def test_memory_stability_under_sustained_workload(self, plate_sample, face_sample):
        """
        Validates memory stability across 100 sustained iterations.
        Ensures process resident memory (RSS) does not leak (delta < 40 MB).
        """
        process = psutil.Process(os.getpid())
        ocr = PlateOCRRecognizer()
        embedder = FaceEmbedder()

        # Warmup iterations to settle model weights and buffers in RAM/VRAM
        for _ in range(10):
            ocr.recognize(plate_sample)
            embedder.extract_embedding(face_sample)

        start_mem_mb = process.memory_info().rss / (1024 * 1024)

        # Run 100 sustained operations
        for _ in range(100):
            ocr.recognize(plate_sample)
            embedder.extract_embedding(face_sample)

        end_mem_mb = process.memory_info().rss / (1024 * 1024)
        mem_delta_mb = end_mem_mb - start_mem_mb

        print(f"\n[MEMORY BENCHMARK] Start: {start_mem_mb:.1f} MB | End: {end_mem_mb:.1f} MB | Delta: {mem_delta_mb:.2f} MB")
        # Memory delta should be minimal (no memory leaks)
        assert mem_delta_mb < 40.0
