"""
OpenVINO AI Inference Engine.
Provides GPU-accelerated (Intel UHD 730) and CPU fallback inference
with model compilation, async request handling, and device management.
"""

import time
import threading
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np

from core.logging.logger import get_logger
from core.config.settings import settings

logger = get_logger("inference_engine")


@dataclass
class InferenceMetrics:
    """Real-time performance metrics for an inference session."""
    total_inferences: int = 0
    total_latency_ms: float = 0.0
    last_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    min_latency_ms: float = float("inf")
    max_latency_ms: float = 0.0
    fps: float = 0.0
    device: str = "UNKNOWN"
    model_name: str = ""
    started_at: Optional[datetime] = None
    _last_fps_time: float = 0.0
    _fps_frame_count: int = 0

    def record(self, latency_ms: float) -> None:
        self.total_inferences += 1
        self.total_latency_ms += latency_ms
        self.last_latency_ms = latency_ms
        self.avg_latency_ms = self.total_latency_ms / self.total_inferences
        self.min_latency_ms = min(self.min_latency_ms, latency_ms)
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)

        # FPS calculation over 1-second windows
        now = time.perf_counter()
        self._fps_frame_count += 1
        elapsed = now - self._last_fps_time
        if elapsed >= 1.0:
            self.fps = self._fps_frame_count / elapsed
            self._fps_frame_count = 0
            self._last_fps_time = now

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_inferences": self.total_inferences,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "last_latency_ms": round(self.last_latency_ms, 2),
            "min_latency_ms": round(self.min_latency_ms, 2) if self.min_latency_ms != float("inf") else 0.0,
            "max_latency_ms": round(self.max_latency_ms, 2),
            "fps": round(self.fps, 1),
            "device": self.device,
            "model_name": self.model_name,
        }


class OpenVINOInferenceEngine:
    """
    Core inference engine wrapping OpenVINO Core for model compilation
    and synchronous/asynchronous inference with GPU/CPU device selection.
    """

    def __init__(self) -> None:
        self._core = None
        self._compiled_models: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._available_devices: List[str] = []
        self._is_initialized = False
        self._active_device = "CPU"

    def initialize(self) -> bool:
        """Initialize OpenVINO Core and detect available devices."""
        try:
            from openvino import Core
            self._core = Core()
            self._available_devices = list(self._core.available_devices)
            self._is_initialized = True

            # Select best device
            preferred = settings.ai.preferred_device
            if preferred == "AUTO":
                if "GPU" in self._available_devices:
                    self._active_device = "GPU"
                else:
                    self._active_device = "CPU"
            elif preferred in self._available_devices:
                self._active_device = preferred
            else:
                self._active_device = "CPU"

            logger.info(
                "OpenVINO Core initialized. Available devices: %s, Active device: %s",
                self._available_devices, self._active_device
            )
            return True
        except ImportError:
            logger.warning("OpenVINO is not installed. Falling back to ONNX Runtime CPU inference.")
            self._is_initialized = False
            return False
        except Exception as e:
            logger.error("Failed to initialize OpenVINO Core: %s", e)
            self._is_initialized = False
            return False

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    @property
    def active_device(self) -> str:
        return self._active_device

    @property
    def available_devices(self) -> List[str]:
        return list(self._available_devices)

    def compile_model(
        self,
        model_path: str,
        model_id: str,
        device: Optional[str] = None,
        config: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Compiles an ONNX or OpenVINO IR model for the target device.
        Returns True on success.
        """
        target_device = device or self._active_device

        if not self._is_initialized or self._core is None:
            logger.error("Cannot compile model: OpenVINO Core not initialized.")
            return False

        model_file = Path(model_path)
        if not model_file.exists():
            logger.error("Model file not found: %s", model_path)
            return False

        try:
            with self._lock:
                ov_model = self._core.read_model(str(model_file))
                compile_config = config or {}

                # Try GPU first, fallback to CPU if GPU compilation fails
                try:
                    compiled = self._core.compile_model(ov_model, target_device, compile_config)
                    actual_device = target_device
                except Exception as gpu_err:
                    if target_device != "CPU":
                        logger.warning(
                            "Failed to compile model on %s: %s. Falling back to CPU.",
                            target_device, gpu_err
                        )
                        compiled = self._core.compile_model(ov_model, "CPU", compile_config)
                        actual_device = "CPU"
                    else:
                        raise

                self._compiled_models[model_id] = {
                    "compiled_model": compiled,
                    "device": actual_device,
                    "input_names": [inp.get_any_name() for inp in compiled.inputs],
                    "output_names": [out.get_any_name() for out in compiled.outputs],
                }

                logger.info(
                    "Model '%s' compiled on %s (inputs: %s, outputs: %s)",
                    model_id, actual_device,
                    self._compiled_models[model_id]["input_names"],
                    self._compiled_models[model_id]["output_names"],
                )
                return True

        except Exception as e:
            logger.error("Failed to compile model '%s': %s", model_id, e)
            return False

    def infer(self, model_id: str, input_data: np.ndarray) -> Optional[Dict[str, np.ndarray]]:
        """
        Runs synchronous inference on a compiled model.
        Returns dict of output name -> numpy array, or None on failure.
        """
        model_info = self._compiled_models.get(model_id)
        if model_info is None:
            logger.error("Model '%s' is not compiled.", model_id)
            return None

        try:
            compiled = model_info["compiled_model"]
            input_name = model_info["input_names"][0]
            result = compiled({input_name: input_data})

            outputs = {}
            for out_name in model_info["output_names"]:
                outputs[out_name] = result[out_name]

            return outputs

        except Exception as e:
            logger.error("Inference failed for model '%s': %s", model_id, e)
            return None

    def get_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Returns metadata about a compiled model."""
        info = self._compiled_models.get(model_id)
        if info is None:
            return None
        return {
            "device": info["device"],
            "input_names": info["input_names"],
            "output_names": info["output_names"],
        }

    def release_model(self, model_id: str) -> None:
        """Releases a compiled model from memory."""
        with self._lock:
            if model_id in self._compiled_models:
                del self._compiled_models[model_id]
                logger.info("Released compiled model '%s'.", model_id)

    def release_all(self) -> None:
        """Releases all compiled models."""
        with self._lock:
            self._compiled_models.clear()
            logger.info("All compiled models released.")


class ONNXInferenceEngine:
    """
    Fallback inference engine using ONNX Runtime.
    Used when OpenVINO is unavailable.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._is_initialized = False

    def initialize(self) -> bool:
        try:
            import onnxruntime
            self._is_initialized = True
            providers = onnxruntime.get_available_providers()
            logger.info("ONNX Runtime initialized. Providers: %s", providers)
            return True
        except ImportError:
            logger.error("ONNX Runtime is not installed.")
            return False

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    def load_model(self, model_path: str, model_id: str) -> bool:
        """Loads an ONNX model into an inference session."""
        if not Path(model_path).exists():
            logger.error("ONNX model file not found: %s", model_path)
            return False

        try:
            import onnxruntime as ort
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.intra_op_num_threads = 4

            providers = ["CPUExecutionProvider"]
            # Try DML on Windows for Intel GPU
            available = ort.get_available_providers()
            if "DmlExecutionProvider" in available:
                providers.insert(0, "DmlExecutionProvider")
            if "OpenVINOExecutionProvider" in available:
                providers.insert(0, "OpenVINOExecutionProvider")

            session = ort.InferenceSession(model_path, sess_options, providers=providers)

            with self._lock:
                self._sessions[model_id] = {
                    "session": session,
                    "input_names": [inp.name for inp in session.get_inputs()],
                    "output_names": [out.name for out in session.get_outputs()],
                }

            logger.info("ONNX model '%s' loaded (providers: %s)", model_id, providers)
            return True

        except Exception as e:
            logger.error("Failed to load ONNX model '%s': %s", model_id, e)
            return False

    def infer(self, model_id: str, input_data: np.ndarray) -> Optional[Dict[str, np.ndarray]]:
        """Runs inference with ONNX Runtime."""
        sess_info = self._sessions.get(model_id)
        if sess_info is None:
            return None

        try:
            session = sess_info["session"]
            input_name = sess_info["input_names"][0]
            results = session.run(None, {input_name: input_data})

            outputs = {}
            for i, name in enumerate(sess_info["output_names"]):
                outputs[name] = results[i]
            return outputs

        except Exception as e:
            logger.error("ONNX inference failed for '%s': %s", model_id, e)
            return None

    def release_all(self) -> None:
        with self._lock:
            self._sessions.clear()


# Global inference engine singletons
openvino_engine = OpenVINOInferenceEngine()
onnx_engine = ONNXInferenceEngine()
