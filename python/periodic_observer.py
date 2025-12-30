#!/usr/bin/env python3
"""
Periodic Observer - Autonomous video+audio capture and commentary system for Jarvis

Periodically captures short video clips with synchronized audio, analyzes them,
and generates contextual commentary. Updates the knowledge graph with observations.

Audio is captured ONLY during the video clip (not continuously) to avoid
blocking the microphone for button-press chat interactions.

Features:
- Configurable observation interval (default: every 10 minutes)
- 4 second video capture with synchronized audio
- Object detection via Edge TPU or YOLO
- Scene description via vision LLM (Gemini)
- Speech transcription via Whisper
- Change detection compared to previous observations
- Mission-aware: checks for mission-relevant events
- Knowledge graph integration
"""

import os
import sys
import time
import json
import argparse
import subprocess
import signal
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from io import BytesIO

# Load .env file for API keys
def load_env_file(env_path: str = "/home/dash/optidex/.env"):
    """Load environment variables from .env file"""
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key not in os.environ:  # Don't override existing
                        os.environ[key] = value

load_env_file()

# Add paths
sys.path.insert(0, '/home/dash/coral-models')
sys.path.insert(0, '/home/dash/optidex/python')

import cv2
from picamera2 import Picamera2
from PIL import Image

# Import memory system
from memory import get_memory, Episode

# Import Edge TPU if available
try:
    from edgetpu_client import EdgeTPUClient
    EDGETPU_AVAILABLE = True
except ImportError:
    EDGETPU_AVAILABLE = False

# Try to import Google GenAI for vision (new package)
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# Configuration
STATE_FILE = "/tmp/periodic_observer_state.json"
VIDEO_DIR = Path(os.path.expanduser("~/optidex/data/videos/observations"))
AUDIO_DIR = Path(os.path.expanduser("~/optidex/data/recordings/observations"))
FRAME_OUTPUT = "/tmp/periodic_observer_frame.jpg"

VIDEO_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Default settings
DEFAULT_INTERVAL_MINUTES = 10  # 10 minute observation cycle
DEFAULT_VIDEO_DURATION = 4  # seconds
DEFAULT_FPS = 15

# Audio settings
AUDIO_DEVICE = os.environ.get("AUDIO_INPUT_DEVICE", "plughw:2,0")
SAMPLE_RATE = 16000


class PeriodicObserver:
    """
    Autonomous observer that periodically captures and analyzes the environment.
    Captures both video AND audio during each observation (not continuously).
    """
    
    def __init__(
        self,
        interval_minutes: float = DEFAULT_INTERVAL_MINUTES,
        video_duration: float = DEFAULT_VIDEO_DURATION,
        fps: int = DEFAULT_FPS,
        use_vision_llm: bool = True,
        audio_device: str = AUDIO_DEVICE
    ):
        self.interval_seconds = interval_minutes * 60
        self.video_duration = video_duration
        self.fps = fps
        self.use_vision_llm = use_vision_llm
        self.audio_device = audio_device
        
        self.running = False
        self.picam2 = None
        self.detector = None
        self.genai_client = None
        self.genai_model = None
        
        # Memory system
        self.memory = get_memory()
        
        # Previous observation for change detection
        self.previous_objects: set = set()
        self.previous_description: Optional[str] = None
        
        # Statistics
        self.observation_count = 0
        self.mission_triggers = 0
        
    def setup(self):
        """Initialize camera and detection models"""
        print("[Observer] Setting up...", file=sys.stderr)
        
        # Initialize camera
        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
        self.picam2.configure(config)
        
        # Initialize detector
        if EDGETPU_AVAILABLE:
            try:
                self.detector = EdgeTPUClient(host='localhost')
                if self.detector.ping('detection'):
                    print("[Observer] Using Edge TPU for detection", file=sys.stderr)
                else:
                    self.detector = None
            except:
                self.detector = None
        
        if self.detector is None:
            print("[Observer] Using YOLO for detection", file=sys.stderr)
            try:
                from ultralytics import YOLO
                self.detector = YOLO("yolov8n.pt")
            except Exception as e:
                print(f"[Observer] Warning: No detector available: {e}", file=sys.stderr)
        
        # Initialize vision LLM (using new google.genai package)
        if self.use_vision_llm and GENAI_AVAILABLE:
            api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
            if api_key:
                self.genai_client = genai.Client(api_key=api_key)
                self.genai_model = "gemini-2.0-flash-exp"
                print("[Observer] Vision LLM ready (google.genai)", file=sys.stderr)
            else:
                print("[Observer] Warning: No Gemini API key found", file=sys.stderr)
                self.genai_client = None
        
        print("[Observer] Setup complete", file=sys.stderr)
    
    def capture_audio_clip(self, duration: float) -> Tuple[Optional[str], Optional[subprocess.Popen]]:
        """Start audio capture in background, returns (path, process)"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audio_path = AUDIO_DIR / f"obs_audio_{timestamp}.wav"
        
        try:
            cmd = [
                "arecord",
                "-D", self.audio_device,
                "-f", "S16_LE",
                "-r", str(SAMPLE_RATE),
                "-c", "1",
                "-d", str(int(duration + 1)),  # Slightly longer to ensure coverage
                "-t", "wav",
                "-q",
                str(audio_path)
            ]
            
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return str(audio_path), process
            
        except Exception as e:
            print(f"[Observer] Audio capture error: {e}", file=sys.stderr)
            return None, None
    
    def transcribe_audio(self, audio_path: str) -> Optional[str]:
        """Transcribe audio file using Whisper"""
        if not audio_path or not os.path.exists(audio_path):
            return None
            
        try:
            # Use tiny model for faster transcription on Pi (base is too slow)
            result = subprocess.run(
                [
                    "whisper", audio_path,
                    "--model", "tiny",
                    "--language", "en",
                    "--output_format", "txt",
                    "--output_dir", "/tmp"
                ],
                capture_output=True,
                text=True,
                timeout=120  # 2 minutes - Pi CPU is slow
            )
            
            # Read transcription
            txt_path = Path("/tmp") / (Path(audio_path).stem + ".txt")
            if txt_path.exists():
                text = txt_path.read_text().strip()
                txt_path.unlink()  # Clean up
                
                # Filter out empty or noise-only transcriptions
                if text and len(text) > 5 and not text.lower().startswith("["):
                    return text
            
            return None
            
        except subprocess.TimeoutExpired:
            print("[Observer] Whisper transcription timed out", file=sys.stderr)
            return None
        except FileNotFoundError:
            # Whisper CLI not installed, skip transcription
            return None
        except Exception as e:
            print(f"[Observer] Transcription error: {e}", file=sys.stderr)
            return None
    
    def capture_video_clip(self) -> Tuple[List, str, Optional[str]]:
        """Capture a short video clip with synchronized audio"""
        frames = []
        frame_count = int(self.video_duration * self.fps)
        frame_interval = 1.0 / self.fps
        
        # Start audio capture first (it takes a moment to initialize)
        audio_path, audio_process = self.capture_audio_clip(self.video_duration)
        
        self.picam2.start()
        time.sleep(0.5)  # Let camera stabilize
        
        for i in range(frame_count):
            frame_start = time.time()
            frame = self.picam2.capture_array()
            frames.append(frame)
            
            # Maintain FPS
            elapsed = time.time() - frame_start
            sleep_time = max(0, frame_interval - elapsed)
            time.sleep(sleep_time)
        
        self.picam2.stop()
        
        # Wait for audio capture to complete
        if audio_process:
            try:
                audio_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                audio_process.terminate()
                audio_path = None
        
        # Save video
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_path = VIDEO_DIR / f"obs_{timestamp}.mp4"
        
        if frames:
            height, width = frames[0].shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(str(video_path), fourcc, self.fps, (width, height))
            
            for frame in frames:
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                writer.write(frame_bgr)
            
            writer.release()
        
        return frames, str(video_path), audio_path
    
    def detect_objects(self, frame) -> List[Dict]:
        """Run object detection on a frame"""
        if self.detector is None:
            return []
        
        detections = []
        
        if isinstance(self.detector, EdgeTPUClient):
            # Edge TPU
            pil_image = Image.fromarray(frame)
            buffer = BytesIO()
            pil_image.save(buffer, format='JPEG', quality=85)
            image_bytes = buffer.getvalue()
            
            result = self.detector.detect_objects(image_bytes, threshold=0.4)
            detections = result if isinstance(result, list) else []
        else:
            # YOLO
            results = self.detector(frame, conf=0.4, verbose=False)
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
        
        return detections
    
    def get_scene_description(self, frame, detected_objects: List[str]) -> Tuple[Optional[str], List[str]]:
        """Get scene description and visible objects from vision LLM
        
        Returns:
            Tuple of (description, list of objects seen by Gemini)
        """
        if not hasattr(self, 'genai_client') or not self.genai_client:
            return None, []
        
        try:
            pil_image = Image.fromarray(frame)
            objects_str = ", ".join(detected_objects) if detected_objects else "unknown"
            
            prompt = f"""You are Jarvis, an AI assistant observing a room through a camera.
Analyze this image and respond with JSON in this exact format:
{{
  "description": "1-2 sentence description of the scene",
  "objects": ["list", "of", "visible", "objects"],
  "people_count": 0,
  "activity": "what is happening or null"
}}

Object detector found: {objects_str}
Include any additional objects you can see that the detector missed.
Keep the description factual and brief. Only respond with valid JSON."""
            
            # Save image to bytes for the new API
            img_buffer = BytesIO()
            pil_image.save(img_buffer, format='JPEG', quality=85)
            img_bytes = img_buffer.getvalue()
            
            # Use new google.genai API (keyword arguments required)
            response = self.genai_client.models.generate_content(
                model=self.genai_model,
                contents=[
                    types.Part.from_text(text=prompt),
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
                ]
            )
            
            if response and response.text:
                text = response.text.strip()
                # Try to parse JSON
                try:
                    # Handle markdown code blocks
                    if text.startswith("```"):
                        text = text.split("```")[1]
                        if text.startswith("json"):
                            text = text[4:]
                        text = text.strip()
                    
                    data = json.loads(text)
                    description = data.get("description", "")
                    objects = data.get("objects", [])
                    return description, objects
                except json.JSONDecodeError:
                    # Fall back to text response
                    return text, []
            
        except Exception as e:
            print(f"[Observer] Vision LLM error: {e}", file=sys.stderr)
        
        return None, []
    
    def detect_changes(self, current_objects: set) -> Dict[str, Any]:
        """Compare current observation to previous"""
        new_objects = current_objects - self.previous_objects
        removed_objects = self.previous_objects - current_objects
        
        return {
            "new_objects": list(new_objects),
            "removed_objects": list(removed_objects),
            "changed": bool(new_objects or removed_objects)
        }
    
    def observe(self) -> Optional[Episode]:
        """Perform a single observation cycle"""
        print(f"[Observer] Starting observation #{self.observation_count + 1}", file=sys.stderr)
        
        try:
            # Capture video and audio simultaneously
            frames, video_path, audio_path = self.capture_video_clip()
            if not frames:
                print("[Observer] No frames captured", file=sys.stderr)
                return None
            
            # Transcribe audio
            transcription = None
            if audio_path and os.path.exists(audio_path):
                transcription = self.transcribe_audio(audio_path)
                if transcription:
                    print(f"[Observer] Heard: {transcription[:100]}...", file=sys.stderr)
                else:
                    # No speech detected, clean up audio file
                    try:
                        os.remove(audio_path)
                    except:
                        pass
                    audio_path = None
            
            # Use middle frame for analysis
            middle_frame = frames[len(frames) // 2]
            
            # Save preview frame
            preview = Image.fromarray(middle_frame)
            preview.save(FRAME_OUTPUT, "JPEG", quality=85)
            
            # Detect objects with Edge TPU/YOLO
            detections = self.detect_objects(middle_frame)
            detector_objects = list(set(d['class_name'] for d in detections))
            
            # Get scene description AND additional objects from Gemini
            scene_description, gemini_objects = self.get_scene_description(middle_frame, detector_objects)
            
            # Merge objects from both sources (detector + Gemini vision)
            all_objects = list(set(detector_objects + gemini_objects))
            current_objects_set = set(all_objects)
            
            print(f"[Observer] Detector found: {detector_objects}", file=sys.stderr)
            print(f"[Observer] Gemini found: {gemini_objects}", file=sys.stderr)
            
            # Detect changes from previous observation
            changes = self.detect_changes(current_objects_set)
            
            # Check for mission matches (use merged object list)
            mission_matches = self.memory.check_mission_match(
                detected_objects=all_objects,
                transcription=transcription,
                location="observed area"
            )
            
            # Determine importance
            importance = 0.3  # Base importance
            if changes.get("changed"):
                importance += 0.2
            if mission_matches:
                importance += 0.3
                self.mission_triggers += 1
            if "person" in [o.lower() for o in all_objects]:
                importance += 0.2
            if transcription:
                importance += 0.1  # Speech detected adds importance
            importance = min(importance, 1.0)
            
            # Build summary
            summary = scene_description or f"Observed: {', '.join(all_objects[:5])}"
            if transcription:
                summary += f" | Heard: \"{transcription[:80]}...\""
            
            # Create episode with merged object list
            episode = self.memory.create_episode(
                episode_type="observation",
                summary=summary,
                video_path=video_path,
                audio_path=audio_path,
                image_path=FRAME_OUTPUT,
                detected_objects=all_objects,  # Merged list from detector + Gemini
                transcription=transcription,
                importance=importance,
                mission_id=mission_matches[0][0].id if mission_matches else None,
                scene_description=scene_description,
                changes=changes,
                detector_objects=detector_objects,  # What Edge TPU/YOLO found
                gemini_objects=gemini_objects       # What Gemini vision found
            )
            
            # Update state for next comparison
            self.previous_objects = current_objects_set
            self.previous_description = scene_description
            self.observation_count += 1
            
            # Save state
            self._save_state()
            
            print(f"[Observer] Completed observation: {episode.id}", file=sys.stderr)
            return episode
            
        except Exception as e:
            print(f"[Observer] Error during observation: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            return None
    
    def _save_state(self):
        """Save observer state to file"""
        state = {
            "observation_count": self.observation_count,
            "mission_triggers": self.mission_triggers,
            "previous_objects": list(self.previous_objects),
            "last_observation": time.time()
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    
    def _load_state(self):
        """Load observer state from file"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                self.observation_count = state.get("observation_count", 0)
                self.mission_triggers = state.get("mission_triggers", 0)
                self.previous_objects = set(state.get("previous_objects", []))
            except:
                pass
    
    def run(self):
        """Run the observer loop"""
        self.running = True
        self._load_state()
        
        print(f"[Observer] Starting observation loop (interval: {self.interval_seconds}s)", file=sys.stderr)
        
        # Do first observation immediately
        self.observe()
        
        while self.running:
            try:
                # Wait for next interval
                time.sleep(self.interval_seconds)
                
                if self.running:
                    self.observe()
                    
            except KeyboardInterrupt:
                print("[Observer] Shutting down...", file=sys.stderr)
                break
            except Exception as e:
                print(f"[Observer] Error in loop: {e}", file=sys.stderr)
                time.sleep(60)  # Wait before retrying
    
    def stop(self):
        """Stop the observer"""
        self.running = False
        if self.picam2:
            try:
                self.picam2.stop()
            except:
                pass
    
    def cleanup(self):
        """Clean up resources"""
        self.stop()
        if self.picam2:
            try:
                self.picam2.close()
            except:
                pass


# Global instance for signal handling
_observer_instance: Optional[PeriodicObserver] = None


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global _observer_instance
    if _observer_instance:
        print("[Observer] Received shutdown signal", file=sys.stderr)
        _observer_instance.stop()


def main():
    global _observer_instance
    
    parser = argparse.ArgumentParser(description="Jarvis Periodic Observer")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_MINUTES,
                       help="Observation interval in minutes (default: 10)")
    parser.add_argument("--duration", type=float, default=DEFAULT_VIDEO_DURATION,
                       help="Video duration in seconds (default: 4)")
    parser.add_argument("--device", type=str, default=AUDIO_DEVICE,
                       help="Audio input device (default: plughw:2,0)")
    parser.add_argument("--once", action="store_true",
                       help="Run single observation and exit")
    parser.add_argument("--no-audio", action="store_true",
                       help="Disable audio capture")
    
    args = parser.parse_args()
    
    observer = PeriodicObserver(
        interval_minutes=args.interval,
        video_duration=args.duration,
        audio_device=args.device
    )
    
    _observer_instance = observer
    
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        observer.setup()
        
        if args.once:
            episode = observer.observe()
            if episode:
                print(f"Episode created: {episode.id}")
                print(f"Summary: {episode.summary}")
        else:
            observer.run()
            
    finally:
        observer.cleanup()


if __name__ == "__main__":
    main()

