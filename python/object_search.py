import time
import sys
import os
import json
import cv2
import argparse
from datetime import datetime
from ultralytics import YOLO

# Configuration
MODEL_PATH = "yolov8n.pt"
IMAGE_DIR = os.path.expanduser("~/ai-pi/captures/search")
STATE_FILE = "/tmp/search_state.json"

os.makedirs(IMAGE_DIR, exist_ok=True)

def main():
    parser = argparse.ArgumentParser(description="Object Search - Find specific stuff")
    parser.add_argument("target_class", help="YOLO class name to scan for (e.g. cup)")
    parser.add_argument("--confidence", type=float, default=0.5, help="Detection confidence threshold")
    parser.add_argument("--interval", type=float, default=2.0, help="Check interval in seconds")
    
    args = parser.parse_args()
    
    print(f"Starting Object Search: Scanning for candidates of type '{args.target_class}'...", file=sys.stderr)
    
    try:
        model = YOLO(MODEL_PATH)
    except Exception as e:
        print(f"Error loading YOLO model: {e}", file=sys.stderr)
        sys.exit(1)
        
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open camera", file=sys.stderr)
        sys.exit(1)
        
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    # Create state file
    with open(STATE_FILE, "w") as f:
        json.dump({"status": "running", "pid": os.getpid()}, f)

    last_trigger_time = 0
    cooldown = 5  # seconds between candidates

    try:
        while True:
            if not os.path.exists(STATE_FILE):
                break
            
            ret, frame = cap.read()
            if not ret:
                time.sleep(1)
                continue
            
            if time.time() - last_trigger_time < cooldown:
                time.sleep(0.1)
                continue

            results = model(frame, verbose=False, conf=args.confidence)
            
            candidate_found = False
            best_box = None
            max_conf = 0
            
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    cls_name = model.names[cls_id]
                    conf = float(box.conf[0])
                    
                    if cls_name == args.target_class and conf > max_conf:
                        candidate_found = True
                        best_box = box
                        max_conf = conf
            
            if candidate_found and best_box is not None:
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                image_filename = f"candidate-{timestamp}.jpg"
                image_path = os.path.join(IMAGE_DIR, image_filename)
                
                # Draw box
                xyxy = best_box.xyxy[0].tolist()
                cv2.rectangle(frame, (int(xyxy[0]), int(xyxy[1])), (int(xyxy[2]), int(xyxy[3])), (0, 255, 255), 2)
                cv2.putText(frame, f"{args.target_class}?", (int(xyxy[0]), int(xyxy[1])-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
                
                cv2.imwrite(image_path, frame)
                
                trigger_data = {
                    "event": "candidate_found",
                    "class": args.target_class,
                    "confidence": max_conf,
                    "image_path": image_path,
                    "timestamp": timestamp
                }
                print(f"JSON_CANDIDATE:{json.dumps(trigger_data)}", flush=True)
                
                last_trigger_time = time.time()
            
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        print("Object Search stopped", file=sys.stderr)

if __name__ == "__main__":
    main()

