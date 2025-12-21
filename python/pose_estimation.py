import time
import sys
import os
import json
import cv2
import argparse
import numpy as np
from datetime import datetime
from picamera2 import Picamera2
from PIL import Image, ImageDraw

# Configuration
MODEL_PATH = "yolo11n-pose.pt"  # YOLO11 fallback
IMAGE_DIR = os.path.expanduser("~/ai-pi/captures/pose")
STATE_FILE = "/tmp/pose_state.json"
POSE_FRAME_OUTPUT = "/tmp/whisplay_pose_frame.jpg"  # For display streaming

os.makedirs(IMAGE_DIR, exist_ok=True)

# Try to import EdgeTPU client for hardware acceleration
EDGETPU_AVAILABLE = False
edgetpu_client = None

try:
    sys.path.insert(0, '/home/dash/coral-models')
    from edgetpu_client import EdgeTPUClient
    
    # Test connection to EdgeTPU server
    test_client = EdgeTPUClient()
    if test_client.ping('pose'):
        edgetpu_client = test_client
        EDGETPU_AVAILABLE = True
        print("[EdgeTPU] MoveNet available - using hardware acceleration (~12ms/frame)", file=sys.stderr)
    else:
        print("[EdgeTPU] Server not responding, falling back to YOLO", file=sys.stderr)
except ImportError as e:
    print(f"[EdgeTPU] Client not available: {e}", file=sys.stderr)
except Exception as e:
    print(f"[EdgeTPU] Connection failed: {e}, falling back to YOLO", file=sys.stderr)

# Skeleton connections for drawing
SKELETON_CONNECTIONS = [
    (0, 1), (0, 2),  # nose to eyes
    (1, 3), (2, 4),  # eyes to ears
    (5, 6),  # shoulders
    (5, 7), (7, 9),  # left arm
    (6, 8), (8, 10),  # right arm
    (5, 11), (6, 12),  # torso
    (11, 12),  # hips
    (11, 13), (13, 15),  # left leg
    (12, 14), (14, 16),  # right leg
]

KEYPOINT_COLORS = [
    (255, 0, 0),    # nose - red
    (255, 128, 0),  # left_eye
    (255, 128, 0),  # right_eye
    (255, 255, 0),  # left_ear
    (255, 255, 0),  # right_ear
    (0, 255, 0),    # left_shoulder - green
    (0, 255, 0),    # right_shoulder
    (0, 255, 128),  # left_elbow
    (0, 255, 128),  # right_elbow
    (0, 255, 255),  # left_wrist - cyan
    (0, 255, 255),  # right_wrist
    (0, 128, 255),  # left_hip - blue
    (0, 128, 255),  # right_hip
    (0, 0, 255),    # left_knee
    (0, 0, 255),    # right_knee
    (128, 0, 255),  # left_ankle - purple
    (128, 0, 255),  # right_ankle
]


def draw_skeleton_pil(image, keypoints, threshold=0.3):
    """Draw skeleton on PIL image using EdgeTPU keypoints format."""
    draw = ImageDraw.Draw(image)
    width, height = image.size
    
    # Draw connections first (behind points)
    for start_idx, end_idx in SKELETON_CONNECTIONS:
        start_kp = keypoints[start_idx]
        end_kp = keypoints[end_idx]
        
        if start_kp['confidence'] > threshold and end_kp['confidence'] > threshold:
            # Scale coordinates to image size
            x1 = int(start_kp['x'] * width / keypoints[0].get('orig_width', width))
            y1 = int(start_kp['y'] * height / keypoints[0].get('orig_height', height))
            x2 = int(end_kp['x'] * width / keypoints[0].get('orig_width', width))
            y2 = int(end_kp['y'] * height / keypoints[0].get('orig_height', height))
            
            draw.line([(x1, y1), (x2, y2)], fill=(0, 255, 0), width=3)
    
    # Draw keypoints
    for i, kp in enumerate(keypoints):
        if kp['confidence'] > threshold:
            x = int(kp['x'] * width / kp.get('orig_width', width))
            y = int(kp['y'] * height / kp.get('orig_height', height))
            
            color = KEYPOINT_COLORS[i] if i < len(KEYPOINT_COLORS) else (255, 255, 255)
            radius = 5
            draw.ellipse([x-radius, y-radius, x+radius, y+radius], fill=color, outline=color)
    
    return image


def draw_skeleton_cv2(frame, keypoints, threshold=0.3):
    """Draw skeleton on OpenCV frame using EdgeTPU keypoints format."""
    height, width = frame.shape[:2]
    
    # Get original dimensions from first keypoint if available
    orig_width = keypoints[0].get('orig_width', width) if keypoints else width
    orig_height = keypoints[0].get('orig_height', height) if keypoints else height
    
    # Draw connections first
    for start_idx, end_idx in SKELETON_CONNECTIONS:
        start_kp = keypoints[start_idx]
        end_kp = keypoints[end_idx]
        
        if start_kp['confidence'] > threshold and end_kp['confidence'] > threshold:
            x1 = int(start_kp['x'] * width / orig_width)
            y1 = int(start_kp['y'] * height / orig_height)
            x2 = int(end_kp['x'] * width / orig_width)
            y2 = int(end_kp['y'] * height / orig_height)
            
            cv2.line(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    
    # Draw keypoints
    for i, kp in enumerate(keypoints):
        if kp['confidence'] > threshold:
            x = int(kp['x'] * width / orig_width)
            y = int(kp['y'] * height / orig_height)
            
            color = KEYPOINT_COLORS[i] if i < len(KEYPOINT_COLORS) else (255, 255, 255)
            # Convert RGB to BGR for OpenCV
            color_bgr = (color[2], color[1], color[0])
            cv2.circle(frame, (x, y), 5, color_bgr, -1)
    
    return frame


def edgetpu_keypoints_to_array(keypoints_dict, image_size):
    """Convert EdgeTPU keypoints dict to numpy array format for analyze_pose."""
    # EdgeTPU returns: [{'name': 'nose', 'x': int, 'y': int, 'confidence': float}, ...]
    # We need: [[x, y, conf], ...] in COCO order (17 keypoints)
    
    width, height = image_size
    keypoints_array = []
    
    # COCO keypoint order
    keypoint_names = [
        'nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
        'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
        'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
        'left_knee', 'right_knee', 'left_ankle', 'right_ankle'
    ]
    
    # Create dict for quick lookup
    kp_lookup = {kp['name']: kp for kp in keypoints_dict}
    
    for name in keypoint_names:
        if name in kp_lookup:
            kp = kp_lookup[name]
            keypoints_array.append([kp['x'], kp['y'], kp['confidence']])
        else:
            keypoints_array.append([0, 0, 0])
    
    return np.array(keypoints_array)


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
        left_visible = left_shoulder[2] > 0.3 and left_elbow[2] > 0.3
        right_visible = right_shoulder[2] > 0.3 and right_elbow[2] > 0.3
        
        if left_visible or right_visible:
            left_arm_bent = abs(left_shoulder[1] - left_elbow[1]) > 50 if left_visible else False
            right_arm_bent = abs(right_shoulder[1] - right_elbow[1]) > 50 if right_visible else False
            
            if left_visible and right_visible:
                if left_arm_bent or right_arm_bent:
                    results["state"] = "down"
                else:
                    results["state"] = "up"
            elif left_visible:
                results["state"] = "down" if left_arm_bent else "up"
            else:
                results["state"] = "down" if right_arm_bent else "up"
    
    elif action == "squat":
        if (left_hip[2] > 0.3 and left_knee[2] > 0.3 and left_ankle[2] > 0.3):
            hip_knee_dist = abs(left_hip[1] - left_knee[1])
            
            if hip_knee_dist < 80:
                results["state"] = "down"
            elif hip_knee_dist > 120:
                results["state"] = "up"
    
    elif action == "pullup":
        if (left_wrist[2] > 0.3 and right_wrist[2] > 0.3 and 
            left_shoulder[2] > 0.3 and nose[2] > 0.3):
            
            hands_up = (left_wrist[1] < left_shoulder[1] - 50 and 
                       right_wrist[1] < right_shoulder[1] - 50)
            
            if hands_up:
                nose_to_hands = abs(nose[1] - ((left_wrist[1] + right_wrist[1]) / 2))
                
                if nose_to_hands < 100:
                    results["state"] = "up"
                else:
                    results["state"] = "down"
    
    elif action == "crunch":
        # Crunch: Person lying on back, curling shoulders toward hips/knees
        # Down: Body flat (large distance between shoulders and hips)
        # Up: Shoulders lifted/curled (smaller distance between shoulders and hips)
        
        # Need at least shoulders and hips visible
        left_shoulder_visible = left_shoulder[2] > 0.3
        right_shoulder_visible = right_shoulder[2] > 0.3
        left_hip_visible = left_hip[2] > 0.3
        right_hip_visible = right_hip[2] > 0.3
        
        if (left_shoulder_visible or right_shoulder_visible) and (left_hip_visible or right_hip_visible):
            # Calculate average shoulder and hip positions
            if left_shoulder_visible and right_shoulder_visible:
                shoulder_y = (left_shoulder[1] + right_shoulder[1]) / 2
            elif left_shoulder_visible:
                shoulder_y = left_shoulder[1]
            else:
                shoulder_y = right_shoulder[1]
            
            if left_hip_visible and right_hip_visible:
                hip_y = (left_hip[1] + right_hip[1]) / 2
            elif left_hip_visible:
                hip_y = left_hip[1]
            else:
                hip_y = right_hip[1]
            
            # Distance between shoulders and hips (vertical component)
            shoulder_hip_dist = abs(shoulder_y - hip_y)
            
            # Also check nose-to-hip distance for better accuracy
            nose_visible = nose[2] > 0.3
            if nose_visible:
                nose_hip_dist = abs(nose[1] - hip_y)
                # Use combined metric: when crunching, both distances decrease
                combined_dist = (shoulder_hip_dist + nose_hip_dist) / 2
                
                if combined_dist < 120:  # Curled up
                    results["state"] = "up"
                elif combined_dist > 180:  # Lying flat
                    results["state"] = "down"
            else:
                # Fallback to just shoulder-hip distance
                if shoulder_hip_dist < 100:  # Curled up
                    results["state"] = "up"
                elif shoulder_hip_dist > 150:  # Lying flat
                    results["state"] = "down"
    
    return results if results else None


def main():
    parser = argparse.ArgumentParser(description="Pose Estimation - Detect human poses and actions")
    parser.add_argument("--action", type=str, default="detect", 
                       help="Action to detect: waving, hands_up, sitting, standing, pushup, squat, pullup, crunch, or 'detect' for all")
    parser.add_argument("--confidence", type=float, default=0.5, 
                       help="Detection confidence threshold")
    parser.add_argument("--interval", type=float, default=0.05,  # Faster for smoother display
                       help="Check interval in seconds")
    parser.add_argument("--duration", type=int, default=3, 
                       help="Number of consecutive detections to trigger")
    parser.add_argument("--visualize", action="store_true", 
                       help="Draw skeleton on captured images")
    parser.add_argument("--count", action="store_true",
                       help="Count exercise repetitions (for pushup, squat, pullup)")
    parser.add_argument("--goal", type=int, default=None,
                       help="Target number of reps to reach before stopping")
    parser.add_argument("--force-yolo", action="store_true",
                       help="Force YOLO even if EdgeTPU is available")
    parser.add_argument("--record", action="store_true",
                       help="Record video with pose overlay during exercise")
    parser.add_argument("--record-path", type=str, default=None,
                       help="Path to save recorded video (default: auto-generated)")
    
    args = parser.parse_args()
    
    # Decide which backend to use
    use_edgetpu = EDGETPU_AVAILABLE and not args.force_yolo
    
    print(f"Starting Pose Estimation: Looking for '{args.action}'", file=sys.stderr)
    print(f"Backend: {'EdgeTPU MoveNet (~82 FPS)' if use_edgetpu else 'YOLO11 (CPU)'}", file=sys.stderr)
    
    # Initialize YOLO only if needed
    model = None
    if not use_edgetpu:
        try:
            from ultralytics import YOLO
            model = YOLO(MODEL_PATH)
            print(f"YOLO Model loaded: {MODEL_PATH}", file=sys.stderr)
        except Exception as e:
            print(f"Error loading YOLO pose model: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Initialize Camera
    picam2 = Picamera2()
    # Use 640x480 for faster processing, especially with EdgeTPU
    config = picam2.create_preview_configuration(main={"size": (640, 480), "format": "RGB888"})
    picam2.configure(config)
    picam2.start()
    print("Camera started with picamera2", file=sys.stderr)
    time.sleep(1)
    
    consecutive_detections = 0
    is_exercise = args.action in ["pushup", "squat", "pullup", "crunch"]
    rep_count = 0
    last_state = None
    frame_count = 0
    fps_start = time.time()
    
    # Video recording setup
    video_writer = None
    video_path = None
    if args.record:
        if args.record_path:
            video_path = args.record_path
        else:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            video_path = os.path.join(IMAGE_DIR, f"exercise-{args.action}-{timestamp}.mp4")
        
        # Use mp4v codec for MP4
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(video_path, fourcc, 15.0, (640, 480))
        print(f"Recording video to: {video_path}", file=sys.stderr)
    
    # Create state file
    state_data = {
        "status": "running", 
        "pid": os.getpid(), 
        "action": args.action,
        "counting": args.count,
        "reps": 0,
        "backend": "edgetpu" if use_edgetpu else "yolo",
        "recording": args.record,
        "video_path": video_path
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state_data, f)
    
    try:
        while True:
            if not os.path.exists(STATE_FILE):
                break
            
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
            
            # Capture frame
            frame = picam2.capture_array()  # RGB format
            frame_count += 1
            
            # Calculate FPS every 30 frames
            if frame_count % 30 == 0:
                elapsed = time.time() - fps_start
                fps = 30 / elapsed
                print(f"[PERF] FPS: {fps:.1f}", file=sys.stderr)
                fps_start = time.time()
            
            action_detected = False
            detected_info = {}
            keypoints_data = None
            keypoints_list = None  # For EdgeTPU format
            annotated_frame = frame.copy()
            
            if use_edgetpu:
                # --- EdgeTPU MoveNet Path ---
                try:
                    # Convert frame to JPEG for EdgeTPU
                    pil_frame = Image.fromarray(frame)
                    
                    result = edgetpu_client.estimate_pose(pil_frame, threshold=args.confidence)
                    
                    if result.get('success') and result.get('visible_count', 0) > 5:
                        keypoints_list = result['keypoints']
                        
                        # Store original image dimensions in keypoints for scaling
                        for kp in keypoints_list:
                            kp['orig_width'] = result['image_size'][0]
                            kp['orig_height'] = result['image_size'][1]
                        
                        # Convert to array format for analyze_pose
                        keypoints_data = edgetpu_keypoints_to_array(keypoints_list, (frame.shape[1], frame.shape[0]))
                        
                        # Analyze pose
                        if args.action != "detect":
                            analysis = analyze_pose(keypoints_data, args.action)
                            if analysis:
                                action_detected = True
                                detected_info = {
                                    "person": 1,
                                    "action": args.action,
                                    "details": analysis
                                }
                        else:
                            for action_type in ["waving", "hands_up", "sitting", "standing"]:
                                analysis = analyze_pose(keypoints_data, action_type)
                                if analysis:
                                    action_detected = True
                                    detected_info = {
                                        "person": 1,
                                        "action": action_type,
                                        "details": analysis
                                    }
                                    break
                        
                        # Draw skeleton if visualizing
                        if args.visualize and keypoints_list:
                            annotated_frame = draw_skeleton_cv2(annotated_frame, keypoints_list, args.confidence)
                            
                except Exception as e:
                    print(f"[EdgeTPU] Inference error: {e}", file=sys.stderr)
            
            else:
                # --- YOLO Fallback Path ---
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                results = model(frame_bgr, verbose=False, conf=args.confidence)
                
                for r in results:
                    if r.keypoints is not None and len(r.keypoints) > 0:
                        for person_idx, kp in enumerate(r.keypoints):
                            keypoints_data = kp.data[0].cpu().numpy()
                            
                            if args.action != "detect":
                                analysis = analyze_pose(keypoints_data, args.action)
                                if analysis:
                                    action_detected = True
                                    detected_info = {
                                        "person": person_idx + 1,
                                        "action": args.action,
                                        "details": analysis
                                    }
                            else:
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
                            
                            if args.visualize:
                                annotated_frame = cv2.cvtColor(r.plot(), cv2.COLOR_BGR2RGB)
            
            # Exercise counting logic
            if action_detected and is_exercise and args.count and detected_info.get('details', {}).get('state'):
                current_state = detected_info['details']['state']
                
                if frame_count % 10 == 0:
                    print(f"[DEBUG] State: {current_state}, Last: {last_state}", file=sys.stderr)
                
                if current_state != last_state:
                    if current_state == "down" and last_state is not None:
                        print(f"JSON_AUDIO:down", flush=True)
                
                if last_state == "down" and current_state == "up":
                    rep_count += 1
                    print(f"Rep {rep_count} completed!", file=sys.stderr)
                    
                    state_data["reps"] = rep_count
                    with open(STATE_FILE, "w") as f:
                        json.dump(state_data, f)
                    
                    progress_data = {
                        "event": "rep_counted",
                        "action": args.action,
                        "reps": rep_count,
                        "goal": args.goal
                    }
                    print(f"JSON_PROGRESS:{json.dumps(progress_data)}", flush=True)
                
                last_state = current_state
            
            # Add rep count overlay
            if args.visualize and is_exercise and args.count:
                cv2.putText(annotated_frame, f"Reps: {rep_count}", 
                          (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 
                          1.5, (0, 255, 0), 3)
                
                # Add exercise name
                cv2.putText(annotated_frame, args.action.upper(), 
                          (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 
                          0.8, (255, 255, 0), 2)
                
                # Add goal if set
                if args.goal:
                    cv2.putText(annotated_frame, f"Goal: {args.goal}", 
                              (50, 130), cv2.FONT_HERSHEY_SIMPLEX, 
                              0.6, (200, 200, 200), 2)
            
            # Write frame to video if recording
            if video_writer is not None:
                # Convert RGB to BGR for OpenCV video writer
                frame_bgr = cv2.cvtColor(annotated_frame, cv2.COLOR_RGB2BGR)
                video_writer.write(frame_bgr)
            
            # Save frame for display streaming
            if args.visualize:
                try:
                    pil_image = Image.fromarray(annotated_frame)
                    pil_image_resized = pil_image.resize((240, 280), Image.LANCZOS)
                    pil_image_resized.save(POSE_FRAME_OUTPUT, "JPEG", quality=80)
                except Exception as e:
                    if frame_count < 5:
                        print(f"[WARN] Failed to save pose frame: {e}", file=sys.stderr)
            
            # Non-exercise action trigger logic
            if action_detected and not is_exercise:
                consecutive_detections += 1
                print(f"Action '{detected_info['action']}' detected! ({consecutive_detections}/{args.duration})", 
                      file=sys.stderr)
                
                if consecutive_detections >= args.duration:
                    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    image_filename = f"pose-{args.action}-{timestamp}.jpg"
                    image_path = os.path.join(IMAGE_DIR, image_filename)
                    
                    if args.visualize:
                        cv2.imwrite(image_path, cv2.cvtColor(annotated_frame, cv2.COLOR_RGB2BGR))
                    else:
                        cv2.imwrite(image_path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
                    
                    trigger_data = {
                        "event": "pose_detected",
                        "action": detected_info['action'],
                        "details": detected_info['details'],
                        "image_path": image_path,
                        "timestamp": timestamp
                    }
                    print(f"JSON_TRIGGER:{json.dumps(trigger_data)}", flush=True)
                    
                    consecutive_detections = 0
                    time.sleep(3)
            elif not action_detected and not is_exercise:
                consecutive_detections = 0
            
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        print("Interrupted by user", file=sys.stderr)
    except Exception as e:
        print(f"Error in pose estimation: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
    finally:
        print("Releasing camera...", file=sys.stderr)
        
        # Release video writer if recording
        if video_writer is not None:
            video_writer.release()
            print(f"Video saved to: {video_path}", file=sys.stderr)
            # Output video path for the caller
            if video_path and os.path.exists(video_path):
                video_data = {
                    "event": "video_saved",
                    "video_path": video_path,
                    "reps": rep_count,
                    "action": args.action
                }
                print(f"JSON_VIDEO:{json.dumps(video_data)}", flush=True)
        
        try:
            picam2.stop()
            picam2.close()
            print("Camera released successfully", file=sys.stderr)
        except Exception as e:
            print(f"Error releasing camera: {e}", file=sys.stderr)
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        if os.path.exists(POSE_FRAME_OUTPUT):
            os.remove(POSE_FRAME_OUTPUT)
        print("Pose Estimation stopped", file=sys.stderr)


if __name__ == "__main__":
    main()
