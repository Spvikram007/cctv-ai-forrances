"""
Automatic Number Plate Recognition (ANPR) Engine Package.
"""

from engines.anpr_engine.plate_detector import PlateDetector, PlateCandidate
from engines.anpr_engine.ocr_recognizer import PlateOCRRecognizer, OCRResult
from engines.anpr_engine.anpr_pipeline import ANPRPipeline, ANPRResult, anpr_pipeline
from engines.anpr_engine.anpr_search import ANPRSearchEngine

__all__ = [
    "PlateDetector",
    "PlateCandidate",
    "PlateOCRRecognizer",
    "OCRResult",
    "ANPRPipeline",
    "ANPRResult",
    "anpr_pipeline",
    "ANPRSearchEngine",
]
