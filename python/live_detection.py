#!/usr/bin/env python3
"""
Live object detection with YOLOE on Raspberry Pi 5
Streams video from camera with detection overlays
"""
import sys
import os
import time
import json
from picamera2 import Picamera2
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# State file for detection control
STATE_FILE = "/tmp/whisplay_detection_state.json"
FRAME_OUTPUT = "/tmp/whisplay_detection_frame.jpg"

def save_state(target_objects, is_running, detections=None):
    """Save detection state"""
    state = {
        "target_objects": target_objects,
        "is_running": is_running,
        "detections": detections or [],
        "timestamp": time.time()
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
    """
    Draw detection boxes and labels on image
    
    Args:
        image: PIL Image
        detections: List of detection dicts with bbox, confidence, class_name
        target_objects: List of objects we're looking for (highlight these)
    """
    draw = ImageDraw.Draw(image)
    
    # Try to use a decent font, fallback to default
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        font = ImageFont.load_default()
        small_font = font
    
    for det in detections:
        bbox = det['bbox']  # [x1, y1, x2, y2]
        confidence = det['confidence']
        class_name = det['class_name']
        
        # Highlight target objects in green, others in yellow
        is_target = class_name.lower() in [obj.lower() for obj in target_objects]
        color = (0, 255, 0) if is_target else (255, 255, 0)  # Green or Yellow
        
        # Draw bounding box
        draw.rectangle(bbox, outline=color, width=3)
        
        # Draw label background
        label = f"{class_name} {confidence:.2f}"
        # Get text size - handle both old and new PIL versions
        try:
            bbox_text = draw.textbbox((bbox[0], bbox[1]-20), label, font=small_font)
            text_width = bbox_text[2] - bbox_text[0]
            text_height = bbox_text[3] - bbox_text[1]
        except AttributeError:
            text_width, text_height = small_font.getsize(label)
        
        draw.rectangle([bbox[0], bbox[1]-text_height-4, bbox[0]+text_width+4, bbox[1]], fill=color)
        
        # Draw label text
        draw.text((bbox[0]+2, bbox[1]-text_height-2), label, fill=(0, 0, 0), font=small_font)
    
    return image

def run_live_detection(target_objects, confidence_threshold=0.3, duration=None):
    """
    Run live object detection with YOLOE
    
    Args:
        target_objects: List of object names to detect (e.g., ["person", "cup"])
        confidence_threshold: Minimum confidence for detections (0.0-1.0)
        duration: How long to run (seconds), None for continuous
    """
    try:
        # Import YOLO (ultralytics)
        try:
            from ultralytics import YOLO
        except ImportError:
            print("Error: ultralytics not installed. Install with: pip3 install ultralytics", file=sys.stderr)
            return False
        
        print(f"Loading YOLO-World model for open-vocabulary detection...")
        # Use YOLO-World for detecting any object via text prompts
        # yolov8s-world.pt (small) or yolov8m-world.pt (medium) or yolov8l-world.pt (large)
        # Standard YOLOv8 only detects 80 COCO classes, World models can detect thousands!
        model = YOLO('yolov8s-world.pt')  # World model for custom object detection (~35MB)
        
        # Set custom classes for YOLO-World (this is how we "prompt" it)
        print(f"Setting detection classes: {', '.join(target_objects)}")
        model.set_classes(target_objects)
        
        print(f"Starting camera...")
        picam2 = Picamera2()
        
        # CRITICAL: Use VIDEO configuration (like video recording does) instead of PREVIEW
        # This properly initializes the camera sensor with dual streams
        # VIDEO mode provides better image quality and proper exposure
        config = picam2.create_video_configuration(
            main={"size": (640, 480)},  # Main stream for YOLO processing
            lores={"size": (320, 240)},  # Lower-res stream (required for video config)
            controls={
                "FrameRate": 15,  # 15 FPS to keep processing manageable
                "AeEnable": True,  # Enable auto-exposure
                "AwbEnable": True,  # Enable auto white balance
                "Brightness": 0.5,  # Increase brightness by 50% (was 0.2 = too dark)
                "Contrast": 1.3,  # Increase contrast by 30%
            }
        )
        picam2.configure(config)
        picam2.start()
        
        # Give camera EXTRA time to auto-adjust exposure (3 seconds instead of 2)
        print(f"Warming up camera (auto-exposure adjustment)...", flush=True)
        time.sleep(3.0)
        print(f"Camera ready!", flush=True)
        
        print(f"Starting live detection for: {', '.join(target_objects)}")
        print(f"Confidence threshold: {confidence_threshold}")
        
        save_state(target_objects, True)
        
        start_time = time.time()
        frame_count = 0
        
        while True:
            # Check if we should stop
            state = load_state()
            if not state or not state.get("is_running"):
                print("Detection stopped by user")
                break
            
            # Check duration limit
            if duration and (time.time() - start_time) > duration:
                print(f"Duration limit reached ({duration}s)")
                break
            
            # Capture frame
            frame = picam2.capture_array("main")
            
            # DEBUG: Check if frame is black
            if frame_count == 0:
                import numpy as np
                print(f"[DEBUG] Frame shape: {frame.shape}", flush=True)
                print(f"[DEBUG] Frame dtype: {frame.dtype}", flush=True)
                print(f"[DEBUG] Frame min: {frame.min()}, max: {frame.max()}, mean: {frame.mean():.2f}", flush=True)
            
            # Convert to PIL Image for YOLO
            image = Image.fromarray(frame)
            
            # Run YOLO detection (detect all objects, filter afterward)
            results = model(
                image,
                conf=confidence_threshold,
                verbose=False
            )
            
            # Parse detections and filter for target objects
            detections = []
            target_objects_lower = [obj.lower() for obj in target_objects]
            
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    cls_name = result.names[cls_id]
                    
                    # Filter: only keep target objects OR show all if we're looking for rare objects
                    # This allows both targeted detection and general awareness
                    is_target = cls_name.lower() in target_objects_lower
                    
                    # Always include target objects, optionally include others for context
                    if is_target or len(target_objects) == 0:
                        detections.append({
                            'bbox': [int(x1), int(y1), int(x2), int(y2)],
                            'confidence': conf,
                            'class_name': cls_name,
                            'is_target': is_target
                        })
            
            # Draw detections on image
            if detections:
                image = draw_detections(image, detections, target_objects)
                # Log every detection
                if frame_count % 5 == 0 or frame_count <= 3:
                    print(f"[Detection] Frame {frame_count}: Found {len(detections)} objects", flush=True)
                    for det in detections[:3]:  # Show first 3
                        print(f"  - {det['class_name']}: {det['confidence']:.2f}", flush=True)
            else:
                # Log when no detections
                if frame_count % 10 == 0 or frame_count <= 3:
                    print(f"[Detection] Frame {frame_count}: No objects detected", flush=True)
            
            # Save frame for display (ALWAYS save, even without detections - shows live camera feed)
            # DEBUG: Check image before processing
            if frame_count == 0:
                import numpy as np
                img_array = np.array(image)
                print(f"[DEBUG] PIL Image mode: {image.mode}, size: {image.size}", flush=True)
                print(f"[DEBUG] PIL Image array - min: {img_array.min()}, max: {img_array.max()}, mean: {img_array.mean():.2f}", flush=True)
            
            # CRITICAL FIX: Convert RGBA to RGB BEFORE resizing!
            # Video recording does this same order and works perfectly
            if image.mode == 'RGBA':
                image = image.convert('RGB')
            
            # Scale to LCD resolution (240x280 for Whisplay display)
            # This matches the actual display aspect ratio
            image_resized = image.resize((240, 280), Image.LANCZOS)
            
            # Save with same quality as video recording (75)
            image_resized.save(FRAME_OUTPUT, "JPEG", quality=75)
            
            # Log frame saves occasionally
            if frame_count % 20 == 0 or frame_count == 1:
                file_size = os.path.getsize(FRAME_OUTPUT)
                print(f"[Detection] Saved frame #{frame_count} ({file_size} bytes)", flush=True)
            
            # Update state with detections
            save_state(target_objects, True, detections)
            
            frame_count += 1
            
            # Small delay to prevent overload
            time.sleep(0.05)
        
        # Cleanup
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
        print("Usage: live_detection.py <start|stop> [objects...] [--confidence 0.3] [--duration 30]")
        print("")
        print("Examples:")
        print("  live_detection.py start person cup bottle")
        print("  live_detection.py start hand --confidence 0.5")
        print("  live_detection.py start person --duration 30")
        print("  live_detection.py stop")
        sys.exit(1)
    
    action = sys.argv[1]
    
    if action == "start":
        # Parse arguments
        objects = []
        confidence = 0.3
        duration = None
        
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--confidence" and i + 1 < len(sys.argv):
                confidence = float(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--duration" and i + 1 < len(sys.argv):
                duration = float(sys.argv[i + 1])
                i += 2
            else:
                objects.append(sys.argv[i])
                i += 1
        
        if not objects:
            print("Error: No objects specified to detect")
            sys.exit(1)
        
        success = run_live_detection(objects, confidence, duration)
        sys.exit(0 if success else 1)
    
    elif action == "stop":
        success = stop_detection()
        sys.exit(0 if success else 1)
    
    else:
        print(f"Error: Unknown action '{action}'")
        sys.exit(1)




