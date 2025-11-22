#!/usr/bin/env python3
"""
Smart Observer script for Whisplay
Detects specific objects, saves a trigger image, and signals the main application.
Based on live_detection.py but focused on "Trigger" events.
"""
import sys
import os
import time
import json
import numpy as np
from picamera2 import Picamera2
from PIL import Image

# Trigger output files
TRIGGER_FILE = "/tmp/whisplay_trigger_event.json"
TRIGGER_IMAGE = "/tmp/whisplay_trigger_image.jpg"

def run_observer(target_objects, confidence_threshold=0.5, stability_frames=5):
    """
    Run detection loop. 
    If target object is found consistently for 'stability_frames', 
    save image and trigger event.
    """
    try:
        # Import YOLO (ultralytics)
        try:
            from ultralytics import YOLO
        except ImportError:
            print("Error: ultralytics not installed.", file=sys.stderr)
            return False
        
        # Use YOLO-World for open-vocabulary detection
        yolo_model = os.environ.get('YOLO_MODEL', 'yolov8s-world.pt')
        print(f"Loading model: {yolo_model}...")
        model = YOLO(yolo_model)
        
        # Set custom classes
        print(f"Setting detection classes: {', '.join(target_objects)}")
        model.set_classes(target_objects)
        
        print(f"Starting camera...")
        picam2 = Picamera2()
        
        # Config for good quality still capture
        config = picam2.create_video_configuration(
            main={"size": (1280, 720)}, # Higher res for VLM
            controls={
                "FrameRate": 10, 
                "AeEnable": True,
                "AwbEnable": True,
            }
        )
        picam2.configure(config)
        picam2.start()
        
        # Warmup
        time.sleep(2.0)
        print(f"Observer active. Watching for: {', '.join(target_objects)}")
        
        consecutive_detections = 0
        target_objects_lower = [obj.lower() for obj in target_objects]
        
        while True:
            # Capture frame
            frame = picam2.capture_array("main")
            image = Image.fromarray(frame)
            
            # Run YOLO
            results = model(image, conf=confidence_threshold, verbose=False)
            
            found_objects = []
            for result in results:
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    cls_name = result.names[cls_id]
                    if cls_name.lower() in target_objects_lower:
                        found_objects.append(cls_name)
            
            if found_objects:
                consecutive_detections += 1
                print(f"Object detected ({consecutive_detections}/{stability_frames}): {', '.join(found_objects)}", flush=True)
                
                if consecutive_detections >= stability_frames:
                    print("Stability threshold reached! Triggering event...", flush=True)
                    
                    # Save high quality image
                    if image.mode == 'RGBA':
                        image = image.convert('RGB')
                    image.save(TRIGGER_IMAGE, "JPEG", quality=90)
                    
                    # Write trigger file
                    event_data = {
                        "event": "object_detected",
                        "objects": list(set(found_objects)),
                        "image_path": TRIGGER_IMAGE,
                        "timestamp": time.time()
                    }
                    with open(TRIGGER_FILE, "w") as f:
                        json.dump(event_data, f)
                    
                    # Print JSON to stdout for Node.js to parse if watching stdout
                    print(f"JSON_TRIGGER:{json.dumps(event_data)}", flush=True)
                    
                    # Exit after trigger (Single shot mode for now)
                    break
            else:
                consecutive_detections = 0
                
            # Scan rate
            time.sleep(0.2)
            
        picam2.stop()
        picam2.close()
        return True
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: smart_observer.py [objects...]")
        sys.exit(1)
        
    objects = sys.argv[1:]
    run_observer(objects)





