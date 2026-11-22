"""
Unit tests for OpenVINO and ONNX AI Inference Engine,
Model Manager, Device Selection, and CPU Fallback.
"""

import os
import time
import pytest
import numpy as np

from engines.ai_engine.inference_engine import (
    OpenVINOInferenceEngine,
    ONNXInferenceEngine,
    InferenceMetrics,
    openvino_engine,
    onnx_engine,
)
from engines.ai_engine.model_manager import (
    ModelManager,
    YOLOV8N_MODEL_INFO,
    SURVEILLANCE_CLASSES,
)


@pytest.fixture(scope="module")
def onnx_model_path():
    """Path to the verified local ONNX model."""
    path = "models/yolov8n_surveillance.onnx"
    assert os.path.exists(path), f"Test ONNX model missing at {path}"
    return path


def test_inference_metrics_tracking():
    """Verifies latency and FPS computation in InferenceMetrics."""
    metrics = InferenceMetrics(device="CPU", model_name="yolov8n")
    metrics._last_fps_time = time.perf_counter()

    metrics.record(10.0)
    metrics.record(20.0)
    metrics.record(30.0)

    assert metrics.total_inferences == 3
    assert metrics.avg_latency_ms == pytest.approx(20.0)
    assert metrics.min_latency_ms == 10.0
    assert metrics.max_latency_ms == 30.0
    assert metrics.last_latency_ms == 30.0

    d = metrics.to_dict()
    assert d["total_inferences"] == 3
    assert d["avg_latency_ms"] == 20.0
    assert d["device"] == "CPU"


def test_openvino_engine_initialization():
    """Verifies OpenVINO Core initialization and device probing."""
    engine = OpenVINOInferenceEngine()
    success = engine.initialize()
    assert success is True
    assert engine.is_initialized is True
    assert "CPU" in engine.available_devices
    assert engine.active_device in ("CPU", "GPU")


def test_openvino_cpu_inference(onnx_model_path):
    """Verifies compiling model on CPU and running inference."""
    engine = OpenVINOInferenceEngine()
    engine.initialize()

    compiled = engine.compile_model(onnx_model_path, "test_cpu_model", device="CPU")
    assert compiled is True

    info = engine.get_model_info("test_cpu_model")
    assert info is not None
    assert info["device"] == "CPU"
    assert len(info["output_names"]) > 0

    dummy_input = np.zeros((1, 3, 640, 640), dtype=np.float32)
    outputs = engine.infer("test_cpu_model", dummy_input)
    assert outputs is not None
    output_key = list(outputs.keys())[0]
    assert outputs[output_key].shape == (1, 84, 8400)

    engine.release_model("test_cpu_model")
    assert engine.get_model_info("test_cpu_model") is None


def test_openvino_gpu_selection_or_fallback(onnx_model_path):
    """
    Verifies Intel UHD GPU device selection if available,
    and automatic CPU fallback when an invalid device is requested.
    """
    engine = OpenVINOInferenceEngine()
    engine.initialize()

    if "GPU" in engine.available_devices:
        compiled = engine.compile_model(onnx_model_path, "test_gpu_model", device="GPU")
        assert compiled is True
        info = engine.get_model_info("test_gpu_model")
        assert info["device"] == "GPU"
        engine.release_model("test_gpu_model")

    # Requesting an unavailable device must trigger automatic CPU fallback
    compiled_fallback = engine.compile_model(
        onnx_model_path, "test_fallback_model", device="NON_EXISTENT_DEVICE_XYZ"
    )
    assert compiled_fallback is True
    info_fb = engine.get_model_info("test_fallback_model")
    assert info_fb["device"] == "CPU"
    engine.release_model("test_fallback_model")


def test_onnx_runtime_inference(onnx_model_path):
    """Verifies fallback ONNX Runtime inference session."""
    engine = ONNXInferenceEngine()
    success = engine.initialize()
    assert success is True

    loaded = engine.load_model(onnx_model_path, "test_ort_model")
    assert loaded is True

    dummy_input = np.zeros((1, 3, 640, 640), dtype=np.float32)
    outputs = engine.infer("test_ort_model", dummy_input)
    assert outputs is not None
    output_key = list(outputs.keys())[0]
    assert outputs[output_key].shape == (1, 84, 8400)

    engine.release_all()


def test_model_manager_sha256_and_validation(onnx_model_path):
    """Verifies model file checksum calculation and validation."""
    mgr = ModelManager()
    actual_hash = mgr.compute_sha256(onnx_model_path)
    assert len(actual_hash) == 64

    # Validation with matching hash
    valid_res = mgr.validate_model_file(onnx_model_path, expected_sha256=actual_hash)
    assert valid_res["valid"] is True
    assert valid_res["file_exists"] is True
    assert valid_res["sha256_match"] is True

    # Validation with mismatched hash
    invalid_res = mgr.validate_model_file(onnx_model_path, expected_sha256="0" * 64)
    assert invalid_res["valid"] is False
    assert invalid_res["sha256_match"] is False

    # Validation of non-existent file
    missing_res = mgr.validate_model_file("models/non_existent_file.onnx")
    assert missing_res["valid"] is False
    assert missing_res["file_exists"] is False


def test_model_manager_registration(onnx_model_path, test_db_manager):
    """Verifies registering a model in the database catalog."""
    mgr = ModelManager()
    spec = mgr.register_model(
        name="yolov8n_surveillance_test",
        task_type="OBJECT_DETECTION",
        framework="ONNX",
        description="Surveillance Object Detection Model",
        version="1.0.0",
        file_path=onnx_model_path,
        target_device="CPU",
    )
    assert spec is not None
    assert spec.name == "yolov8n_surveillance_test"
    assert spec.version_id is not None
    assert spec.target_device == "CPU"
    assert "person" in spec.class_labels
    assert "car" in spec.class_labels


def test_model_loading_errors():
    """Verifies error handling on missing files or uncompiled model calls."""
    engine = OpenVINOInferenceEngine()
    engine.initialize()

    # Compiling a non-existent file returns False
    res = engine.compile_model("missing/path/model.onnx", "missing_model")
    assert res is False

    # Inferring on an uncompiled model returns None
    out = engine.infer("uncompiled_model_id", np.zeros((1, 3, 640, 640), dtype=np.float32))
    assert out is None
