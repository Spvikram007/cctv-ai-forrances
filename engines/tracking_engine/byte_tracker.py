"""
ByteTrack Multi-Object Tracker.
Implements the ByteTrack algorithm for persistent object tracking
across video frames with Kalman filter prediction and Hungarian assignment.

Reference: Zhang et al., "ByteTrack: Multi-Object Tracking by Associating Every Detection Box" (2022)
"""

import numpy as np
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from core.logging.logger import get_logger

logger = get_logger("byte_tracker")


@dataclass
class TrackedObject:
    """Active tracked object with persistent ID."""
    track_id: int
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]  # (x, y, w, h) normalized
    pixel_bbox: Tuple[int, int, int, int]  # (x, y, w, h) pixels
    velocity: Tuple[float, float] = (0.0, 0.0)
    frames_tracked: int = 1
    frames_lost: int = 0
    is_active: bool = True
    last_timestamp: float = 0.0

    def center(self) -> Tuple[float, float]:
        return (self.bbox[0] + self.bbox[2] / 2, self.bbox[1] + self.bbox[3] / 2)


class KalmanBoxTracker:
    """
    Simplified Kalman filter for bounding box tracking.
    State: [cx, cy, w, h, vx, vy, vw, vh]
    """

    _next_id = 1

    def __init__(self, bbox: Tuple[float, float, float, float], class_id: int, class_name: str, confidence: float) -> None:
        self.track_id = KalmanBoxTracker._next_id
        KalmanBoxTracker._next_id += 1

        cx = bbox[0] + bbox[2] / 2
        cy = bbox[1] + bbox[3] / 2
        w = bbox[2]
        h = bbox[3]

        self.state = np.array([cx, cy, w, h, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)
        self.class_id = class_id
        self.class_name = class_name
        self.confidence = confidence
        self.hits = 1
        self.time_since_update = 0
        self.age = 0

    def predict(self) -> Tuple[float, float, float, float]:
        """Predict next state using constant velocity model."""
        self.state[0] += self.state[4]
        self.state[1] += self.state[5]
        self.state[2] += self.state[6]
        self.state[3] += self.state[7]
        self.state[2] = max(self.state[2], 0.001)
        self.state[3] = max(self.state[3], 0.001)
        self.age += 1
        self.time_since_update += 1
        return self.get_bbox()

    def update(self, bbox: Tuple[float, float, float, float], confidence: float) -> None:
        """Update state with new observation."""
        cx = bbox[0] + bbox[2] / 2
        cy = bbox[1] + bbox[3] / 2
        w = bbox[2]
        h = bbox[3]

        # Simple alpha-beta filter update
        alpha = 0.6
        old_cx, old_cy = self.state[0], self.state[1]

        self.state[4] = alpha * (cx - old_cx) + (1 - alpha) * self.state[4]
        self.state[5] = alpha * (cy - old_cy) + (1 - alpha) * self.state[5]
        self.state[6] = alpha * (w - self.state[2]) + (1 - alpha) * self.state[6]
        self.state[7] = alpha * (h - self.state[3]) + (1 - alpha) * self.state[7]

        self.state[0] = cx
        self.state[1] = cy
        self.state[2] = w
        self.state[3] = h

        self.confidence = confidence
        self.hits += 1
        self.time_since_update = 0

    def get_bbox(self) -> Tuple[float, float, float, float]:
        """Returns current (x, y, w, h) bounding box."""
        cx, cy, w, h = self.state[:4]
        return (cx - w / 2, cy - h / 2, w, h)


def iou_batch(bboxes_a: np.ndarray, bboxes_b: np.ndarray) -> np.ndarray:
    """
    Computes IoU matrix between two sets of (x, y, w, h) bounding boxes.
    Returns: (len(a), len(b)) IoU matrix.
    """
    if len(bboxes_a) == 0 or len(bboxes_b) == 0:
        return np.empty((len(bboxes_a), len(bboxes_b)), dtype=np.float64)

    # Convert xywh to x1y1x2y2
    a_x1 = bboxes_a[:, 0]
    a_y1 = bboxes_a[:, 1]
    a_x2 = bboxes_a[:, 0] + bboxes_a[:, 2]
    a_y2 = bboxes_a[:, 1] + bboxes_a[:, 3]

    b_x1 = bboxes_b[:, 0]
    b_y1 = bboxes_b[:, 1]
    b_x2 = bboxes_b[:, 0] + bboxes_b[:, 2]
    b_y2 = bboxes_b[:, 1] + bboxes_b[:, 3]

    # Intersection
    inter_x1 = np.maximum(a_x1[:, None], b_x1[None, :])
    inter_y1 = np.maximum(a_y1[:, None], b_y1[None, :])
    inter_x2 = np.minimum(a_x2[:, None], b_x2[None, :])
    inter_y2 = np.minimum(a_y2[:, None], b_y2[None, :])

    inter_area = np.maximum(inter_x2 - inter_x1, 0) * np.maximum(inter_y2 - inter_y1, 0)

    # Union
    area_a = (a_x2 - a_x1) * (a_y2 - a_y1)
    area_b = (b_x2 - b_x1) * (b_y2 - b_y1)
    union_area = area_a[:, None] + area_b[None, :] - inter_area

    iou = np.where(union_area > 0, inter_area / union_area, 0.0)
    return iou


def linear_assignment(cost_matrix: np.ndarray, threshold: float = 0.7) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
    """
    Solves linear assignment using lap.lapjv if available,
    scipy.optimize if available, or greedy matching.
    """
    if cost_matrix.size == 0:
        return [], list(range(cost_matrix.shape[0])), list(range(cost_matrix.shape[1]))

    # Try lap.lapjv first
    try:
        import lap
        cost = 1.0 - cost_matrix
        _, x, y = lap.lapjv(cost, extend_cost=True, cost_limit=(1.0 - threshold))
        matches = []
        for i, j in enumerate(x):
            if j >= 0 and cost_matrix[i, j] >= threshold:
                matches.append((i, j))
        matched_a = set(m[0] for m in matches)
        matched_b = set(m[1] for m in matches)
        unmatched_a = [i for i in range(cost_matrix.shape[0]) if i not in matched_a]
        unmatched_b = [j for j in range(cost_matrix.shape[1]) if j not in matched_b]
        return matches, unmatched_a, unmatched_b
    except ImportError:
        pass

    # Try scipy
    try:
        from scipy.optimize import linear_sum_assignment as scipy_lsa
        cost = 1.0 - cost_matrix
        row_ind, col_ind = scipy_lsa(cost)
        matches = []
        matched_a = set()
        matched_b = set()
        for r, c in zip(row_ind, col_ind):
            if cost_matrix[r, c] >= threshold:
                matches.append((r, c))
                matched_a.add(r)
                matched_b.add(c)
        unmatched_a = [i for i in range(cost_matrix.shape[0]) if i not in matched_a]
        unmatched_b = [j for j in range(cost_matrix.shape[1]) if j not in matched_b]
        return matches, unmatched_a, unmatched_b
    except ImportError:
        pass

    # Greedy fallback
    flat_indices = np.argsort(-cost_matrix.ravel())
    matches = []
    matched_a_set = set()
    matched_b_set = set()

    for flat_idx in flat_indices:
        r = flat_idx // cost_matrix.shape[1]
        c = flat_idx % cost_matrix.shape[1]
        if cost_matrix[r, c] < threshold:
            break
        if r not in matched_a_set and c not in matched_b_set:
            matches.append((r, c))
            matched_a_set.add(r)
            matched_b_set.add(c)

    unmatched_a = [i for i in range(cost_matrix.shape[0]) if i not in matched_a_set]
    unmatched_b = [j for j in range(cost_matrix.shape[1]) if j not in matched_b_set]

    return matches, unmatched_a, unmatched_b


class ByteTracker:
    """
    ByteTrack multi-object tracker.
    Maintains persistent track IDs per camera channel.
    """

    def __init__(
        self,
        high_threshold: float = 0.5,
        low_threshold: float = 0.1,
        match_threshold: float = 0.3,
        max_lost_frames: int = 30,
        min_hits: int = 3,
    ) -> None:
        self.high_threshold = high_threshold
        self.low_threshold = low_threshold
        self.match_threshold = match_threshold
        self.max_lost_frames = max_lost_frames
        self.min_hits = min_hits

        self._active_tracks: List[KalmanBoxTracker] = []
        self._lost_tracks: List[KalmanBoxTracker] = []
        self._removed_tracks: List[KalmanBoxTracker] = []

        self.total_tracks_created = 0

    def reset(self) -> None:
        """Resets all tracks."""
        self._active_tracks.clear()
        self._lost_tracks.clear()
        self._removed_tracks.clear()
        KalmanBoxTracker._next_id = 1

    def update(self, detections, timestamp: float = 0.0) -> List[TrackedObject]:
        """
        Main ByteTrack update step.
        Args:
            detections: List of DetectionResult objects
            timestamp: Current frame timestamp
        Returns:
            List of TrackedObject with persistent IDs
        """
        # Step 1: Predict all existing active and lost tracks forward
        for track in self._active_tracks:
            track.predict()
        for track in self._lost_tracks:
            track.predict()

        # Step 2: Split detections into high-confidence and low-confidence
        high_dets = [d for d in detections if d.confidence >= self.high_threshold]
        low_dets = [d for d in detections if self.low_threshold <= d.confidence < self.high_threshold]

        # Step 3: Match high-confidence detections with active tracks
        matched_active: List[KalmanBoxTracker] = []
        unmatched_active: List[KalmanBoxTracker] = []
        unmatched_high_dets = list(high_dets)

        if self._active_tracks and high_dets:
            track_bboxes = np.array([t.get_bbox() for t in self._active_tracks])
            det_bboxes = np.array([(d.bbox_x, d.bbox_y, d.bbox_w, d.bbox_h) for d in high_dets])
            iou_matrix = iou_batch(track_bboxes, det_bboxes)

            matches_1, unmatched_t_idx, unmatched_d_idx = linear_assignment(
                iou_matrix, threshold=self.match_threshold
            )

            for t_idx, d_idx in matches_1:
                t = self._active_tracks[t_idx]
                d = high_dets[d_idx]
                t.update((d.bbox_x, d.bbox_y, d.bbox_w, d.bbox_h), d.confidence)
                t.class_id = d.class_id
                t.class_name = d.class_name
                matched_active.append(t)

            unmatched_active = [self._active_tracks[i] for i in unmatched_t_idx]
            unmatched_high_dets = [high_dets[i] for i in unmatched_d_idx]
        else:
            unmatched_active = list(self._active_tracks)

        # Step 4: Match low-confidence detections with remaining active tracks
        unmatched_active_after_low: List[KalmanBoxTracker] = []

        if unmatched_active and low_dets:
            track_bboxes_2 = np.array([t.get_bbox() for t in unmatched_active])
            det_bboxes_2 = np.array([(d.bbox_x, d.bbox_y, d.bbox_w, d.bbox_h) for d in low_dets])
            iou_matrix_2 = iou_batch(track_bboxes_2, det_bboxes_2)

            matches_2, unmatched_t_idx_2, _ = linear_assignment(
                iou_matrix_2, threshold=self.match_threshold
            )

            for t_idx, d_idx in matches_2:
                t = unmatched_active[t_idx]
                d = low_dets[d_idx]
                t.update((d.bbox_x, d.bbox_y, d.bbox_w, d.bbox_h), d.confidence)
                matched_active.append(t)

            unmatched_active_after_low = [unmatched_active[i] for i in unmatched_t_idx_2]
        else:
            unmatched_active_after_low = list(unmatched_active)

        # Step 5: Match remaining high-confidence detections with lost tracks
        recovered_tracks: List[KalmanBoxTracker] = []
        remaining_lost_tracks: List[KalmanBoxTracker] = []
        new_dets_for_init = list(unmatched_high_dets)

        if self._lost_tracks and unmatched_high_dets:
            lost_bboxes = np.array([t.get_bbox() for t in self._lost_tracks])
            new_det_bboxes = np.array([(d.bbox_x, d.bbox_y, d.bbox_w, d.bbox_h) for d in unmatched_high_dets])
            iou_matrix_3 = iou_batch(lost_bboxes, new_det_bboxes)

            matches_3, unmatched_l_idx, unmatched_d_idx_3 = linear_assignment(
                iou_matrix_3, threshold=self.match_threshold
            )

            for l_idx, d_idx in matches_3:
                t = self._lost_tracks[l_idx]
                d = unmatched_high_dets[d_idx]
                t.update((d.bbox_x, d.bbox_y, d.bbox_w, d.bbox_h), d.confidence)
                recovered_tracks.append(t)

            remaining_lost_tracks = [self._lost_tracks[i] for i in unmatched_l_idx]
            new_dets_for_init = [unmatched_high_dets[i] for i in unmatched_d_idx_3]
        else:
            remaining_lost_tracks = list(self._lost_tracks)

        # Step 6: Create new tracks for remaining unmatched high-confidence detections
        created_tracks: List[KalmanBoxTracker] = []
        for d in new_dets_for_init:
            new_track = KalmanBoxTracker(
                bbox=(d.bbox_x, d.bbox_y, d.bbox_w, d.bbox_h),
                class_id=d.class_id,
                class_name=d.class_name,
                confidence=d.confidence,
            )
            created_tracks.append(new_track)
            self.total_tracks_created += 1

        # Step 7: Rebuild active tracks
        self._active_tracks = matched_active + recovered_tracks + created_tracks

        # Step 8: Rebuild lost tracks (unmatched active + remaining lost)
        new_lost: List[KalmanBoxTracker] = []
        for t in unmatched_active_after_low + remaining_lost_tracks:
            if t.time_since_update <= self.max_lost_frames:
                new_lost.append(t)
            else:
                self._removed_tracks.append(t)

        self._lost_tracks = new_lost

        # Step 9: Assemble result (tracks with enough hits or newly updated)
        result: List[TrackedObject] = []
        for track in self._active_tracks:
            if track.hits >= self.min_hits or track.time_since_update == 0:
                bbox = track.get_bbox()
                result.append(TrackedObject(
                    track_id=track.track_id,
                    class_id=track.class_id,
                    class_name=track.class_name,
                    confidence=track.confidence,
                    bbox=bbox,
                    pixel_bbox=(0, 0, 0, 0),
                    velocity=(float(track.state[4]), float(track.state[5])),
                    frames_tracked=track.hits,
                    frames_lost=track.time_since_update,
                    is_active=track.time_since_update == 0,
                    last_timestamp=timestamp,
                ))

        return result

    @property
    def active_track_count(self) -> int:
        return len(self._active_tracks)

    @property
    def lost_track_count(self) -> int:
        return len(self._lost_tracks)
