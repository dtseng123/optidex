#!/usr/bin/env python3
"""
Kalman Filter Tracker for Detection Boxes and Segmentation Masks

Provides temporal smoothing for:
- Bounding boxes (reduces jitter in detection overlays)
- Segmentation masks (temporal consistency)

Can be used by both optidex live_detection.py and vr-passthrough.
"""

import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import time


@dataclass
class TrackedBox:
    """A tracked bounding box with Kalman state."""
    class_name: str
    confidence: float
    bbox: List[int]  # [x1, y1, x2, y2]
    track_id: int
    age: int = 0  # frames since last detection
    hits: int = 1  # consecutive detections


class KalmanBoxTracker:
    """
    Kalman filter for tracking a single bounding box.
    
    State: [x, y, w, h, vx, vy, vw, vh]
    where (x,y) is center, (w,h) is size, and v* are velocities.
    """
    
    def __init__(self, bbox: List[int], process_noise: float = 0.1, measurement_noise: float = 0.5):
        """
        Initialize tracker with initial bounding box [x1, y1, x2, y2].
        
        Args:
            bbox: Initial bounding box
            process_noise: How much we expect the object to move (higher = more responsive)
            measurement_noise: How noisy the detections are (higher = more smoothing)
        """
        # Convert [x1,y1,x2,y2] to [cx, cy, w, h]
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        w = x2 - x1
        h = y2 - y1
        
        # State vector [cx, cy, w, h, vx, vy, vw, vh]
        self.state = np.array([cx, cy, w, h, 0, 0, 0, 0], dtype=np.float64)
        
        # State covariance matrix
        self.P = np.eye(8) * 100  # High initial uncertainty
        self.P[4:, 4:] *= 10  # Higher uncertainty for velocities
        
        # State transition matrix (constant velocity model)
        self.F = np.eye(8)
        self.F[0, 4] = 1  # cx += vx
        self.F[1, 5] = 1  # cy += vy
        self.F[2, 6] = 1  # w += vw
        self.F[3, 7] = 1  # h += vh
        
        # Measurement matrix (we only observe position, not velocity)
        self.H = np.zeros((4, 8))
        self.H[0, 0] = 1  # cx
        self.H[1, 1] = 1  # cy
        self.H[2, 2] = 1  # w
        self.H[3, 3] = 1  # h
        
        # Process noise
        self.Q = np.eye(8) * process_noise
        self.Q[4:, 4:] *= 2  # More noise for velocity
        
        # Measurement noise
        self.R = np.eye(4) * measurement_noise
        
        self.time_since_update = 0
        self.hits = 1
        self.age = 0
    
    def predict(self) -> List[int]:
        """
        Predict next state and return predicted bbox [x1, y1, x2, y2].
        """
        # Predict state
        self.state = self.F @ self.state
        
        # Predict covariance
        self.P = self.F @ self.P @ self.F.T + self.Q
        
        self.age += 1
        self.time_since_update += 1
        
        return self._state_to_bbox()
    
    def update(self, bbox: List[int]) -> List[int]:
        """
        Update state with new measurement and return smoothed bbox.
        """
        # Convert bbox to measurement
        x1, y1, x2, y2 = bbox
        z = np.array([
            (x1 + x2) / 2,  # cx
            (y1 + y2) / 2,  # cy
            x2 - x1,        # w
            y2 - y1         # h
        ])
        
        # Kalman gain
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        
        # Update state
        y = z - self.H @ self.state  # Innovation
        self.state = self.state + K @ y
        
        # Update covariance
        I = np.eye(8)
        self.P = (I - K @ self.H) @ self.P
        
        self.time_since_update = 0
        self.hits += 1
        
        return self._state_to_bbox()
    
    def _state_to_bbox(self) -> List[int]:
        """Convert state [cx, cy, w, h, ...] to bbox [x1, y1, x2, y2]."""
        cx, cy, w, h = self.state[:4]
        w = max(1, w)  # Ensure positive
        h = max(1, h)
        return [
            int(cx - w / 2),
            int(cy - h / 2),
            int(cx + w / 2),
            int(cy + h / 2)
        ]
    
    def get_state(self) -> Tuple[List[int], float, float]:
        """Return (bbox, velocity_magnitude, uncertainty)."""
        bbox = self._state_to_bbox()
        vel = np.sqrt(self.state[4]**2 + self.state[5]**2)
        uncertainty = np.trace(self.P[:4, :4])
        return bbox, vel, uncertainty


class MultiObjectTracker:
    """
    Multi-object tracker using Kalman filters.
    
    Handles:
    - Matching detections to existing tracks (IoU-based)
    - Creating new tracks for unmatched detections
    - Removing stale tracks
    """
    
    def __init__(self, 
                 max_age: int = 5,
                 min_hits: int = 2,
                 iou_threshold: float = 0.3,
                 process_noise: float = 0.1,
                 measurement_noise: float = 0.5):
        """
        Args:
            max_age: Max frames to keep track without detection
            min_hits: Min detections before track is confirmed
            iou_threshold: Minimum IoU for matching
            process_noise: Kalman process noise (higher = more responsive)
            measurement_noise: Kalman measurement noise (higher = more smoothing)
        """
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        
        self.trackers: Dict[int, Tuple[KalmanBoxTracker, str, float]] = {}  # id -> (tracker, class_name, confidence)
        self.next_id = 0
    
    def update(self, detections: List[Dict]) -> List[TrackedBox]:
        """
        Update trackers with new detections.
        
        Args:
            detections: List of {'bbox': [x1,y1,x2,y2], 'class_name': str, 'confidence': float}
            
        Returns:
            List of TrackedBox with smoothed bboxes
        """
        # Predict all existing trackers
        for track_id, (tracker, _, _) in self.trackers.items():
            tracker.predict()
        
        # Match detections to trackers
        matched, unmatched_dets, unmatched_tracks = self._match_detections(detections)
        
        # Update matched trackers
        for det_idx, track_id in matched:
            det = detections[det_idx]
            tracker, _, _ = self.trackers[track_id]
            tracker.update(det['bbox'])
            self.trackers[track_id] = (tracker, det['class_name'], det['confidence'])
        
        # Create new trackers for unmatched detections
        for det_idx in unmatched_dets:
            det = detections[det_idx]
            tracker = KalmanBoxTracker(
                det['bbox'],
                process_noise=self.process_noise,
                measurement_noise=self.measurement_noise
            )
            self.trackers[self.next_id] = (tracker, det['class_name'], det['confidence'])
            self.next_id += 1
        
        # Remove stale trackers
        to_remove = []
        for track_id in unmatched_tracks:
            tracker, _, _ = self.trackers[track_id]
            if tracker.time_since_update > self.max_age:
                to_remove.append(track_id)
        for track_id in to_remove:
            del self.trackers[track_id]
        
        # Return confirmed tracks
        results = []
        for track_id, (tracker, class_name, confidence) in self.trackers.items():
            if tracker.hits >= self.min_hits or tracker.time_since_update == 0:
                results.append(TrackedBox(
                    class_name=class_name,
                    confidence=confidence,
                    bbox=tracker._state_to_bbox(),
                    track_id=track_id,
                    age=tracker.age,
                    hits=tracker.hits
                ))
        
        return results
    
    def _match_detections(self, detections: List[Dict]) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """
        Match detections to existing trackers using IoU.
        
        Returns:
            (matched_pairs, unmatched_detection_indices, unmatched_tracker_ids)
        """
        if not detections or not self.trackers:
            return [], list(range(len(detections))), list(self.trackers.keys())
        
        # Build IoU matrix
        det_bboxes = [d['bbox'] for d in detections]
        track_ids = list(self.trackers.keys())
        track_bboxes = [self.trackers[tid][0]._state_to_bbox() for tid in track_ids]
        
        iou_matrix = np.zeros((len(detections), len(track_ids)))
        for i, det_bbox in enumerate(det_bboxes):
            for j, track_bbox in enumerate(track_bboxes):
                iou_matrix[i, j] = self._iou(det_bbox, track_bbox)
        
        # Greedy matching (could use Hungarian algorithm for optimal)
        matched = []
        unmatched_dets = set(range(len(detections)))
        unmatched_tracks = set(track_ids)
        
        while True:
            if iou_matrix.size == 0:
                break
            max_iou = iou_matrix.max()
            if max_iou < self.iou_threshold:
                break
            
            det_idx, track_idx = np.unravel_index(iou_matrix.argmax(), iou_matrix.shape)
            track_id = track_ids[track_idx]
            
            matched.append((det_idx, track_id))
            unmatched_dets.discard(det_idx)
            unmatched_tracks.discard(track_id)
            
            # Zero out matched row and column
            iou_matrix[det_idx, :] = 0
            iou_matrix[:, track_idx] = 0
        
        return matched, list(unmatched_dets), list(unmatched_tracks)
    
    @staticmethod
    def _iou(bbox1: List[int], bbox2: List[int]) -> float:
        """Calculate IoU between two bboxes [x1, y1, x2, y2]."""
        x1 = max(bbox1[0], bbox2[0])
        y1 = max(bbox1[1], bbox2[1])
        x2 = min(bbox1[2], bbox2[2])
        y2 = min(bbox1[3], bbox2[3])
        
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        
        union = area1 + area2 - inter
        
        return inter / union if union > 0 else 0
    
    def reset(self):
        """Clear all trackers."""
        self.trackers.clear()
        self.next_id = 0


class MaskSmoother:
    """
    Temporal smoothing for segmentation masks.
    
    Uses exponential moving average with optional morphological cleanup.
    """
    
    def __init__(self, 
                 alpha: float = 0.7,
                 threshold: float = 0.5,
                 morph_kernel_size: int = 5):
        """
        Args:
            alpha: EMA weight for new frame (higher = less smoothing, more responsive)
            threshold: Threshold for binarizing smoothed mask
            morph_kernel_size: Kernel size for morphological operations (0 to disable)
        """
        self.alpha = alpha
        self.threshold = threshold
        self.morph_kernel_size = morph_kernel_size
        
        self._prev_mask: Optional[np.ndarray] = None
        self._shape: Optional[Tuple[int, int]] = None
        
        # Morphological kernel
        if morph_kernel_size > 0:
            import cv2
            self._morph_kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, 
                (morph_kernel_size, morph_kernel_size)
            )
        else:
            self._morph_kernel = None
    
    def update(self, mask: np.ndarray, class_id: Optional[int] = None) -> np.ndarray:
        """
        Update with new mask and return smoothed result.
        
        Args:
            mask: Input mask (HxW, uint8 class IDs or binary)
            class_id: If provided, extract this class from mask first
            
        Returns:
            Smoothed binary mask (HxW, uint8, 0 or 255)
        """
        import cv2
        
        # Extract class if specified
        if class_id is not None:
            binary = (mask == class_id).astype(np.float32)
        else:
            binary = (mask > 0).astype(np.float32)
        
        # Handle shape changes
        if self._prev_mask is None or self._shape != binary.shape:
            self._prev_mask = binary
            self._shape = binary.shape
        
        # Exponential moving average
        smoothed = self.alpha * binary + (1 - self.alpha) * self._prev_mask
        self._prev_mask = smoothed
        
        # Threshold to binary
        result = (smoothed >= self.threshold).astype(np.uint8) * 255
        
        # Morphological cleanup (close small holes, smooth edges)
        if self._morph_kernel is not None:
            result = cv2.morphologyEx(result, cv2.MORPH_CLOSE, self._morph_kernel)
            result = cv2.morphologyEx(result, cv2.MORPH_OPEN, self._morph_kernel)
        
        return result
    
    def reset(self):
        """Reset temporal state."""
        self._prev_mask = None
        self._shape = None


class StereoMaskSmoother:
    """Paired mask smoothers for stereo VR (left and right eyes)."""
    
    def __init__(self, **kwargs):
        self.left = MaskSmoother(**kwargs)
        self.right = MaskSmoother(**kwargs)
    
    def update(self, 
               left_mask: Optional[np.ndarray], 
               right_mask: Optional[np.ndarray],
               class_id: Optional[int] = None) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Update both smoothers and return smoothed masks."""
        left_out = self.left.update(left_mask, class_id) if left_mask is not None else None
        right_out = self.right.update(right_mask, class_id) if right_mask is not None else None
        return left_out, right_out
    
    def reset(self):
        self.left.reset()
        self.right.reset()


# Convenience functions for easy integration

def create_tracker(smoothing: str = "medium") -> MultiObjectTracker:
    """
    Create a tracker with preset smoothing level.
    
    Args:
        smoothing: "low" (responsive), "medium" (balanced), "high" (very smooth)
    """
    presets = {
        "low": {"process_noise": 0.3, "measurement_noise": 0.2, "max_age": 3},
        "medium": {"process_noise": 0.1, "measurement_noise": 0.5, "max_age": 5},
        "high": {"process_noise": 0.05, "measurement_noise": 1.0, "max_age": 8},
    }
    params = presets.get(smoothing, presets["medium"])
    return MultiObjectTracker(**params)


def create_mask_smoother(smoothing: str = "medium") -> MaskSmoother:
    """
    Create a mask smoother with preset smoothing level.
    
    Args:
        smoothing: "low" (responsive), "medium" (balanced), "high" (very smooth)
    """
    presets = {
        "low": {"alpha": 0.85, "threshold": 0.4, "morph_kernel_size": 3},
        "medium": {"alpha": 0.7, "threshold": 0.5, "morph_kernel_size": 5},
        "high": {"alpha": 0.5, "threshold": 0.5, "morph_kernel_size": 7},
    }
    params = presets.get(smoothing, presets["medium"])
    return MaskSmoother(**params)


if __name__ == "__main__":
    # Simple test
    print("Testing Kalman Tracker...")
    
    tracker = MultiObjectTracker()
    
    # Simulate detections with noise
    np.random.seed(42)
    base_bbox = [100, 100, 200, 200]
    
    for frame in range(20):
        # Add noise to simulate jittery detections
        noise = np.random.randint(-10, 10, 4)
        noisy_bbox = [b + n for b, n in zip(base_bbox, noise)]
        
        # Move the box slightly
        base_bbox = [b + 5 for b in base_bbox]
        
        detections = [{
            'bbox': noisy_bbox,
            'class_name': 'person',
            'confidence': 0.9
        }]
        
        results = tracker.update(detections)
        
        if results:
            r = results[0]
            print(f"Frame {frame:2d}: noisy={noisy_bbox} -> smoothed={r.bbox}")
    
    print("\nTesting Mask Smoother...")
    smoother = MaskSmoother(alpha=0.7)
    
    # Simulate noisy masks
    for frame in range(10):
        mask = np.zeros((100, 100), dtype=np.uint8)
        # Add a circle with some noise
        import cv2
        cv2.circle(mask, (50, 50), 30, 255, -1)
        noise = (np.random.random((100, 100)) > 0.9).astype(np.uint8) * 255
        noisy_mask = cv2.bitwise_xor(mask, noise)
        
        smoothed = smoother.update(noisy_mask)
        noisy_pixels = np.sum(noisy_mask > 0)
        smooth_pixels = np.sum(smoothed > 0)
        print(f"Frame {frame}: noisy_pixels={noisy_pixels}, smoothed_pixels={smooth_pixels}")
    
    print("\n✓ Kalman tracker tests complete!")

