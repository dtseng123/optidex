#!/usr/bin/env python3
"""
Semantic Sentry - Detect object interactions with live video display
Uses Edge TPU for fast inference, falls back to YOLO for custom objects.
Shows live detection video on display with rolling buffer recording.

Recording behavior:
- Keeps a 15-second rolling buffer of frames
- When interaction detected: saves buffer + continues recording
- Stops recording 10 seconds after last interaction
- Sends clip to Telegram
"""
import sys
import os
import time
import json
import argparse
import cv2
from datetime import datetime
from io import BytesIO
from collections import deque

# Add coral-models to path for EdgeTPUClient
sys.path.insert(0, '/home/dash/coral-models')

from picamera2 import Picamera2
from PIL import Image, ImageDraw

# Import Edge TPU client
try:
    from edgetpu_client import EdgeTPUClient
    EDGETPU_AVAILABLE = True
except ImportError:
    EDGETPU_AVAILABLE = False

# Configuration
STATE_FILE = "/tmp/sentry_state.json"
FRAME_OUTPUT = "/tmp/whisplay_sentry_frame.jpg"
IMAGE_DIR = os.path.expanduser("~/ai-pi/captures/sentry")
VIDEO_DIR = os.path.expanduser("~/ai-pi/captures/sentry")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

# Recording settings
PRE_BUFFER_SECONDS = 15
POST_DETECTION_SECONDS = 10
TARGET_FPS = 15

# COCO classes
COCO_CLASSES = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat',
    'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat',
    'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack',
    'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball',
    'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket',
    'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
    'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake',
    'chair', 'couch', 'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop',
    'mouse', 'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
    'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'
]


def is_coco_class(obj):
    return obj.lower() in [c.lower() for c in COCO_CLASSES]


def all_are_coco_classes(objects):
    return all(is_coco_class(obj) for obj in objects)


def check_interaction(box1, box2, threshold=0.1):
    """Check if two bounding boxes overlap."""
    x1_min, y1_min, x1_max, y1_max = box1
    x2_min, y2_min, x2_max, y2_max = box2

    inter_x_min = max(x1_min, x2_min)
    inter_y_min = max(y1_min, y2_min)
    inter_x_max = min(x1_max, x2_max)
    inter_y_max = min(y1_max, y2_max)

    if inter_x_max <= inter_x_min or inter_y_max <= inter_y_min:
        return False

    inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
    area1 = (x1_max - x1_min) * (y1_max - y1_min)
    area2 = (x2_max - x2_min) * (y2_max - y2_min)
    min_area = min(area1, area2)

    if min_area == 0:
        return False

    return inter_area / min_area > threshold


def draw_detections(frame, detections, needed_classes, interaction_count, 
                    is_recording=False, interaction_found=None):
    """Draw bounding boxes and info overlay."""
    height, width = frame.shape[:2]
    needed_lower = [c.lower() for c in needed_classes]
    
    for det in detections:
        cls_name = det['class_name'].lower()
        if cls_name in needed_lower:
            bbox = det['bbox']
            conf = det['confidence']
            
            # Red if part of interaction, green otherwise
            color = (0, 255, 0)
            if interaction_found:
                if cls_name == interaction_found[0] or cls_name == interaction_found[1]:
                    color = (255, 0, 0)
            
            cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)
            label = f"{cls_name}: {conf:.2f}"
            cv2.putText(frame, label, (bbox[0], bbox[1] - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    
    # Overlay info
    cv2.putText(frame, f"Sentry Mode", (10, 30),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    cv2.putText(frame, f"Interactions: {interaction_count}", (10, 60),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    
    # Recording indicator (RGB format - red is 255,0,0)
    if is_recording:
        cv2.circle(frame, (width - 30, 30), 10, (255, 0, 0), -1)  # Red dot
        cv2.putText(frame, "REC", (width - 70, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
    
    if interaction_found:
        cv2.putText(frame, f"ALERT: {interaction_found[0]} + {interaction_found[1]}!", (10, height - 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)  # Red in RGB
    
    return frame


def save_video_clip(frames, video_path, fps=15):
    """Save frames to video file."""
    if not frames:
        return False
    
    height, width = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(video_path, fourcc, fps, (width, height))
    
    for frame in frames:
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        writer.write(frame_bgr)
    
    writer.release()
    return True


def main():
    parser = argparse.ArgumentParser(description="Semantic Sentry - Detect object interactions with rolling buffer")
    parser.add_argument("pairs", nargs='+', help="Object pairs (obj1,obj2) or use --all-combinations")
    parser.add_argument("--all-combinations", action="store_true", help="Check all pairwise combinations")
    parser.add_argument("--threshold", type=float, default=0.1, help="Overlap threshold")
    parser.add_argument("--confidence", type=float, default=0.5, help="Detection confidence")
    parser.add_argument("--duration", type=int, default=3, help="Consecutive frames to confirm")
    parser.add_argument("--visualize", action="store_true", help="Show live video on display")
    parser.add_argument("--record", action="store_true", help="Enable rolling buffer recording")
    parser.add_argument("--continuous", action="store_true", help="Keep watching after saving clips")
    parser.add_argument("--pre-buffer", type=int, default=PRE_BUFFER_SECONDS, help="Seconds before detection")
    parser.add_argument("--post-buffer", type=int, default=POST_DETECTION_SECONDS, help="Seconds after last detection")
    
    args = parser.parse_args()
    
    # Parse pairs
    target_pairs = []
    needed_classes = set()
    
    if args.all_combinations:
        objects = [obj.lower() for obj in args.pairs]
        needed_classes = set(objects)
        for i, obj1 in enumerate(objects):
            for j, obj2 in enumerate(objects):
                if i < j:
                    target_pairs.append((obj1, obj2))
    else:
        for p in args.pairs:
            if ',' in p:
                o1, o2 = p.split(',')
                target_pairs.append((o1.lower(), o2.lower()))
                needed_classes.add(o1.lower())
                needed_classes.add(o2.lower())
    
    if not target_pairs:
        print("No valid pairs provided", file=sys.stderr)
        sys.exit(1)
    
    print(f"Semantic Sentry starting...", file=sys.stderr)
    print(f"Watching pairs: {target_pairs}", file=sys.stderr)
    print(f"Rolling buffer: {args.pre_buffer}s before, {args.post_buffer}s after", file=sys.stderr)
    
    # Decide backend
    use_edgetpu = False
    client = None
    model = None
    
    if all_are_coco_classes(needed_classes) and EDGETPU_AVAILABLE:
        try:
            client = EdgeTPUClient(host='localhost')
            if client.ping('detection'):
                use_edgetpu = True
                print("Using Edge TPU for detection", file=sys.stderr)
        except:
            pass
    
    if not use_edgetpu:
        print("Using YOLO for detection", file=sys.stderr)
        try:
            from ultralytics import YOLO
            model = YOLO("yolov8n.pt")
        except Exception as e:
            print(f"Error loading YOLO: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Initialize camera
    print("Starting camera...", file=sys.stderr)
    picam2 = Picamera2()
    config = picam2.create_preview_configuration(main={"size": (640, 480), "format": "RGB888"})
    picam2.configure(config)
    picam2.start()
    time.sleep(1)
    
    # Rolling buffer
    buffer_size = args.pre_buffer * TARGET_FPS
    frame_buffer = deque(maxlen=buffer_size)
    
    # Recording state
    is_recording = False
    recording_frames = []
    last_interaction_time = 0
    
    # State file
    state_data = {
        "status": "running",
        "pid": os.getpid(),
        "pairs": [list(p) for p in target_pairs],
        "interactions": 0,
        "clips_saved": 0,
        "backend": "edgetpu" if use_edgetpu else "yolo"
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state_data, f)
    
    consecutive_detections = 0
    total_interactions = 0
    clips_saved = 0
    
    try:
        while True:
            if not os.path.exists(STATE_FILE):
                print("State file removed, stopping...", file=sys.stderr)
                break
            
            frame_start = time.time()
            frame = picam2.capture_array()
            
            # Run detection
            detections = []
            
            if use_edgetpu:
                pil_image = Image.fromarray(frame)
                buffer = BytesIO()
                pil_image.save(buffer, format='JPEG', quality=85)
                image_bytes = buffer.getvalue()
                
                result = client.detect_objects(image_bytes, classes=list(needed_classes), threshold=args.confidence)
                detections = result if isinstance(result, list) else []
            else:
                results = model(frame, conf=args.confidence, verbose=False)
                for r in results:
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        cls_name = model.names[cls_id].lower()
                        if cls_name in needed_classes:
                            bbox = box.xyxy[0].tolist()
                            detections.append({
                                'class_name': cls_name,
                                'confidence': float(box.conf[0]),
                                'bbox': [int(x) for x in bbox]
                            })
            
            # Group by class
            detected_objects = {cls: [] for cls in needed_classes}
            for det in detections:
                cls_name = det['class_name'].lower()
                if cls_name in needed_classes:
                    detected_objects[cls_name].append(det['bbox'])
            
            # Check for interactions
            interaction_found = None
            for (obj1, obj2) in target_pairs:
                list1 = detected_objects.get(obj1, [])
                list2 = detected_objects.get(obj2, [])
                
                for i, b1 in enumerate(list1):
                    for j, b2 in enumerate(list2):
                        if obj1 == obj2 and j <= i:
                            continue
                        if check_interaction(b1, b2, args.threshold):
                            interaction_found = (obj1, obj2, b1, b2)
                            break
                    if interaction_found:
                        break
                if interaction_found:
                    break
            
            is_interacting = interaction_found is not None
            
            # Draw frame
            annotated_frame = draw_detections(
                frame.copy(), detections, needed_classes, 
                total_interactions, is_recording,
                interaction_found[:2] if interaction_found else None
            )
            
            # Add to rolling buffer
            if args.record:
                frame_buffer.append(annotated_frame.copy())
            
            # Handle interaction state
            if is_interacting:
                consecutive_detections += 1
                last_interaction_time = time.time()
                
                # Confirmed interaction after duration threshold
                if consecutive_detections >= args.duration and not is_recording:
                    total_interactions += 1
                    obj1, obj2, b1, b2 = interaction_found
                    print(f"CONFIRMED INTERACTION #{total_interactions}: {obj1} + {obj2}", file=sys.stderr)
                    
                    # Save image
                    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    image_path = os.path.join(IMAGE_DIR, f"sentry-{timestamp}.jpg")
                    
                    cv2.rectangle(annotated_frame, (b1[0], b1[1]), (b1[2], b1[3]), (255, 0, 0), 3)
                    cv2.rectangle(annotated_frame, (b2[0], b2[1]), (b2[2], b2[3]), (255, 0, 0), 3)
                    cv2.imwrite(image_path, cv2.cvtColor(annotated_frame, cv2.COLOR_RGB2BGR))
                    
                    # Update state
                    state_data["interactions"] = total_interactions
                    with open(STATE_FILE, "w") as f:
                        json.dump(state_data, f)
                    
                    # Output trigger
                    event_data = {
                        "event": "interaction_detected",
                        "object1": obj1,
                        "object2": obj2,
                        "count": total_interactions,
                        "image_path": image_path,
                        "timestamp": timestamp
                    }
                    print(f"JSON_TRIGGER:{json.dumps(event_data)}", flush=True)
                    
                    # Start recording if enabled
                    if args.record:
                        is_recording = True
                        recording_frames = list(frame_buffer)
                        print(f"Started recording (buffer: {len(recording_frames)} frames)", file=sys.stderr)
                    elif not args.continuous:
                        # If not recording and not continuous, stop after first interaction
                        print("Interaction confirmed, stopping (no continuous mode)", file=sys.stderr)
                        break
                
                if is_recording:
                    recording_frames.append(annotated_frame.copy())
            else:
                consecutive_detections = 0
                
                if is_recording:
                    recording_frames.append(annotated_frame.copy())
                    
                    time_since_interaction = time.time() - last_interaction_time
                    if time_since_interaction >= args.post_buffer:
                        # Save clip
                        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                        video_path = os.path.join(VIDEO_DIR, f"sentry-{timestamp}.mp4")
                        
                        print(f"Saving clip: {len(recording_frames)} frames ({len(recording_frames)/TARGET_FPS:.1f}s)", file=sys.stderr)
                        
                        if save_video_clip(recording_frames, video_path, TARGET_FPS):
                            clips_saved += 1
                            state_data["clips_saved"] = clips_saved
                            with open(STATE_FILE, "w") as f:
                                json.dump(state_data, f)
                            
                            print(f"Video saved: {video_path}", file=sys.stderr)
                            
                            video_data = {
                                "event": "video_saved",
                                "video_path": video_path,
                                "interactions": total_interactions,
                                "duration": len(recording_frames) / TARGET_FPS
                            }
                            print(f"JSON_VIDEO:{json.dumps(video_data)}", flush=True)
                        
                        is_recording = False
                        recording_frames = []
                        
                        if not args.continuous:
                            break
            
            # Save frame for display
            if args.visualize:
                try:
                    pil_frame = Image.fromarray(annotated_frame)
                    pil_frame_resized = pil_frame.resize((240, 280), Image.LANCZOS)
                    pil_frame_resized.save(FRAME_OUTPUT, "JPEG", quality=80)
                except:
                    pass
            
            # Maintain target FPS
            elapsed = time.time() - frame_start
            sleep_time = max(0, (1.0 / TARGET_FPS) - elapsed)
            time.sleep(sleep_time)
    
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
    finally:
        # Save remaining recording
        if is_recording and recording_frames:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            video_path = os.path.join(VIDEO_DIR, f"sentry-{timestamp}.mp4")
            
            print(f"Saving final clip: {len(recording_frames)} frames", file=sys.stderr)
            if save_video_clip(recording_frames, video_path, TARGET_FPS):
                video_data = {
                    "event": "video_saved",
                    "video_path": video_path,
                    "interactions": total_interactions,
                    "duration": len(recording_frames) / TARGET_FPS
                }
                print(f"JSON_VIDEO:{json.dumps(video_data)}", flush=True)
        
        picam2.stop()
        picam2.close()
        
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        if os.path.exists(FRAME_OUTPUT):
            os.remove(FRAME_OUTPUT)
        
        print(f"Semantic Sentry stopped. Clips saved: {clips_saved}", file=sys.stderr)


if __name__ == "__main__":
    main()
