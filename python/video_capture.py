#!/usr/bin/env python3
"""
Video capture script using picamera2 with live preview
"""
import sys
import os
import time
import signal
import json
import socket
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput
from PIL import Image
import io
import threading

class VideoRecorder:
    def __init__(self, output_path, duration=None, width=1280, height=720, framerate=30, show_preview=True):
        """
        Initialize video recorder
        
        Args:
            output_path: Path where to save the video (should end in .h264 or .mp4)
            duration: Recording duration in seconds (None for continuous)
            width: Video width (default: 1280)
            height: Video height (default: 720)
            framerate: Frames per second (default: 30)
            show_preview: Show live preview on display (default: True)
        """
        self.output_path = output_path
        self.duration = duration
        self.width = width
        self.height = height
        self.framerate = framerate
        self.show_preview = show_preview
        self.picam2 = None
        self.is_recording = False
        self.preview_thread = None
        self.stop_preview = False
        
        # Preview frame paths (rotate between multiple files to force display update)
        self.preview_base = "/tmp/whisplay_video_preview"
        self.preview_frame_num = 0
        
    def preview_loop(self):
        """Capture preview frames to temp file for display"""
        frame_interval = 0.15  # Update display ~6-7 times per second
        frame_count = 0
        
        # Use a SINGLE file path - just like video playback does!
        # This avoids symlink issues and ensures Python display reloads properly
        preview_path = f"{self.preview_base}_latest.jpg"
        
        print(f"[Preview] Starting preview loop...", flush=True)
        print(f"[Preview] Writing frames to: {preview_path}", flush=True)
        
        while self.is_recording and not self.stop_preview:
            try:
                if self.picam2:
                    # Capture a frame for preview
                    frame = self.picam2.capture_array("main")
                    
                    # Convert to PIL Image
                    img = Image.fromarray(frame)
                    
                    # Convert RGBA to RGB if needed (JPEG doesn't support alpha)
                    if img.mode == 'RGBA':
                        img = img.convert('RGB')
                    
                    # Save DIRECTLY to the same file every time (like video playback)
                    # No rotation, no symlinks - just overwrite the same file
                    img.save(preview_path, "JPEG", quality=75)
                    frame_count += 1
                    
                    # Log first few frames and then periodically
                    if frame_count <= 3 or frame_count % 20 == 0:
                        file_size = os.path.getsize(preview_path)
                        print(f"[Preview] Frame #{frame_count} saved ({file_size} bytes)", flush=True)
                        
                time.sleep(frame_interval)
            except Exception as e:
                print(f"[Preview] Error: {e}", file=sys.stderr, flush=True)
                time.sleep(frame_interval)
        
        print(f"[Preview] Preview loop ended (total frames: {frame_count})", flush=True)
    
    def start_recording(self):
        """Start video recording with live preview"""
        try:
            # Initialize camera
            self.picam2 = Picamera2()
            
            # Configure for video recording with preview capability
            video_config = self.picam2.create_video_configuration(
                main={"size": (self.width, self.height)},
                lores={"size": (640, 480)},  # Lower res for preview
                controls={"FrameRate": self.framerate}
            )
            
            self.picam2.configure(video_config)
            
            # Create encoder
            encoder = H264Encoder()
            
            # Start recording
            self.picam2.start_recording(encoder, self.output_path)
            self.is_recording = True
            
            print(f"[Recording] Recording started: {self.output_path}", flush=True)
            
            # Start preview thread if enabled
            if self.show_preview:
                print(f"[Recording] Starting preview thread...", flush=True)
                self.preview_thread = threading.Thread(target=self.preview_loop, daemon=True)
                self.preview_thread.start()
                print(f"[Recording] ✅ Preview thread started!", flush=True)
                print(f"[Recording] Preview file: {self.preview_base}_latest.jpg", flush=True)
            else:
                print(f"[Recording] Preview disabled", flush=True)
            
            if self.duration:
                # Record for specified duration
                time.sleep(self.duration)
                self.stop_recording()
            else:
                # Record until interrupted
                print("Recording... (send SIGINT or SIGTERM to stop)")
                while self.is_recording:
                    time.sleep(0.1)
            
            return True
            
        except Exception as e:
            print(f"Error during recording: {e}", file=sys.stderr)
            self.stop_recording()
            return False
    
    def stop_recording(self):
        """Stop video recording and preview"""
        if self.picam2 and self.is_recording:
            try:
                self.stop_preview = True
                self.is_recording = False
                
                # Wait for preview thread to finish
                if self.preview_thread and self.preview_thread.is_alive():
                    self.preview_thread.join(timeout=1.0)
                
                self.picam2.stop_recording()
                self.picam2.close()
                
                # Delete preview file
                preview_file = f"{self.preview_base}_latest.jpg"
                if os.path.exists(preview_file):
                    try:
                        os.remove(preview_file)
                        print(f"[Preview] Deleted preview file: {preview_file}", flush=True)
                    except Exception as e:
                        print(f"[Preview] Error deleting preview file: {e}", file=sys.stderr, flush=True)
                
                print(f"Recording stopped: {self.output_path}")
            except Exception as e:
                print(f"Error stopping recording: {e}", file=sys.stderr)

# Global recorder instance for signal handling
recorder = None

def signal_handler(signum, frame):
    """Handle interrupt signals"""
    global recorder
    if recorder:
        print("\nReceived stop signal, stopping recording...")
        recorder.stop_recording()
    sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: video_capture.py <output_path> [duration_seconds] [width] [height] [framerate] [show_preview]")
        sys.exit(1)
    
    output_path = sys.argv[1]
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else None
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 1280
    height = int(sys.argv[4]) if len(sys.argv) > 4 else 720
    framerate = int(sys.argv[5]) if len(sys.argv) > 5 else 30
    show_preview = sys.argv[6].lower() != "false" if len(sys.argv) > 6 else True
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create recorder with preview
    recorder = VideoRecorder(output_path, duration, width, height, framerate, show_preview)
    
    # Start recording
    success = recorder.start_recording()
    sys.exit(0 if success else 1)

