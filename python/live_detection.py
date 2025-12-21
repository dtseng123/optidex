#!/usr/bin/env python3
"""
Live object detection with Coral EdgeTPU + YOLO-World fallback
- EdgeTPU: Fast (~21ms/47FPS) for COCO classes (person, car, bottle, etc.)
- YOLO-World: Open vocabulary for custom objects (my red backpack, etc.)
"""
import sys
import os
import time
import json
import cv2
import numpy as np
from picamera2 import Picamera2
from PIL import Image, ImageDraw, ImageFont

# State file for detection control
STATE_FILE = "/tmp/whisplay_detection_state.json"
FRAME_OUTPUT = "/tmp/whisplay_detection_frame.jpg"

# COCO classes supported by EdgeTPU SSD MobileNet
COCO_CLASSES = {
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck',
    'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench',
    'bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra',
    'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
    'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove',
    'skateboard', 'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup',
    'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange',
    'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
    'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse',
    'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
    'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear',
    'hair drier', 'toothbrush'
}

# Try to import EdgeTPU client
EDGETPU_AVAILABLE = False
edgetpu_client = None

try:
    sys.path.insert(0, '/home/dash/coral-models')
    from edgetpu_client import EdgeTPUClient
    
    test_client = EdgeTPUClient()
    if test_client.ping('detection'):
        edgetpu_client = test_client
        EDGETPU_AVAILABLE = True
        print("[EdgeTPU] Detection server available - using hardware acceleration (~47 FPS)", file=sys.stderr)
    else:
        print("[EdgeTPU] Server not responding", file=sys.stderr)
except ImportError as e:
    print(f"[EdgeTPU] Client not available: {e}", file=sys.stderr)
except Exception as e:
    print(f"[EdgeTPU] Connection failed: {e}", file=sys.stderr)


def can_use_edgetpu(target_objects):
    """Check if all target objects are COCO classes (EdgeTPU compatible)."""
    if not EDGETPU_AVAILABLE:
        return False
    
    for obj in target_objects:
        obj_lower = obj.lower().strip()
        if obj_lower not in COCO_CLASSES:
            print(f"[EdgeTPU] '{obj}' not in COCO classes, will use YOLO-World", file=sys.stderr)
            return False
    return True


def save_state(target_objects, is_running, detections=None, backend="unknown"):
    """Save detection state"""
    state = {
        "target_objects": target_objects,
        "is_running": is_running,
        "detections": detections or [],
        "timestamp": time.time(),
        "backend": backend
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def load_state():
    """Load detection state"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return None


def clear_state():
    """Clear detection state"""
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    if os.path.exists(FRAME_OUTPUT):
        os.remove(FRAME_OUTPUT)


def draw_detections(image, detections, target_objects):
    """Draw detection boxes and labels on PIL image."""
    draw = ImageDraw.Draw(image)
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        font = ImageFont.load_default()
        small_font = font
    
    target_objects_lower = [obj.lower() for obj in target_objects]
    
    for det in detections:
        bbox = det['bbox']
        confidence = det['confidence']
        class_name = det['class_name']
        
        is_target = class_name.lower() in target_objects_lower
        color = (0, 255, 0) if is_target else (255, 255, 0)
        
        draw.rectangle(bbox, outline=color, width=3)
        
        label = f"{class_name} {confidence:.2f}"
        try:
            bbox_text = draw.textbbox((bbox[0], bbox[1]-20), label, font=small_font)
            text_width = bbox_text[2] - bbox_text[0]
            text_height = bbox_text[3] - bbox_text[1]
        except AttributeError:
            text_width, text_height = small_font.getsize(label)
        
        draw.rectangle([bbox[0], bbox[1]-text_height-4, bbox[0]+text_width+4, bbox[1]], fill=color)
        draw.text((bbox[0]+2, bbox[1]-text_height-2), label, fill=(0, 0, 0), font=small_font)
    
    return image


def run_live_detection(target_objects, confidence_threshold=0.3, duration=None, video_out=None, force_yolo=False):
    """
    Run live object detection.
    
    Automatically chooses backend:
    - EdgeTPU (fast) for standard COCO objects
    - YOLO-World (flexible) for custom/open-vocabulary objects
    """
    try:
        # Decide which backend to use
        use_edgetpu = can_use_edgetpu(target_objects) and not force_yolo
        backend = "edgetpu" if use_edgetpu else "yolo-world"
        
        print(f"=" * 50)
        print(f"Backend: {backend.upper()}")
        print(f"Objects: {', '.join(target_objects)}")
        print(f"=" * 50)
        
        # Initialize YOLO-World if needed
        model = None
        if not use_edgetpu:
            try:
                from ultralytics import YOLO
            except ImportError:
                print("Error: ultralytics not installed", file=sys.stderr)
                return False
            
            print(f"Loading YOLO-World model for open-vocabulary detection...")
            yolo_model = os.environ.get('YOLO_MODEL', 'yolov8s-world.pt')
            model = YOLO(yolo_model)
            model.set_classes(target_objects)
            print(f"YOLO-World ready!")
        
        # Initialize camera
        print(f"Starting camera...")
        picam2 = Picamera2()
        
        config = picam2.create_video_configuration(
            main={"size": (640, 480), "format": "RGB888"},  # Explicit RGB format for PIL
            lores={"size": (320, 240)},
            controls={
                "FrameRate": 30 if use_edgetpu else 15,  # Faster FPS with EdgeTPU
                "AeEnable": True,
                "AwbEnable": True,
                "Brightness": 0.5,
                "Contrast": 1.3,
            }
        )
        picam2.configure(config)
        picam2.start()
        
        print(f"Warming up camera...", flush=True)
        time.sleep(2.0)
        print(f"Camera ready!", flush=True)
        
        # Video writer
        video_writer = None
        if video_out:
            print(f"Recording to: {video_out}")
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            fps = 30.0 if use_edgetpu else 15.0
            video_writer = cv2.VideoWriter(video_out, fourcc, fps, (640, 480))
        
        print(f"Starting live detection for: {', '.join(target_objects)}")
        save_state(target_objects, True, backend=backend)
        
        start_time = time.time()
        frame_count = 0
        fps_start = time.time()
        
        while True:
            state = load_state()
            if not state or not state.get("is_running"):
                print("Detection stopped by user")
                break
            
            if duration and (time.time() - start_time) > duration:
                print(f"Duration limit reached ({duration}s)")
                break
            
            # Capture frame
            frame = picam2.capture_array("main")
            frame_count += 1
            
            # Calculate FPS every 30 frames
            if frame_count % 30 == 0:
                elapsed = time.time() - fps_start
                fps = 30 / elapsed
                print(f"[PERF] FPS: {fps:.1f} ({backend})", flush=True)
                fps_start = time.time()
            
            image = Image.fromarray(frame)
            detections = []
            
            if use_edgetpu:
                # --- EdgeTPU Path ---
                try:
                    result = edgetpu_client.detect(image, threshold=confidence_threshold)
                    
                    if result.get('success'):
                        all_detections = result.get('detections', [])
                        target_objects_lower = [obj.lower() for obj in target_objects]
                        
                        # Log all detections for debugging (first few frames)
                        if frame_count <= 5 and all_detections:
                            print(f"[EdgeTPU] Raw detections: {[d['class_name'] + ':' + str(d['confidence'])[:4] for d in all_detections]}", flush=True)
                        
                        for det in all_detections:
                            class_name = det['class_name']
                            # Filter for target objects
                            if class_name.lower() in target_objects_lower:
                                detections.append({
                                    'bbox': det['bbox'],
                                    'confidence': det['confidence'],
                                    'class_name': class_name,
                                    'is_target': True
                                })
                    elif frame_count <= 3:
                        print(f"[EdgeTPU] Detection failed: {result}", file=sys.stderr)
                except Exception as e:
                    print(f"[EdgeTPU] Error: {e}", file=sys.stderr)
                    import traceback
                    traceback.print_exc()
            
            else:
                # --- YOLO-World Path ---
                results = model(image, conf=confidence_threshold, verbose=False)
                target_objects_lower = [obj.lower() for obj in target_objects]
                
                for result in results:
                    boxes = result.boxes
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        conf = float(box.conf[0])
                        cls_id = int(box.cls[0])
                        cls_name = result.names[cls_id]
                        
                        is_target = cls_name.lower() in target_objects_lower
                        if is_target or len(target_objects) == 0:
                            detections.append({
                                'bbox': [int(x1), int(y1), int(x2), int(y2)],
                                'confidence': conf,
                                'class_name': cls_name,
                                'is_target': is_target
                            })
            
            # Draw detections
            if detections:
                image = draw_detections(image, detections, target_objects)
                if frame_count % 10 == 0 or frame_count <= 3:
                    print(f"[Detection] Frame {frame_count}: Found {len(detections)} objects", flush=True)
                    for det in detections[:3]:
                        print(f"  - {det['class_name']}: {det['confidence']:.2f}", flush=True)
            else:
                if frame_count % 30 == 0 or frame_count <= 3:
                    print(f"[Detection] Frame {frame_count}: No objects detected", flush=True)
            
            # Write to video
            if video_writer:
                if image.mode == 'RGBA':
                    frame_to_save = np.array(image.convert('RGB'))
                else:
                    frame_to_save = np.array(image)
                frame_to_save = cv2.cvtColor(frame_to_save, cv2.COLOR_RGB2BGR)
                video_writer.write(frame_to_save)
            
            # Save frame for display
            if image.mode == 'RGBA':
                image = image.convert('RGB')
            
            image_resized = image.resize((240, 280), Image.LANCZOS)
            image_resized.save(FRAME_OUTPUT, "JPEG", quality=75)
            
            save_state(target_objects, True, detections, backend=backend)
            
            # Smaller delay with EdgeTPU (faster processing)
            time.sleep(0.02 if use_edgetpu else 0.05)
        
        # Cleanup
        if video_writer:
            video_writer.release()
            print(f"Video saved to: {video_out}")
        
        picam2.stop()
        picam2.close()
        clear_state()
        
        print(f"Detection complete. Processed {frame_count} frames.")
        return True
        
    except Exception as e:
        print(f"Error during detection: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        clear_state()
        return False


def stop_detection():
    """Stop live detection"""
    state = load_state()
    if state:
        save_state(state.get("target_objects", []), False)
        print("Detection stop requested")
        return True
    else:
        print("No active detection")
        return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: live_detection.py <start|stop> [objects...] [--confidence 0.3] [--duration 30] [--video_out path.mp4] [--force-yolo]")
        print("")
        print("Backends:")
        print("  EdgeTPU (~47 FPS) - Used automatically for COCO classes:")
        print(f"    {', '.join(sorted(list(COCO_CLASSES)[:20]))}...")
        print("  YOLO-World (~15 FPS) - Used for custom objects or with --force-yolo")
        print("")
        print("Examples:")
        print("  live_detection.py start person cup bottle  # Uses EdgeTPU (fast)")
        print("  live_detection.py start 'red backpack'     # Uses YOLO-World (open vocab)")
        print("  live_detection.py start person --force-yolo  # Force YOLO-World")
        print("  live_detection.py stop")
        sys.exit(1)
    
    action = sys.argv[1]
    
    if action == "start":
        objects = []
        confidence = 0.3
        duration = None
        video_out = None
        force_yolo = False
        
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--confidence" and i + 1 < len(sys.argv):
                confidence = float(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--duration" and i + 1 < len(sys.argv):
                duration = float(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--video_out" and i + 1 < len(sys.argv):
                video_out = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--force-yolo":
                force_yolo = True
                i += 1
            else:
                objects.append(sys.argv[i])
                i += 1
        
        if not objects:
            print("Error: No objects specified to detect")
            sys.exit(1)
        
        success = run_live_detection(objects, confidence, duration, video_out, force_yolo)
        sys.exit(0 if success else 1)
    
    elif action == "stop":
        success = stop_detection()
        sys.exit(0 if success else 1)
    
    else:
        print(f"Error: Unknown action '{action}'")
        sys.exit(1)
