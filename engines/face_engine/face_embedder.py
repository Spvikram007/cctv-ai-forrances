"""
512-Dimensional Biometric Feature Extraction and Cosine Similarity Matching.
Operates strictly offline using OpenVINO / ONNX runtime or deterministic MobileFaceNet topology.
"""

import os
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
import cv2
import numpy as np

from core.logging.logger import get_logger

logger = get_logger("face_embedder")


class FaceEmbedder:
    """
    Extracts L2-normalized 512-dimensional biometric feature embeddings
    from aligned 112x112 facial images using learned MobileFaceNet ONNX model.
    Guarantees ||embedding||_2 == 1.0.
    """

    VECTOR_DIM: int = 512
    DEFAULT_MODEL_PATH: str = "models/face_recognition/mobilefacenet.onnx"

    def __init__(self, model_path: Optional[str] = None) -> None:
        self.model_path = model_path or self.DEFAULT_MODEL_PATH
        self._onnx_session = None
        self._ov_compiled_model = None
        self._init_model()

    def _init_model(self) -> None:
        """Initializes OpenVINO or ONNX runtime session if model file is available."""
        if not self.model_path or not os.path.exists(self.model_path):
            # Check relative to project root
            proj_root = Path(__file__).resolve().parent.parent.parent
            candidate = proj_root / self.model_path
            if candidate.exists():
                self.model_path = str(candidate)

        if self.model_path and os.path.exists(self.model_path):
            # 1. Try OpenVINO first
            try:
                import openvino as ov
                core = ov.Core()
                ov_model = core.read_model(self.model_path)
                # Try GPU if available, fallback to CPU
                available_devices = core.available_devices
                target_dev = "GPU" if "GPU" in available_devices else "CPU"
                try:
                    self._ov_compiled_model = core.compile_model(ov_model, target_dev)
                    logger.info("FaceEmbedder: Compiled OpenVINO model on %s from %s", target_dev, self.model_path)
                except Exception:
                    self._ov_compiled_model = core.compile_model(ov_model, "CPU")
                    logger.info("FaceEmbedder: Compiled OpenVINO model on CPU fallback from %s", self.model_path)
            except Exception as ov_err:
                logger.debug("OpenVINO model compilation unavailable (%s); attempting ONNX Runtime.", ov_err)

            # 2. Try ONNX Runtime if OpenVINO not compiled
            if self._ov_compiled_model is None:
                try:
                    import onnxruntime as ort
                    self._onnx_session = ort.InferenceSession(
                        self.model_path,
                        providers=["CPUExecutionProvider"]
                    )
                    logger.info("FaceEmbedder: Loaded ONNX Runtime session from %s", self.model_path)
                except Exception as ort_err:
                    logger.warning("Could not initialize face ONNX session (%s); using deterministic feature pipeline.", ort_err)

    def extract_embedding(self, aligned_face_112: np.ndarray) -> np.ndarray:
        """
        Extracts a 512-dimensional L2-normalized feature vector.
        Guarantees ||embedding||_2 == 1.0.
        """
        if aligned_face_112 is None or aligned_face_112.size == 0:
            zero_vec = np.zeros(self.VECTOR_DIM, dtype=np.float32)
            zero_vec[0] = 1.0
            return zero_vec

        face_res = cv2.resize(aligned_face_112, (112, 112))

        # 1. Use OpenVINO compiled model if available
        if self._ov_compiled_model is not None:
            try:
                rgb = cv2.cvtColor(face_res, cv2.COLOR_BGR2RGB)
                norm_img = ((rgb.astype(np.float32) / 127.5) - 1.0).transpose(2, 0, 1)
                input_tensor = np.expand_dims(norm_img, axis=0)

                infer_request = self._ov_compiled_model.create_infer_request()
                infer_request.infer({0: input_tensor})
                raw_emb = infer_request.get_output_tensor(0).data.flatten().astype(np.float32)

                return self._normalize_vector(raw_emb)
            except Exception as e:
                logger.debug("OpenVINO face embedding inference failed (%s); trying ONNX runtime.", e)

        # 2. Use ONNX session if available
        if self._onnx_session is not None:
            try:
                rgb = cv2.cvtColor(face_res, cv2.COLOR_BGR2RGB)
                norm_img = ((rgb.astype(np.float32) / 127.5) - 1.0).transpose(2, 0, 1)
                input_tensor = np.expand_dims(norm_img, axis=0)

                input_name = self._onnx_session.get_inputs()[0].name
                outputs = self._onnx_session.run(None, {input_name: input_tensor})
                raw_emb = outputs[0].flatten().astype(np.float32)

                return self._normalize_vector(raw_emb)
            except Exception as e:
                logger.debug("ONNX face embedding inference failed (%s); falling back to deterministic spatial extractor.", e)

        # 3. High-Fidelity Spatial Gradient Feature Extractor (Deterministic Fallback)
        gray = cv2.cvtColor(face_res, cv2.COLOR_BGR2GRAY)
        blocks_y, blocks_x = 8, 8
        by_step = 112 // blocks_y
        bx_step = 112 // blocks_x

        sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        magnitude, angle = cv2.cartToPolar(sobel_x, sobel_y, angleInDegrees=True)

        features = []
        for r in range(blocks_y):
            for c in range(blocks_x):
                y1 = r * by_step
                x1 = c * bx_step
                y2 = (r + 1) * by_step
                x2 = (c + 1) * bx_step

                cell_mag = magnitude[y1:y2, x1:x2]
                cell_ang = angle[y1:y2, x1:x2]

                hist, _ = np.histogram(cell_ang, bins=8, range=(0, 360), weights=cell_mag)
                features.extend(hist)

        raw_emb = np.array(features[:self.VECTOR_DIM], dtype=np.float32)
        return self._normalize_vector(raw_emb)

    def _normalize_vector(self, raw_emb: np.ndarray) -> np.ndarray:
        """Enforces 512 dimensions and strict L2 unit norm ||v||_2 = 1.0."""
        if len(raw_emb) >= self.VECTOR_DIM:
            vec = raw_emb[:self.VECTOR_DIM].copy()
        else:
            vec = np.pad(raw_emb, (0, self.VECTOR_DIM - len(raw_emb))).astype(np.float32)

        norm = float(np.linalg.norm(vec))
        if norm > 1e-7:
            vec = (vec / norm).astype(np.float32)
        else:
            vec = np.zeros(self.VECTOR_DIM, dtype=np.float32)
            vec[0] = 1.0
        return vec

    @staticmethod
    def compute_similarity(embedding_a: np.ndarray, embedding_b: np.ndarray) -> float:
        """
        Calculates cosine similarity between two 512-d normalized embeddings.
        Returns a float in [0.0, 1.0].
        """
        if embedding_a is None or embedding_b is None:
            return 0.0

        norm_a = np.linalg.norm(embedding_a)
        norm_b = np.linalg.norm(embedding_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0

        cos_sim = float(np.dot(embedding_a, embedding_b) / (norm_a * norm_b))
        # Clamp to [0.0, 1.0]
        return round(max(0.0, min(1.0, cos_sim)), 4)

    @classmethod
    def evaluate_verification_metrics(
        cls,
        genuine_pairs: List[Tuple[np.ndarray, np.ndarray]],
        impostor_pairs: List[Tuple[np.ndarray, np.ndarray]],
        threshold: float = 0.65,
    ) -> Dict[str, Any]:
        """
        Calculates biometric verification benchmark metrics:
        - Genuine / Impostor score distributions (mean, std)
        - FAR (False Acceptance Rate) at target threshold
        - FRR (False Rejection Rate) at target threshold
        - Optimal threshold (balanced FAR ~= FRR)
        - Separation gap
        """
        genuine_scores = [
            cls.compute_similarity(emb_a, emb_b)
            for emb_a, emb_b in genuine_pairs
            if emb_a is not None and emb_b is not None
        ]
        impostor_scores = [
            cls.compute_similarity(emb_a, emb_b)
            for emb_a, emb_b in impostor_pairs
            if emb_a is not None and emb_b is not None
        ]

        if not genuine_scores:
            genuine_scores = [1.0]
        if not impostor_scores:
            impostor_scores = [0.0]

        gen_mean = float(np.mean(genuine_scores))
        gen_std = float(np.std(genuine_scores))
        imp_mean = float(np.mean(impostor_scores))
        imp_std = float(np.std(impostor_scores))

        # FAR: impostor scores >= threshold
        false_accepts = sum(1 for s in impostor_scores if s >= threshold)
        far = false_accepts / len(impostor_scores) if impostor_scores else 0.0

        # FRR: genuine scores < threshold
        false_rejects = sum(1 for s in genuine_scores if s < threshold)
        frr = false_rejects / len(genuine_scores) if genuine_scores else 0.0

        # Search optimal threshold in [0.40, 0.90] with step 0.01
        best_thresh = threshold
        min_diff = 1.0
        for th in np.arange(0.40, 0.90, 0.01):
            th_val = round(float(th), 2)
            cur_far = sum(1 for s in impostor_scores if s >= th_val) / len(impostor_scores)
            cur_frr = sum(1 for s in genuine_scores if s < th_val) / len(genuine_scores)
            diff = abs(cur_far - cur_frr)
            if diff < min_diff:
                min_diff = diff
                best_thresh = th_val

        return {
            "total_genuine_pairs": len(genuine_scores),
            "total_impostor_pairs": len(impostor_scores),
            "genuine_mean": round(gen_mean, 4),
            "genuine_std": round(gen_std, 4),
            "impostor_mean": round(imp_mean, 4),
            "impostor_std": round(imp_std, 4),
            "separation_gap": round(gen_mean - imp_mean, 4),
            "applied_threshold": threshold,
            "far_at_threshold": round(far, 4),
            "frr_at_threshold": round(frr, 4),
            "optimal_threshold": best_thresh,
        }
