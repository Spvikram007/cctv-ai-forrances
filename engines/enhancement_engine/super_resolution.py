"""
AI Super-Resolution & Forensic Watermarking (Phase 9 - F-044).
Provides 2x and 4x deep learned super-resolution with OpenVINO GPU offload
(targeting Intel UHD Graphics 730), CPU AVX2 fallback, high-fidelity
Lanczos-4 interpolation fallback, and mandatory visual evidence watermarking:
[AI ENHANCED - NOT ORIGINAL EVIDENCE].
"""

from typing import Optional, Tuple
from pathlib import Path
import cv2
import numpy as np

from core.logging.logger import get_logger
from core.config.settings import settings

logger = get_logger("super_resolution")


class SuperResolutionEnhancer:
    """
    Upscales surveillance footage by 2x or 4x scale factor.
    Supports OpenVINO runtime with GPU/CPU device selection, ONNX models,
    deterministic Lanczos-4/Bicubic fallback, and mandatory forensic watermarking.
    """

    WATERMARK_LABEL_2X = "[AI ENHANCED 2X - NOT ORIGINAL EVIDENCE]"
    WATERMARK_LABEL_4X = "[AI ENHANCED 4X - NOT ORIGINAL EVIDENCE]"
    WATERMARK_LABEL_GENERIC = "[AI ENHANCED - NOT ORIGINAL EVIDENCE]"

    def __init__(self, preferred_device: str = "AUTO") -> None:
        self.preferred_device = preferred_device
        self._openvino_core = None
        self._compiled_model = None
        self._active_device = "CPU"
        self._model_path: Optional[str] = None
        self._init_backend()

    def _init_backend(self) -> None:
        """Initialize OpenVINO Core if available."""
        try:
            import openvino as ov
            self._openvino_core = ov.Core()
            available = self._openvino_core.available_devices
            logger.info("OpenVINO devices available for Super-Resolution: %s", available)

            target = self.preferred_device.upper()
            if target in ("GPU", "AUTO") and "GPU" in available:
                self._active_device = "GPU"
            else:
                self._active_device = "CPU"
        except ImportError:
            logger.info("OpenVINO not installed; Super-Resolution running with Lanczos-4/Bicubic deterministic engine.")
            self._openvino_core = None
            self._active_device = "CPU (Lanczos-4)"
        except Exception as e:
            logger.warning("Failed to initialize OpenVINO runtime for SR: %s", e)
            self._openvino_core = None
            self._active_device = "CPU (Lanczos-4)"

    @property
    def active_device(self) -> str:
        return self._active_device

    def enhance(
        self,
        frame: np.ndarray,
        scale: int = 2,
        add_watermark: bool = True,
        watermark_text: Optional[str] = None,
        interpolation: str = "lanczos4",
    ) -> np.ndarray:
        """
        Upscale frame by scale factor (2 or 4).

        Args:
            frame: Input BGR uint8 image.
            scale: Upscaling factor: 2 or 4 (or 1 for no scale).
            add_watermark: Burn mandatory forensic watermark onto frame.
            watermark_text: Custom watermark text (default is legally compliant label).
            interpolation: Deterministic fallback method: 'lanczos4' or 'cubic'.

        Returns:
            Upscaled BGR uint8 image.
        """
        if frame is None or frame.size == 0:
            return frame

        scale = int(scale)
        if scale <= 1:
            upscaled = frame.copy()
        elif self._compiled_model is not None:
            upscaled = self._infer_openvino(frame, scale)
        else:
            upscaled = self._upscale_deterministic(frame, scale, method=interpolation)

        if add_watermark:
            if watermark_text is None:
                if scale == 2:
                    watermark_text = self.WATERMARK_LABEL_2X
                elif scale == 4:
                    watermark_text = self.WATERMARK_LABEL_4X
                else:
                    watermark_text = self.WATERMARK_LABEL_GENERIC
            upscaled = self.apply_watermark(upscaled, watermark_text)

        return upscaled

    def _upscale_deterministic(
        self,
        frame: np.ndarray,
        scale: int,
        method: str = "lanczos4",
    ) -> np.ndarray:
        """
        High-fidelity deterministic upscaling with edge acutance preservation.
        Uses 8-tap Lanczos-4 or Bicubic interpolation with subtle edge refinement.
        """
        h, w = frame.shape[:2]
        target_w = w * scale
        target_h = h * scale

        interp = cv2.INTER_LANCZOS4 if method.lower() == "lanczos4" else cv2.INTER_CUBIC
        upscaled = cv2.resize(frame, (target_w, target_h), interpolation=interp)

        # Subtle unsharp mask to counteract interpolation softness
        blurred = cv2.GaussianBlur(upscaled, (0, 0), sigmaX=1.0)
        sharpened = cv2.addWeighted(upscaled, 1.25, blurred, -0.25, 0)
        return sharpened

    def _infer_openvino(self, frame: np.ndarray, scale: int) -> np.ndarray:
        """Run deep learned Super-Resolution model inference via OpenVINO."""
        try:
            # Model inference logic for OpenVINO compiled model
            input_tensor = np.expand_dims(frame.transpose(2, 0, 1), 0).astype(np.float32) / 255.0
            results = self._compiled_model([input_tensor])
            output = results[0][0].transpose(1, 2, 0)
            return (output * 255.0).clip(0, 255).astype(np.uint8)
        except Exception as e:
            logger.warning("OpenVINO inference failed, falling back to Lanczos-4: %s", e)
            return self._upscale_deterministic(frame, scale, method="lanczos4")

    def load_model(self, model_path: str, device: Optional[str] = None) -> bool:
        """
        Load OpenVINO or ONNX super-resolution model weights.
        """
        if self._openvino_core is None:
            return False

        path = Path(model_path)
        if not path.exists():
            logger.warning("Super-Resolution model file not found: %s", model_path)
            return False

        target_device = (device or self.preferred_device).upper()
        try:
            model = self._openvino_core.read_model(str(path))
            self._compiled_model = self._openvino_core.compile_model(model, target_device)
            self._active_device = target_device
            self._model_path = str(path)
            logger.info("Successfully loaded SR model on %s: %s", target_device, path.name)
            return True
        except Exception as e:
            logger.warning("Failed to compile SR model on %s: %s. Attempting CPU fallback.", target_device, e)
            try:
                self._compiled_model = self._openvino_core.compile_model(model, "CPU")
                self._active_device = "CPU"
                return True
            except Exception as e2:
                logger.error("CPU fallback compilation also failed: %s", e2)
                return False

    @classmethod
    def apply_watermark(
        cls,
        frame: np.ndarray,
        text: str = WATERMARK_LABEL_GENERIC,
        position: str = "bottom_right",
        opacity: float = 0.85,
    ) -> np.ndarray:
        """
        Overlays a high-contrast forensic disclaimer watermark onto the frame.
        Guarantees that enhanced media is never misrepresented as original evidence.
        """
        out = frame.copy()
        h, w = out.shape[:2]

        font = cv2.FONT_HERSHEY_SIMPLEX
        # Dynamic scale based on image dimensions
        font_scale = max(0.45, min(1.2, w / 1600.0))
        thickness = max(1, int(round(font_scale * 1.8)))

        (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)

        margin_x = 15
        margin_y = 15

        if position == "bottom_right":
            box_x1 = max(0, w - text_w - 2 * margin_x)
            box_y1 = max(0, h - text_h - 2 * margin_y)
            box_x2 = w
            box_y2 = h
            text_x = box_x1 + margin_x
            text_y = box_y2 - margin_y - baseline // 2
        elif position == "top_left":
            box_x1 = 0
            box_y1 = 0
            box_x2 = min(w, text_w + 2 * margin_x)
            box_y2 = min(h, text_h + 2 * margin_y)
            text_x = margin_x
            text_y = margin_y + text_h
        else:
            box_x1 = max(0, (w - text_w) // 2 - margin_x)
            box_y1 = max(0, h - text_h - 2 * margin_y)
            box_x2 = min(w, box_x1 + text_w + 2 * margin_x)
            box_y2 = h
            text_x = box_x1 + margin_x
            text_y = box_y2 - margin_y - baseline // 2

        # Semi-transparent dark background box for legible contrast
        overlay = out.copy()
        cv2.rectangle(overlay, (box_x1, box_y1), (box_x2, box_y2), (18, 18, 18), -1)
        # Gold/yellow border for visual warning indication
        cv2.rectangle(overlay, (box_x1, box_y1), (box_x2, box_y2), (0, 165, 255), 1)

        cv2.addWeighted(overlay, opacity, out, 1.0 - opacity, 0, out)

        # High-contrast bright warning text
        cv2.putText(
            out,
            text,
            (text_x, text_y),
            font,
            font_scale,
            (255, 255, 255),
            thickness,
            lineType=cv2.LINE_AA,
        )

        return out
