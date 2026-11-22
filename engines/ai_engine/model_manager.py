"""
AI Model Manager.
Handles ONNX model loading, SHA-256 validation, version management,
and model registry operations against the database.
"""

import os
import json
import hashlib
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from database.database_manager import db_manager
from database.models.ai import AIModel, AIModelVersion
from core.logging.logger import get_logger
from core.config.settings import settings

logger = get_logger("model_manager")

# Default YOLOv8n ONNX model metadata
# Source: Ultralytics YOLOv8n (Nano) exported to ONNX
# License: AGPL-3.0 (Ultralytics)
# Input: 1x3x640x640 (NCHW, float32, normalized 0-1)
# This model must be obtained and placed manually by the operator.
YOLOV8N_MODEL_INFO = {
    "name": "yolov8n",
    "task_type": "OBJECT_DETECTION",
    "framework": "ONNX",
    "description": "Ultralytics YOLOv8 Nano - General object detection (80 classes, COCO pretrained)",
    "version": "8.0",
    "input_width": 640,
    "input_height": 640,
    "source": "https://github.com/ultralytics/ultralytics",
    "license": "AGPL-3.0",
    "classes": [
        "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
        "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
        "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
        "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
        "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
        "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
        "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
        "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
        "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
        "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
        "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
        "hair drier", "toothbrush"
    ],
}

# Platform-relevant detection classes (subset of COCO for surveillance)
SURVEILLANCE_CLASSES = {"person", "bicycle", "car", "motorcycle", "bus", "truck"}
SURVEILLANCE_CLASS_INDICES = {0, 1, 2, 3, 5, 7}  # COCO indices for the above


@dataclass
class ModelSpec:
    """In-memory specification for a loaded model."""
    model_id: str
    version_id: str
    name: str
    task_type: str
    file_path: str
    input_width: int
    input_height: int
    class_labels: List[str]
    target_device: str
    sha256: Optional[str] = None


class ModelManager:
    """
    Manages AI model lifecycle: registration, validation, loading,
    and version tracking.
    """

    def __init__(self) -> None:
        self._loaded_specs: Dict[str, ModelSpec] = {}
        self._lock = threading.Lock()
        self._models_dir = Path("models")

    @property
    def models_dir(self) -> Path:
        return self._models_dir

    def set_models_dir(self, path: str) -> None:
        self._models_dir = Path(path)
        self._models_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_sha256(file_path: str) -> str:
        """Computes SHA-256 hash of a model file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        return sha256.hexdigest()

    def register_model(
        self,
        name: str,
        task_type: str,
        framework: str,
        description: str,
        version: str,
        file_path: str,
        input_width: int = 640,
        input_height: int = 640,
        class_labels: Optional[List[str]] = None,
        target_device: str = "AUTO",
        expected_sha256: Optional[str] = None,
    ) -> Optional[ModelSpec]:
        """
        Registers a model and version in the database.
        Validates file existence and optional SHA-256 checksum.
        """
        if not os.path.exists(file_path):
            logger.error("Model file does not exist: %s", file_path)
            return None

        actual_sha256 = self.compute_sha256(file_path)

        if expected_sha256 and actual_sha256 != expected_sha256:
            logger.error(
                "SHA-256 mismatch for model '%s': expected %s, got %s",
                name, expected_sha256, actual_sha256
            )
            return None

        labels = class_labels or YOLOV8N_MODEL_INFO["classes"]

        with db_manager.get_session() as session:
            # Find or create the AIModel record
            ai_model = session.query(AIModel).filter_by(name=name).first()
            if not ai_model:
                ai_model = AIModel(
                    name=name,
                    task_type=task_type,
                    framework=framework,
                    description=description,
                    is_active=True,
                )
                session.add(ai_model)
                session.flush()

            model_id = ai_model.id

            # Create version record
            existing_ver = session.query(AIModelVersion).filter_by(
                model_id=model_id, version=version
            ).first()

            if existing_ver:
                version_id = existing_ver.id
                logger.info("Model version '%s' v%s already registered.", name, version)
            else:
                model_version = AIModelVersion(
                    model_id=model_id,
                    version=version,
                    file_path=file_path,
                    weights_sha256=actual_sha256,
                    target_device=target_device,
                    input_width=input_width,
                    input_height=input_height,
                    classes_json=json.dumps(labels),
                    is_default=True,
                )
                session.add(model_version)
                session.flush()
                version_id = model_version.id
                logger.info(
                    "Registered model '%s' v%s (SHA-256: %s..., Device: %s)",
                    name, version, actual_sha256[:12], target_device
                )

        spec = ModelSpec(
            model_id=model_id,
            version_id=version_id,
            name=name,
            task_type=task_type,
            file_path=file_path,
            input_width=input_width,
            input_height=input_height,
            class_labels=labels,
            target_device=target_device,
            sha256=actual_sha256,
        )

        with self._lock:
            self._loaded_specs[name] = spec

        return spec

    def get_model_spec(self, name: str) -> Optional[ModelSpec]:
        """Returns the in-memory spec for a loaded model."""
        with self._lock:
            return self._loaded_specs.get(name)

    def list_registered_models(self) -> List[Dict[str, Any]]:
        """Returns all registered models from the database."""
        result = []
        with db_manager.get_session() as session:
            models = session.query(AIModel).filter_by(is_deleted=False).all()
            for m in models:
                for v in m.versions:
                    result.append({
                        "model_id": m.id,
                        "name": m.name,
                        "task_type": m.task_type,
                        "framework": m.framework,
                        "version": v.version,
                        "file_path": v.file_path,
                        "sha256": v.weights_sha256,
                        "device": v.target_device,
                        "input_size": f"{v.input_width}x{v.input_height}",
                        "is_active": m.is_active,
                    })
        return result

    def validate_model_file(self, file_path: str, expected_sha256: Optional[str] = None) -> Dict[str, Any]:
        """Validates a model file exists and optionally matches SHA-256."""
        result = {"valid": False, "file_exists": False, "sha256_match": None}

        if not os.path.exists(file_path):
            return result

        result["file_exists"] = True
        result["file_size_bytes"] = os.path.getsize(file_path)
        actual_sha256 = self.compute_sha256(file_path)
        result["sha256"] = actual_sha256

        if expected_sha256:
            result["sha256_match"] = actual_sha256 == expected_sha256
            result["valid"] = result["sha256_match"]
        else:
            result["valid"] = True

        return result


# Global model manager singleton
model_manager = ModelManager()
