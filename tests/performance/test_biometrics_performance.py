"""
Performance Benchmark Test Suite for Phase 7 Biometrics & ANPR:
Measures processing throughput (FPS), per-frame latency (ms),
and hardware resource efficiency across 1, 4, 9, and 16 channels.
"""

import time
import os
import pytest
import numpy as np
import cv2

from engines.anpr_engine.plate_detector import PlateDetector
from engines.anpr_engine.ocr_recognizer import PlateOCRRecognizer
from engines.face_engine.face_detector import FaceDetector
from engines.face_engine.face_embedder import FaceEmbedder
from engines.face_engine.face_vault import FaceBiometricVault


@pytest.fixture
def benchmark_plate_image():
    """Generates standard vehicle plate crop."""
    img = np.full((60, 200, 3), 240, dtype=np.uint8)
    cv2.putText(img, "KA05MH1234", (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (10, 10, 10), 3)
    return img


@pytest.fixture
def benchmark_face_image():
    """Generates standard 112x112 face crop."""
    img = np.full((112, 112, 3), 150, dtype=np.uint8)
    cv2.circle(img, (56, 56), 40, (200, 200, 200), -1)
    cv2.circle(img, (42, 45), 6, (20, 20, 20), -1)
    cv2.circle(img, (70, 45), 6, (20, 20, 20), -1)
    cv2.ellipse(img, (56, 80), (16, 8), 0, 0, 180, (20, 20, 20), 2)
    return img


class TestBiometricsPerformance:
    def test_anpr_ocr_latency(self, benchmark_plate_image):
        ocr = PlateOCRRecognizer()

        # Warmup
        ocr.recognize(benchmark_plate_image)

        iterations = 20
        start = time.perf_counter()
        for _ in range(iterations):
            res = ocr.recognize(benchmark_plate_image)
        elapsed = time.perf_counter() - start

        avg_latency_ms = (elapsed / iterations) * 1000.0
        fps = iterations / elapsed

        print(f"\n[PERF] ANPR OCR Average Latency: {avg_latency_ms:.2f} ms ({fps:.1f} FPS)")
        # Real-time requirement: local OCR should execute in < 25 ms per plate crop
        assert avg_latency_ms < 25.0

    def test_face_quality_and_embedding_latency(self, benchmark_face_image):
        detector = FaceDetector()
        embedder = FaceEmbedder()

        # Warmup
        detector.assess_quality(benchmark_face_image)
        embedder.extract_embedding(benchmark_face_image)

        iterations = 25
        start = time.perf_counter()
        for _ in range(iterations):
            q = detector.assess_quality(benchmark_face_image)
            emb = embedder.extract_embedding(benchmark_face_image)
        elapsed = time.perf_counter() - start

        avg_latency_ms = (elapsed / iterations) * 1000.0
        fps = iterations / elapsed

        print(f"\n[PERF] Face Quality & Embedding Average Latency: {avg_latency_ms:.2f} ms ({fps:.1f} FPS)")
        # Real-time requirement: face quality + 512-d embedding extraction < 20 ms
        assert avg_latency_ms < 20.0

    @pytest.mark.parametrize("channel_count", [1, 4, 9, 16])
    def test_multichannel_simulated_workload(self, channel_count, benchmark_plate_image, benchmark_face_image):
        """
        Simulates multi-camera workload:
        Each camera channel processes 2 vehicle crops and 2 face crops per second.
        Validates pipeline scale up to 16 channels.
        """
        ocr = PlateOCRRecognizer()
        embedder = FaceEmbedder()

        total_operations = channel_count * 4  # 2 ANPR + 2 Face per channel
        start = time.perf_counter()

        for _ in range(channel_count):
            # ANPR operations
            ocr.recognize(benchmark_plate_image)
            ocr.recognize(benchmark_plate_image)
            # Face operations
            embedder.extract_embedding(benchmark_face_image)
            embedder.extract_embedding(benchmark_face_image)

        elapsed = time.perf_counter() - start
        avg_channel_latency_ms = (elapsed / channel_count) * 1000.0

        print(f"\n[PERF] Multi-Channel Benchmark: {channel_count} channels | Total Time: {elapsed*1000:.1f} ms | Per-Channel: {avg_channel_latency_ms:.2f} ms")
        # Ensure multi-channel simulated burst completes within 500ms budget (well below 1000ms real-time second)
        assert elapsed < 0.500
