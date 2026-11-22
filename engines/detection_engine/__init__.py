"""
Object Detection Engine Package.
YOLO object detection preprocessing, inference, and postprocessing.
"""

from engines.detection_engine.yolo_detector import (
    YOLODetector,
    DetectionResult,
)

__all__ = [
    "YOLODetector",
    "DetectionResult",
]
