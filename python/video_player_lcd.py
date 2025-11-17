#!/usr/bin/env python3
"""
Video player for whisplay LCD display
Extracts frames from H.264 video and displays them on the LCD
"""
import sys
import os
import subprocess
import tempfile
import time
import json
from pathlib import Path

# State file for playback control
STATE_FILE = "/tmp/whisplay_video_playback.json"
FRAME_DIR = "/tmp/whisplay_video_frames"

def save_state(video_path, is_playing, frame_count=0):
    """Save playback state"""
    state = {
        "video_path": video_path,
        "is_playing": is_playing,
        "frame_count": frame_count,
        "timestamp": time.time()
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def load_state():
    """Load playback state"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return None

def clear_state():
    """Clear playback state"""
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)

def extract_frame_count(video_path):
    """Get total frame count from video"""
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-count_packets",
            "-show_entries", "stream=nb_read_packets",
            "-of", "csv=p=0",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return int(result.stdout.strip())
    except:
        return 0

def extract_video_frames(video_path, output_pattern, max_frames=300):
    """
    Extract frames from video using ffmpeg
    
    Args:
        video_path: Path to H.264 video
        output_pattern: Pattern for output frames (e.g., frame_%04d.jpg)
        max_frames: Maximum number of frames to extract
    """
    try:
        # Extract frames at original fps, but limit total frames
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vf", f"select='not(mod(n\\,1))',scale=240:280:force_original_aspect_ratio=decrease,pad=240:280:(ow-iw)/2:(oh-ih)/2",
            "-vframes", str(max_frames),
            "-q:v", "3",  # Quality (1-31, lower is better)
            "-y",  # Overwrite
            output_pattern
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"ffmpeg error: {result.stderr}", file=sys.stderr)
            return False
        
        return True
        
    except Exception as e:
        print(f"Error extracting frames: {e}", file=sys.stderr)
        return False

def play_video_on_lcd(video_path, target_socket="127.0.0.1", target_port=8765):
    """
    Play video on LCD by displaying frames sequentially
    
    Args:
        video_path: Path to video file
        target_socket: Socket to send frame updates (for future use)
        target_port: Port for socket communication
    """
    try:
        if not os.path.exists(video_path):
            print(f"Error: Video file not found: {video_path}", file=sys.stderr)
            return False
        
        # Create temp directory for frames
        os.makedirs(FRAME_DIR, exist_ok=True)
        
        # Clean up old frames
        for f in Path(FRAME_DIR).glob("frame_*.jpg"):
            f.unlink()
        
        print(f"Extracting frames from: {video_path}")
        
        # Extract frames
        output_pattern = os.path.join(FRAME_DIR, "frame_%04d.jpg")
        if not extract_video_frames(video_path, output_pattern):
            return False
        
        # Get list of extracted frames
        frames = sorted(Path(FRAME_DIR).glob("frame_*.jpg"))
        frame_count = len(frames)
        
        if frame_count == 0:
            print("Error: No frames extracted", file=sys.stderr)
            return False
        
        print(f"Extracted {frame_count} frames")
        
        # Calculate frame delay - slow down to match display update rate
        # Display updates every 50ms, so use similar timing
        frame_delay = 0.05  # 20 FPS for smoother display on LCD
        
        # Save state
        save_state(video_path, True, frame_count)
        
        # Create a marker file that display can read
        current_frame_marker = "/tmp/whisplay_current_video_frame.jpg"
        
        print(f"Playing video on LCD...")
        
        # Play frames
        for i, frame_path in enumerate(frames):
            # Check if playback should stop
            state = load_state()
            if not state or not state.get("is_playing"):
                print("Playback stopped")
                break
            
            # Copy frame to marker location for display system to read
            try:
                # Use hard copy for reliability (symlinks can cause display issues)
                import shutil
                shutil.copy(str(frame_path), current_frame_marker)
            except Exception as e:
                print(f"Error copying frame: {e}", file=sys.stderr)
                continue
            
            # Progress indicator
            if (i + 1) % 20 == 0:  # Every second
                print(f"Playing... {i+1}/{frame_count} frames", flush=True)
            
            # Wait before next frame
            time.sleep(frame_delay)
        
        print("Playback complete", flush=True)
        
        # Keep the last frame visible for 2 seconds before cleanup
        time.sleep(2.0)
        
        # Clean up
        if os.path.exists(current_frame_marker):
            os.remove(current_frame_marker)
        
        clear_state()
        
        return True
        
    except Exception as e:
        print(f"Error playing video: {e}", file=sys.stderr)
        clear_state()
        return False

def stop_playback():
    """Stop current video playback"""
    try:
        state = load_state()
        if state:
            save_state(state.get("video_path", ""), False)
            print("Playback stop requested")
            
            # Clean up marker file
            marker = "/tmp/whisplay_current_video_frame.jpg"
            if os.path.exists(marker):
                os.remove(marker)
            
            return True
        else:
            print("No active playback")
            return True
    except Exception as e:
        print(f"Error stopping playback: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: video_player_lcd.py <play|stop> [video_path]")
        sys.exit(1)
    
    action = sys.argv[1]
    
    if action == "play":
        if len(sys.argv) < 3:
            print("Error: video_path required for play action")
            sys.exit(1)
        video_path = sys.argv[2]
        success = play_video_on_lcd(video_path)
        sys.exit(0 if success else 1)
    
    elif action == "stop":
        success = stop_playback()
        sys.exit(0 if success else 1)
    
    else:
        print(f"Error: Unknown action '{action}'")
        sys.exit(1)


