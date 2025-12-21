#!/usr/bin/env python3
"""
Smart Observer - Watch for specific objects with live video display
Uses Edge TPU for fast inference, falls back to YOLO-World for custom objects.
Shows live detection video on display with rolling buffer recording.

Recording behavior:
- Keeps a 15-second rolling buffer of frames
- When object detected: saves buffer + continues recording
- Stops recording 10 seconds after last detection
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
import threading

# Add coral-models to path for EdgeTPUClient
sys.path.insert(0, '/home/dash/coral-models')

from picamera2 import Picamera2
from PIL import Image, ImageDraw, ImageFont

# Import Edge TPU client
try:
    from edgetpu_client import EdgeTPUClient
    EDGETPU_AVAILABLE = True
except ImportError:
    EDGETPU_AVAILABLE = False

# Configuration
TRIGGER_FILE = "/tmp/whisplay_trigger_event.json"
TRIGGER_IMAGE = "/tmp/whisplay_trigger_image.jpg"
STATE_FILE = "/tmp/observer_state.json"
FRAME_OUTPUT = "/tmp/whisplay_observer_frame.jpg"
IMAGE_DIR = os.path.expanduser("~/ai-pi/captures/observer")
VIDEO_DIR = os.path.expanduser("~/ai-pi/captures/observer")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

# Recording settings
PRE_BUFFER_SECONDS = 15  # Keep 15 seconds before detection
POST_DETECTION_SECONDS = 10  # Continue 10 seconds after last detection
TARGET_FPS = 15

# COCO classes available on Edge TPU
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


def draw_detections(frame, detections, target_objects, detection_count, is_recording=False, is_detecting=False):
    """Draw bounding boxes and info overlay on frame."""
    height, width = frame.shape[:2]
    
    target_lower = [t.lower() for t in target_objects]
    
    for det in detections:
        cls_name = det['class_name'].lower()
        if cls_name in target_lower:
            bbox = det['bbox']
            conf = det['confidence']
            
            # Green when detecting, yellow otherwise
            color = (0, 255, 0) if is_detecting else (0, 255, 255)
            cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)
            
            label = f"{cls_name}: {conf:.2f}"
            cv2.putText(frame, label, (bbox[0], bbox[1] - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    
    # Draw overlay info
    cv2.putText(frame, f"Watching: {', '.join(target_objects)}", (10, 30),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    cv2.putText(frame, f"Detections: {detection_count}", (10, 60),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    
    # Recording indicator (RGB format - red is 255,0,0)
    if is_recording:
        cv2.circle(frame, (width - 30, 30), 10, (255, 0, 0), -1)  # Red dot
        cv2.putText(frame, "REC", (width - 70, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
    
    if is_detecting:
        cv2.putText(frame, "DETECTED!", (10, height - 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    
    return frame


def save_video_clip(frames, video_path, fps=15):
    """Save frames to video file."""
    if not frames:
        return False
    
    height, width = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(video_path, fourcc, fps, (width, height))
    
    for frame in frames:
        # Convert RGB to BGR for OpenCV
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        writer.write(frame_bgr)
    
    writer.release()
    return True


def main():
    parser = argparse.ArgumentParser(description="Smart Observer - Watch for objects with rolling buffer recording")
    parser.add_argument("objects", nargs='+', help="Objects to watch for")
    parser.add_argument("--confidence", type=float, default=0.5, help="Detection confidence threshold")
    parser.add_argument("--stability", type=int, default=3, help="Consecutive frames to confirm detection")
    parser.add_argument("--visualize", action="store_true", help="Show live video on display")
    parser.add_argument("--record", action="store_true", help="Enable rolling buffer recording")
    parser.add_argument("--continuous", action="store_true", help="Keep watching after saving clips")
    parser.add_argument("--pre-buffer", type=int, default=PRE_BUFFER_SECONDS, help="Seconds to keep before detection")
    parser.add_argument("--post-buffer", type=int, default=POST_DETECTION_SECONDS, help="Seconds after last detection")
    
    args = parser.parse_args()
    target_objects = args.objects
    
    print(f"Smart Observer starting...", file=sys.stderr)
    print(f"Watching for: {', '.join(target_objects)}", file=sys.stderr)
    print(f"Recording: {args.record}, Continuous: {args.continuous}", file=sys.stderr)
    print(f"Rolling buffer: {args.pre_buffer}s before, {args.post_buffer}s after", file=sys.stderr)
    
    # Decide backend
    use_edgetpu = False
    client = None
    model = None
    
    if all_are_coco_classes(target_objects) and EDGETPU_AVAILABLE:
        try:
            client = EdgeTPUClient(host='localhost')
            if client.ping('detection'):
                use_edgetpu = True
                print("Using Edge TPU for detection", file=sys.stderr)
        except:
            pass
    
    if not use_edgetpu:
        print("Using YOLO-World for detection", file=sys.stderr)
        try:
            from ultralytics import YOLO
            model = YOLO(os.environ.get('YOLO_MODEL', 'yolov8s-world.pt'))
            model.set_classes(target_objects)
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
    
    # Rolling buffer for pre-detection frames
    buffer_size = args.pre_buffer * TARGET_FPS
    frame_buffer = deque(maxlen=buffer_size)
    
    # Recording state
    is_recording = False
    recording_frames = []
    last_detection_time = 0
    
    # Create state file
    state_data = {
        "status": "running",
        "pid": os.getpid(),
        "objects": target_objects,
        "detections": 0,
        "clips_saved": 0,
        "backend": "edgetpu" if use_edgetpu else "yolo"
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state_data, f)
    
    consecutive_detections = 0
    total_detections = 0
    clips_saved = 0
    target_lower = [t.lower() for t in target_objects]
    
    try:
        while True:
            if not os.path.exists(STATE_FILE):
                print("State file removed, stopping...", file=sys.stderr)
                break
            
            frame_start = time.time()
            
            # Capture frame
            frame = picam2.capture_array()  # RGB
            
            # Run detection
            detections = []
            
            if use_edgetpu:
                pil_image = Image.fromarray(frame)
                buffer = BytesIO()
                pil_image.save(buffer, format='JPEG', quality=85)
                image_bytes = buffer.getvalue()
                
                result = client.detect_objects(image_bytes, classes=target_objects, threshold=args.confidence)
                detections = result if isinstance(result, list) else []
            else:
                results = model(frame, conf=args.confidence, verbose=False)
                for r in results:
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        cls_name = r.names[cls_id]
                        bbox = box.xyxy[0].tolist()
                        detections.append({
                            'class_name': cls_name,
                            'confidence': float(box.conf[0]),
                            'bbox': [int(x) for x in bbox]
                        })
            
            # Filter for target objects
            found_objects = [d for d in detections if d['class_name'].lower() in target_lower]
            is_detecting = len(found_objects) > 0
            
            # Draw on frame
            annotated_frame = draw_detections(
                frame.copy(), detections, target_objects, 
                total_detections, is_recording, is_detecting
            )
            
            # Always add to rolling buffer
            if args.record:
                frame_buffer.append(annotated_frame.copy())
            
            # Handle detection state
            if is_detecting:
                consecutive_detections += 1
                last_detection_time = time.time()
                
                # Confirmed detection after stability threshold
                if consecutive_detections >= args.stability and not is_recording:
                    total_detections += 1
                    print(f"CONFIRMED DETECTION #{total_detections}", file=sys.stderr)
                    
                    # Save trigger image
                    trigger_image = Image.fromarray(annotated_frame)
                    trigger_image.save(TRIGGER_IMAGE, "JPEG", quality=90)
                    
                    # Update state
                    state_data["detections"] = total_detections
                    with open(STATE_FILE, "w") as f:
                        json.dump(state_data, f)
                    
                    # Output trigger event
                    event_data = {
                        "event": "object_detected",
                        "objects": [d['class_name'] for d in found_objects],
                        "count": total_detections,
                        "image_path": TRIGGER_IMAGE,
                        "timestamp": time.time()
                    }
                    print(f"JSON_TRIGGER:{json.dumps(event_data)}", flush=True)
                    
                    # Start recording if enabled
                    if args.record:
                        is_recording = True
                        recording_frames = list(frame_buffer)
                        print(f"Started recording (buffer: {len(recording_frames)} frames)", file=sys.stderr)
                    elif not args.continuous:
                        # If not recording and not continuous, stop after first detection
                        print("Detection confirmed, stopping (no continuous mode)", file=sys.stderr)
                        break
                
                # Add frame to recording
                if is_recording:
                    recording_frames.append(annotated_frame.copy())
            else:
                consecutive_detections = 0
                
                # If recording, add frame and check timeout
                if is_recording:
                    recording_frames.append(annotated_frame.copy())
                    
                    time_since_detection = time.time() - last_detection_time
                    if time_since_detection >= args.post_buffer:
                        # Save the clip
                        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                        video_path = os.path.join(VIDEO_DIR, f"observer-{timestamp}.mp4")
                        
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
                                "detections": total_detections,
                                "duration": len(recording_frames) / TARGET_FPS
                            }
                            print(f"JSON_VIDEO:{json.dumps(video_data)}", flush=True)
                        
                        # Reset recording state
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
        # Save any remaining recording
        if is_recording and recording_frames:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            video_path = os.path.join(VIDEO_DIR, f"observer-{timestamp}.mp4")
            
            print(f"Saving final clip: {len(recording_frames)} frames", file=sys.stderr)
            if save_video_clip(recording_frames, video_path, TARGET_FPS):
                video_data = {
                    "event": "video_saved",
                    "video_path": video_path,
                    "detections": total_detections,
                    "duration": len(recording_frames) / TARGET_FPS
                }
                print(f"JSON_VIDEO:{json.dumps(video_data)}", flush=True)
        
        picam2.stop()
        picam2.close()
        
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        if os.path.exists(FRAME_OUTPUT):
            os.remove(FRAME_OUTPUT)
        
        print(f"Smart Observer stopped. Clips saved: {clips_saved}", file=sys.stderr)


if __name__ == "__main__":
    main()
