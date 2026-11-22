"""
YOLO Object Detection Engine.
Handles preprocessing (letterbox, normalize), inference dispatch,
and postprocessing (NMS, bounding box decode, class filtering).

Supported model: YOLOv8n ONNX (Ultralytics, COCO pretrained)
Source: https://github.com/ultralytics/ultralytics
License: AGPL-3.0
Input format: 1x3x640x640 (NCHW, float32, normalized 0-1)
"""

import time
from typing import List, Optional, Dict, Any, Set, Tuple
from dataclasses import dataclass, field

import numpy as np
import cv2

from core.logging.logger import get_logger

logger = get_logger("yolo_detector")


@dataclass
class DetectionResult:
    """Single object detection result."""
    class_id: int
    class_name: str
    confidence: float
    bbox_x: float  # Normalized 0-1
    bbox_y: float
    bbox_w: float
    bbox_h: float
    # Pixel coordinates (original image space)
    pixel_x: int = 0
    pixel_y: int = 0
    pixel_w: int = 0
    pixel_h: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 4),
            "bbox": [self.bbox_x, self.bbox_y, self.bbox_w, self.bbox_h],
            "pixel_bbox": [self.pixel_x, self.pixel_y, self.pixel_w, self.pixel_h],
        }


class YOLODetector:
    """
    YOLO object detection preprocessor and postprocessor.
    Uses either OpenVINO or ONNX Runtime as backend.
    """

    # COCO class names
    COCO_CLASSES = [
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
    ]

    # Surveillance-relevant classes (Phase 5 requirement)
    SURVEILLANCE_CLASS_IDS = {0, 1, 2, 3, 5, 7}  # person, bicycle, car, motorcycle, bus, truck

    def __init__(
        self,
        inference_fn=None,
        model_name: str = "yolov8n",
        input_width: int = 640,
        input_height: int = 640,
        confidence_threshold: float = 0.50,
        iou_threshold: float = 0.45,
        class_filter: Optional[Set[int]] = None,
        class_names: Optional[List[str]] = None,
    ) -> None:
        self.inference_fn = inference_fn
        self.model_name = model_name
        self.input_width = input_width
        self.input_height = input_height
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.class_filter = class_filter if class_filter is not None else self.SURVEILLANCE_CLASS_IDS
        self.class_names = class_names or self.COCO_CLASSES
        self.execution_device = "CPU"

        # Letterbox scaling factors (set during preprocessing)
        self._scale_x = 1.0
        self._scale_y = 1.0
        self._pad_x = 0
        self._pad_y = 0
        self._orig_h = 0
        self._orig_w = 0

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """
        Letterbox resize, normalize, and format for YOLO NCHW input.
        Input: BGR numpy array (HxWxC)
        Output: Float32 array (1x3xHxW)
        """
        self._orig_h, self._orig_w = image.shape[:2]

        # Calculate letterbox scaling
        scale = min(self.input_width / self._orig_w, self.input_height / self._orig_h)
        new_w = int(self._orig_w * scale)
        new_h = int(self._orig_h * scale)

        self._scale_x = scale
        self._scale_y = scale
        self._pad_x = (self.input_width - new_w) // 2
        self._pad_y = (self.input_height - new_h) // 2

        # Resize and pad
        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        # Create padded image with gray fill
        padded = np.full((self.input_height, self.input_width, 3), 114, dtype=np.uint8)
        padded[self._pad_y:self._pad_y + new_h, self._pad_x:self._pad_x + new_w] = resized

        # BGR -> RGB, normalize to [0,1], transpose to NCHW
        blob = padded[:, :, ::-1].astype(np.float32) / 255.0
        blob = blob.transpose(2, 0, 1)
        blob = np.expand_dims(blob, axis=0)

        return blob

    def postprocess(self, outputs: Dict[str, np.ndarray], image_shape: Tuple[int, int]) -> List[DetectionResult]:
        """
        Decodes YOLO output tensor into DetectionResult objects.
        Applies confidence thresholding, class filtering, and NMS.

        YOLOv8 output format: (1, 84, 8400) = (batch, 4+80classes, predictions)
        """
        orig_h, orig_w = image_shape

        # Get the first (and usually only) output
        output_key = list(outputs.keys())[0]
        raw_output = outputs[output_key]

        # YOLOv8 output: (1, 84, N) -> transpose to (N, 84)
        if raw_output.ndim == 3:
            predictions = raw_output[0].T  # (N, 84)
        elif raw_output.ndim == 2:
            predictions = raw_output
        else:
            return []

        num_predictions = predictions.shape[0]
        num_classes = predictions.shape[1] - 4

        if num_classes <= 0:
            return []

        # Extract boxes (cx, cy, w, h) and class scores
        boxes_cxcywh = predictions[:, :4]
        class_scores = predictions[:, 4:]

        # Get max class and confidence per prediction
        class_ids = np.argmax(class_scores, axis=1)
        confidences = np.max(class_scores, axis=1)

        # Filter by confidence threshold
        mask = confidences >= self.confidence_threshold
        # Apply class filter
        if self.class_filter:
            class_mask = np.isin(class_ids, list(self.class_filter))
            mask = mask & class_mask

        filtered_boxes = boxes_cxcywh[mask]
        filtered_confs = confidences[mask]
        filtered_class_ids = class_ids[mask]

        if len(filtered_boxes) == 0:
            return []

        # Convert cx,cy,w,h to x1,y1,x2,y2 for NMS
        x1 = filtered_boxes[:, 0] - filtered_boxes[:, 2] / 2
        y1 = filtered_boxes[:, 1] - filtered_boxes[:, 3] / 2
        x2 = filtered_boxes[:, 0] + filtered_boxes[:, 2] / 2
        y2 = filtered_boxes[:, 1] + filtered_boxes[:, 3] / 2

        boxes_xyxy = np.stack([x1, y1, x2, y2], axis=1)

        # Apply NMS using OpenCV
        boxes_for_nms = [[float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1])]
                         for b in boxes_xyxy]
        confs_list = filtered_confs.tolist()

        indices = cv2.dnn.NMSBoxes(boxes_for_nms, confs_list, self.confidence_threshold, self.iou_threshold)

        results: List[DetectionResult] = []
        if len(indices) > 0:
            # OpenCV NMS returns flat array or nested depending on version
            if isinstance(indices, np.ndarray):
                indices = indices.flatten()

            for idx in indices:
                cx = filtered_boxes[idx, 0]
                cy = filtered_boxes[idx, 1]
                w = filtered_boxes[idx, 2]
                h = filtered_boxes[idx, 3]

                # Remove letterbox padding and scale to original coordinates
                real_cx = (cx - self._pad_x) / self._scale_x
                real_cy = (cy - self._pad_y) / self._scale_y
                real_w = w / self._scale_x
                real_h = h / self._scale_y

                # Clamp to image bounds
                real_x = max(0, real_cx - real_w / 2)
                real_y = max(0, real_cy - real_h / 2)
                real_w = min(real_w, orig_w - real_x)
                real_h = min(real_h, orig_h - real_y)

                class_id = int(filtered_class_ids[idx])
                class_name = self.class_names[class_id] if class_id < len(self.class_names) else f"class_{class_id}"

                result = DetectionResult(
                    class_id=class_id,
                    class_name=class_name,
                    confidence=float(filtered_confs[idx]),
                    bbox_x=round(real_x / orig_w, 6),
                    bbox_y=round(real_y / orig_h, 6),
                    bbox_w=round(real_w / orig_w, 6),
                    bbox_h=round(real_h / orig_h, 6),
                    pixel_x=int(real_x),
                    pixel_y=int(real_y),
                    pixel_w=int(real_w),
                    pixel_h=int(real_h),
                )
                results.append(result)

        return results

    def detect(self, image: np.ndarray) -> List[DetectionResult]:
        """
        End-to-end detection: preprocess -> infer -> postprocess.
        """
        if self.inference_fn is None:
            logger.error("No inference function set for detector '%s'.", self.model_name)
            return []

        orig_shape = image.shape[:2]  # (H, W)
        blob = self.preprocess(image)

        outputs = self.inference_fn(blob)
        if outputs is None:
            return []

        return self.postprocess(outputs, orig_shape)
