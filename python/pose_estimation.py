import time
import sys
import os
import json
import cv2
import argparse
import numpy as np
from datetime import datetime
from ultralytics import YOLO

# Configuration
MODEL_PATH = "yolo11n-pose.pt"  # YOLO11 - latest and most efficient
IMAGE_DIR = os.path.expanduser("~/ai-pi/captures/pose")
STATE_FILE = "/tmp/pose_state.json"

os.makedirs(IMAGE_DIR, exist_ok=True)

def analyze_pose(keypoints, action="detect"):
    """
    Analyze pose keypoints to detect specific actions or poses.
    
    Keypoint indices (COCO format):
    0: nose, 1: left_eye, 2: right_eye, 3: left_ear, 4: right_ear,
    5: left_shoulder, 6: right_shoulder, 7: left_elbow, 8: right_elbow,
    9: left_wrist, 10: right_wrist, 11: left_hip, 12: right_hip,
    13: left_knee, 14: right_knee, 15: left_ankle, 16: right_ankle
    """
    if keypoints is None or len(keypoints) < 17:
        return None
    
    # Extract key points (x, y, confidence)
    nose = keypoints[0]
    left_wrist = keypoints[9]
    right_wrist = keypoints[10]
    left_shoulder = keypoints[5]
    right_shoulder = keypoints[6]
    left_elbow = keypoints[7]
    right_elbow = keypoints[8]
    left_hip = keypoints[11]
    right_hip = keypoints[12]
    left_knee = keypoints[13]
    right_knee = keypoints[14]
    left_ankle = keypoints[15]
    right_ankle = keypoints[16]
    
    results = {}
    
    if action == "waving":
        # Check if either hand is raised above shoulder
        if left_wrist[2] > 0.3 and left_shoulder[2] > 0.3:
            if left_wrist[1] < left_shoulder[1] - 30:  # Hand above shoulder
                results["waving"] = True
                results["hand"] = "left"
        
        if right_wrist[2] > 0.3 and right_shoulder[2] > 0.3:
            if right_wrist[1] < right_shoulder[1] - 30:
                results["waving"] = True
                results["hand"] = "right"
    
    elif action == "hands_up":
        # Both hands raised above shoulders
        left_up = (left_wrist[2] > 0.3 and left_shoulder[2] > 0.3 and 
                   left_wrist[1] < left_shoulder[1] - 30)
        right_up = (right_wrist[2] > 0.3 and right_shoulder[2] > 0.3 and 
                    right_wrist[1] < right_shoulder[1] - 30)
        
        if left_up and right_up:
            results["hands_up"] = True
    
    elif action == "sitting":
        # Hips and knees detected, knees bent (y position similar)
        if (left_hip[2] > 0.3 and left_knee[2] > 0.3 and 
            abs(left_hip[1] - left_knee[1]) < 100):
            results["sitting"] = True
    
    elif action == "standing":
        # Hips above knees, knees above ankles (vertical alignment)
        if (left_hip[2] > 0.3 and left_knee[2] > 0.3 and 
            left_hip[1] < left_knee[1] - 50):
            results["standing"] = True
    
    # Exercise detection states
    elif action == "pushup":
        # Push-up: arms extended (up) vs bent (down)
        # Check if elbows, shoulders, and wrists are visible
        if (left_shoulder[2] > 0.3 and left_elbow[2] > 0.3 and left_wrist[2] > 0.3 and
            right_shoulder[2] > 0.3 and right_elbow[2] > 0.3 and right_wrist[2] > 0.3):
            
            # Calculate arm angle (shoulder-elbow-wrist)
            # If arms are straight, angle is ~180°, if bent ~90°
            left_arm_bent = abs(left_shoulder[1] - left_elbow[1]) > 50
            right_arm_bent = abs(right_shoulder[1] - right_elbow[1]) > 50
            
            if left_arm_bent and right_arm_bent:
                results["state"] = "down"
            else:
                results["state"] = "up"
    
    elif action == "squat":
        # Squat: standing (knees straight) vs crouched (knees bent)
        if (left_hip[2] > 0.3 and left_knee[2] > 0.3 and left_ankle[2] > 0.3):
            # Measure hip-to-knee distance
            hip_knee_dist = abs(left_hip[1] - left_knee[1])
            
            if hip_knee_dist < 80:  # Knees bent (squatting down)
                results["state"] = "down"
            elif hip_knee_dist > 120:  # Knees straight (standing up)
                results["state"] = "up"
    
    elif action == "pullup":
        # Pull-up: hands above head, body up vs down
        if (left_wrist[2] > 0.3 and right_wrist[2] > 0.3 and 
            left_shoulder[2] > 0.3 and nose[2] > 0.3):
            
            # Check if hands are above shoulders (gripping bar)
            hands_up = (left_wrist[1] < left_shoulder[1] - 50 and 
                       right_wrist[1] < right_shoulder[1] - 50)
            
            if hands_up:
                # Check if nose is near hands (pulled up) or far (hanging)
                nose_to_hands = abs(nose[1] - ((left_wrist[1] + right_wrist[1]) / 2))
                
                if nose_to_hands < 100:  # Chin at or above bar
                    results["state"] = "up"
                else:  # Arms extended, hanging
                    results["state"] = "down"
    
    return results if results else None

def main():
    parser = argparse.ArgumentParser(description="Pose Estimation - Detect human poses and actions")
    parser.add_argument("--action", type=str, default="detect", 
                       help="Action to detect: waving, hands_up, sitting, standing, pushup, squat, pullup, or 'detect' for all")
    parser.add_argument("--confidence", type=float, default=0.5, 
                       help="Detection confidence threshold")
    parser.add_argument("--interval", type=float, default=0.5, 
                       help="Check interval in seconds")
    parser.add_argument("--duration", type=int, default=3, 
                       help="Number of consecutive detections to trigger")
    parser.add_argument("--visualize", action="store_true", 
                       help="Draw skeleton on captured images")
    parser.add_argument("--count", action="store_true",
                       help="Count exercise repetitions (for pushup, squat, pullup)")
    parser.add_argument("--goal", type=int, default=None,
                       help="Target number of reps to reach before stopping")
    
    args = parser.parse_args()
    
    print(f"Starting Pose Estimation: Looking for '{args.action}'", file=sys.stderr)
    
    # Initialize YOLO Pose model
    try:
        model = YOLO(MODEL_PATH)
        print(f"Model loaded: {MODEL_PATH}", file=sys.stderr)
    except Exception as e:
        print(f"Error loading YOLO pose model: {e}", file=sys.stderr)
        print("Model will auto-download on first use...", file=sys.stderr)
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
    
    # For exercise counting
    is_exercise = args.action in ["pushup", "squat", "pullup"]
    rep_count = 0
    last_state = None
    state_confirmed = False
    
    # Create state file
    state_data = {
        "status": "running", 
        "pid": os.getpid(), 
        "action": args.action,
        "counting": args.count,
        "reps": 0
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state_data, f)
    
    try:
        while True:
            # Check if we should stop
            if not os.path.exists(STATE_FILE):
                break
            
            # Check if goal reached
            if args.goal and rep_count >= args.goal:
                print(f"Goal reached! {rep_count} reps completed.", file=sys.stderr)
                trigger_data = {
                    "event": "goal_reached",
                    "action": args.action,
                    "reps": rep_count,
                    "goal": args.goal
                }
                print(f"JSON_TRIGGER:{json.dumps(trigger_data)}", flush=True)
                break
            
            ret, frame = cap.read()
            if not ret:
                print("Error reading frame", file=sys.stderr)
                time.sleep(1)
                continue
            
            # Run pose detection
            results = model(frame, verbose=False, conf=args.confidence)
            
            action_detected = False
            detected_info = {}
            annotated_frame = frame.copy()
            
            for r in results:
                if r.keypoints is not None and len(r.keypoints) > 0:
                    # Process each detected person
                    for person_idx, kp in enumerate(r.keypoints):
                        # Get keypoints (x, y, confidence) - shape: (17, 3)
                        keypoints_data = kp.data[0].cpu().numpy()
                        
                        # Analyze pose for the specified action
                        if args.action != "detect":
                            analysis = analyze_pose(keypoints_data, args.action)
                            if analysis:
                                action_detected = True
                                detected_info = {
                                    "person": person_idx + 1,
                                    "action": args.action,
                                    "details": analysis
                                }
                                
                                # Exercise counting logic
                                if is_exercise and args.count and "state" in analysis:
                                    current_state = analysis["state"]
                                    
                                    # Confirm state change (avoid noise)
                                    if current_state != last_state:
                                        if not state_confirmed:
                                            state_confirmed = True
                                        else:
                                            # State changed and confirmed
                                            # Count a rep on transition from down to up
                                            if last_state == "down" and current_state == "up":
                                                rep_count += 1
                                                print(f"Rep {rep_count} completed!", file=sys.stderr)
                                                
                                                # Update state file
                                                state_data["reps"] = rep_count
                                                with open(STATE_FILE, "w") as f:
                                                    json.dump(state_data, f)
                                                
                                                # Send progress update
                                                progress_data = {
                                                    "event": "rep_counted",
                                                    "action": args.action,
                                                    "reps": rep_count,
                                                    "goal": args.goal
                                                }
                                                print(f"JSON_PROGRESS:{json.dumps(progress_data)}", flush=True)
                                            
                                            last_state = current_state
                                            state_confirmed = False
                                    else:
                                        state_confirmed = False
                        else:
                            # Detect any action
                            for action_type in ["waving", "hands_up", "sitting", "standing"]:
                                analysis = analyze_pose(keypoints_data, action_type)
                                if analysis:
                                    action_detected = True
                                    detected_info = {
                                        "person": person_idx + 1,
                                        "action": action_type,
                                        "details": analysis
                                    }
                                    break
                        
                        # Draw skeleton if requested
                        if args.visualize:
                            annotated_frame = r.plot()
                            # Add rep count overlay for exercises
                            if is_exercise and args.count:
                                cv2.putText(annotated_frame, f"Reps: {rep_count}", 
                                          (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 
                                          1.5, (0, 255, 0), 3)
            
            # For non-exercise actions, use original trigger logic
            if action_detected and not is_exercise:
                consecutive_detections += 1
                print(f"Action '{detected_info['action']}' detected! ({consecutive_detections}/{args.duration})", 
                      file=sys.stderr)
                
                if consecutive_detections >= args.duration:
                    # Trigger!
                    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    image_filename = f"pose-{args.action}-{timestamp}.jpg"
                    image_path = os.path.join(IMAGE_DIR, image_filename)
                    
                    # Save frame (with or without skeleton)
                    cv2.imwrite(image_path, annotated_frame if args.visualize else frame)
                    
                    # Output JSON trigger
                    trigger_data = {
                        "event": "pose_detected",
                        "action": detected_info['action'],
                        "details": detected_info['details'],
                        "image_path": image_path,
                        "timestamp": timestamp
                    }
                    print(f"JSON_TRIGGER:{json.dumps(trigger_data)}", flush=True)
                    
                    # Reset and cooldown
                    consecutive_detections = 0
                    time.sleep(3)
            elif not action_detected and not is_exercise:
                consecutive_detections = 0
            
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        print("Pose Estimation stopped", file=sys.stderr)

if __name__ == "__main__":
    main()

