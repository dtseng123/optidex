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
IMAGE_DIR = os.path.expanduser("~/ai-pi/captures/sentry")
STATE_FILE = "/tmp/sentry_state.json"

os.makedirs(IMAGE_DIR, exist_ok=True)

def check_interaction(box1, box2, threshold=0.1):
    """
    Check if two bounding boxes interact (overlap).
    box: [x1, y1, x2, y2]
    Returns True if overlap area / smaller box area > threshold
    """
    x1_min, y1_min, x1_max, y1_max = box1
    x2_min, y2_min, x2_max, y2_max = box2

    # Calculate intersection rectangle
    inter_x_min = max(x1_min, x2_min)
    inter_y_min = max(y1_min, y2_min)
    inter_x_max = min(x1_max, x2_max)
    inter_y_max = min(y1_max, y2_max)

    if inter_x_max <= inter_x_min or inter_y_max <= inter_y_min:
        return False  # No overlap

    inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
    
    area1 = (x1_max - x1_min) * (y1_max - y1_min)
    area2 = (x2_max - x2_min) * (y2_max - y2_min)
    
    min_area = min(area1, area2)
    
    if min_area == 0: return False
    
    overlap_ratio = inter_area / min_area
    return overlap_ratio > threshold

def main():
    parser = argparse.ArgumentParser(description="Semantic Sentry - Detect object interactions")
    parser.add_argument("pairs", nargs='+', help="Objects to check. Use --all-combinations to check all pairs, or provide explicit pairs like: obj1,obj2 obj3,obj4")
    parser.add_argument("--threshold", type=float, default=0.1, help="Overlap threshold (0-1)")
    parser.add_argument("--confidence", type=float, default=0.5, help="Detection confidence threshold")
    parser.add_argument("--interval", type=float, default=1.0, help="Check interval in seconds")
    parser.add_argument("--duration", type=int, default=3, help="Number of consecutive detections to trigger")
    parser.add_argument("--all-combinations", action="store_true", help="Check all pairwise combinations of provided objects")
    
    args = parser.parse_args()
    
    # Parse pairs
    target_pairs = []
    needed_classes = set()
    
    if args.all_combinations:
        # Treat all arguments as individual objects and create all pairwise combinations
        objects = args.pairs
        needed_classes = set(objects)
        
        # Generate all pairwise combinations (including with itself for multiple instances)
        for i, obj1 in enumerate(objects):
            for j, obj2 in enumerate(objects):
                if i < j:  # Avoid duplicate pairs and self-pairs unless same class
                    target_pairs.append((obj1, obj2))
                elif i == j and objects.count(obj1) == 1:
                    # If same object appears once, skip self-pair
                    continue
        
        if not target_pairs:
            print("Not enough objects for combinations. Provide at least 2 objects with --all-combinations", file=sys.stderr)
            sys.exit(1)
    else:
        # Original behavior: parse explicit pairs
        for p in args.pairs:
            if ',' in p:
                o1, o2 = p.split(',')
                target_pairs.append((o1, o2))
                needed_classes.add(o1)
                needed_classes.add(o2)
            else:
                print(f"Invalid pair format: {p}. Use obj1,obj2 or use --all-combinations flag", file=sys.stderr)
        
        if not target_pairs:
            print("No valid pairs provided", file=sys.stderr)
            sys.exit(1)
        
    print(f"Starting Semantic Sentry: Watching {len(target_pairs)} pairs: {target_pairs}", file=sys.stderr)
    
    # Initialize YOLO
    try:
        model = YOLO(MODEL_PATH)
    except Exception as e:
        print(f"Error loading YOLO model: {e}", file=sys.stderr)
        sys.exit(1)
        
    # Initialize Camera
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open camera", file=sys.stderr)
        sys.exit(1)
        
    # Set resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    consecutive_detections = 0
    
    # Create state file to indicate running
    with open(STATE_FILE, "w") as f:
        json.dump({"status": "running", "pid": os.getpid()}, f)

    try:
        while True:
            # Check if we should stop (external signal)
            if not os.path.exists(STATE_FILE):
                break
            
            ret, frame = cap.read()
            if not ret:
                print("Error reading frame", file=sys.stderr)
                time.sleep(1)
                continue
            
            # Run inference
            results = model(frame, verbose=False, conf=args.confidence)
            
            # Collect boxes for all interesting classes
            detected_objects = {cls: [] for cls in needed_classes}
            
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    cls_name = model.names[cls_id]
                    xyxy = box.xyxy[0].tolist()
                    
                    if cls_name in needed_classes:
                        detected_objects[cls_name].append(xyxy)
            
            interaction_found = None
            
            # Check each target pair
            for (obj1, obj2) in target_pairs:
                # Check interactions between obj1 list and obj2 list
                # Handle case where obj1 == obj2 (e.g. person interacting with person)
                # If same class, ensure we don't compare box to itself
                
                list1 = detected_objects[obj1]
                list2 = detected_objects[obj2]
                
                for i, b1 in enumerate(list1):
                    for j, b2 in enumerate(list2):
                        # If same list, skip self-compare and duplicate compares
                        if obj1 == obj2 and j <= i: continue
                        
                        if check_interaction(b1, b2, args.threshold):
                            interaction_found = (obj1, obj2, b1, b2)
                            break
                    if interaction_found: break
                if interaction_found: break
            
            if interaction_found:
                consecutive_detections += 1
                obj1_name, obj2_name, b1, b2 = interaction_found
                print(f"Interaction detected ({obj1_name}+{obj2_name})! ({consecutive_detections}/{args.duration})", file=sys.stderr)
                
                if consecutive_detections >= args.duration:
                    # Trigger!
                    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    image_filename = f"sentry-{timestamp}.jpg"
                    image_path = os.path.join(IMAGE_DIR, image_filename)
                    
                    # Draw boxes on frame for the interacting pair
                    cv2.rectangle(frame, (int(b1[0]), int(b1[1])), (int(b1[2]), int(b1[3])), (0, 255, 0), 2)
                    cv2.putText(frame, obj1_name, (int(b1[0]), int(b1[1])-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
                    
                    cv2.rectangle(frame, (int(b2[0]), int(b2[1])), (int(b2[2]), int(b2[3])), (0, 0, 255), 2)
                    cv2.putText(frame, obj2_name, (int(b2[0]), int(b2[1])-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                        
                    cv2.imwrite(image_path, frame)
                    
                    # Output JSON trigger
                    trigger_data = {
                        "event": "interaction_detected",
                        "object1": obj1_name,
                        "object2": obj2_name,
                        "image_path": image_path,
                        "timestamp": timestamp
                    }
                    print(f"JSON_TRIGGER:{json.dumps(trigger_data)}", flush=True)
                    
                    # Reset to avoid continuous triggering
                    consecutive_detections = 0
                    time.sleep(5) # Cooldown
            else:
                consecutive_detections = 0
            
            time.sleep(args.interval)
            
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        print("Semantic Sentry stopped", file=sys.stderr)

if __name__ == "__main__":
    main()
