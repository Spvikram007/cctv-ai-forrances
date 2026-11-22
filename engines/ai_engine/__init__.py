"""
AI Inference Engine Package.
OpenVINO and ONNX Runtime hardware acceleration, model management,
and multi-channel inference workers.
"""

from engines.ai_engine.inference_engine import (
    OpenVINOInferenceEngine,
    ONNXInferenceEngine,
    InferenceMetrics,
    openvino_engine,
    onnx_engine,
)
from engines.ai_engine.model_manager import (
    ModelManager,
    ModelSpec,
    model_manager,
    YOLOV8N_MODEL_INFO,
    SURVEILLANCE_CLASSES,
)
from engines.ai_engine.inference_worker import (
    AIInferenceWorker,
    InferenceWorkerManager,
    InferenceResult,
    FramePacket,
    inference_worker_manager,
)

__all__ = [
    "OpenVINOInferenceEngine",
    "ONNXInferenceEngine",
    "InferenceMetrics",
    "openvino_engine",
    "onnx_engine",
    "ModelManager",
    "ModelSpec",
    "model_manager",
    "YOLOV8N_MODEL_INFO",
    "SURVEILLANCE_CLASSES",
    "AIInferenceWorker",
    "InferenceWorkerManager",
    "InferenceResult",
    "FramePacket",
    "inference_worker_manager",
]
