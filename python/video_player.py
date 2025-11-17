#!/usr/bin/env python3
"""
Video player using ffplay or omxplayer for Raspberry Pi
"""
import sys
import os
import subprocess
import json

PLAYER_STATE_FILE = "/tmp/whisplay_video_state.json"

def save_state(video_path, player_pid):
    """Save current player state"""
    state = {
        "video_path": video_path,
        "player_pid": player_pid,
        "playing": True
    }
    with open(PLAYER_STATE_FILE, "w") as f:
        json.dump(state, f)

def load_state():
    """Load player state"""
    if os.path.exists(PLAYER_STATE_FILE):
        try:
            with open(PLAYER_STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return None

def clear_state():
    """Clear player state"""
    if os.path.exists(PLAYER_STATE_FILE):
        os.remove(PLAYER_STATE_FILE)

def play_video(video_path):
    """Play video using available player"""
    try:
        # Check if file exists
        if not os.path.exists(video_path):
            print(f"Error: Video file not found: {video_path}", file=sys.stderr)
            return False
        
        # Try ffplay first (works well with H264)
        # -autoexit: exit when video ends
        # -fs: fullscreen
        # -loglevel quiet: suppress ffmpeg logs
        
        # For Raspberry Pi, we'll use ffplay in a subprocess that we can control
        cmd = [
            "ffplay",
            "-autoexit",
            "-loglevel", "error",
            video_path
        ]
        
        print(f"Playing video: {video_path}")
        print(f"Command: {' '.join(cmd)}")
        
        # Start player in background
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Save state for later control
        save_state(video_path, process.pid)
        
        print(f"Video player started (PID: {process.pid})")
        return True
        
    except FileNotFoundError:
        print("Error: ffplay not found. Install with: sudo apt install ffmpeg", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error playing video: {e}", file=sys.stderr)
        return False

def stop_video():
    """Stop currently playing video"""
    try:
        state = load_state()
        if not state:
            print("No video currently playing")
            return True
        
        pid = state.get("player_pid")
        if pid:
            # Kill the player process
            try:
                os.kill(pid, 15)  # SIGTERM
                print(f"Stopped video player (PID: {pid})")
            except ProcessLookupError:
                print("Video player already stopped")
        
        clear_state()
        return True
        
    except Exception as e:
        print(f"Error stopping video: {e}", file=sys.stderr)
        clear_state()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: video_player.py <play|stop> [video_path]")
        sys.exit(1)
    
    action = sys.argv[1]
    
    if action == "play":
        if len(sys.argv) < 3:
            print("Error: video_path required for play action")
            sys.exit(1)
        video_path = sys.argv[2]
        success = play_video(video_path)
        sys.exit(0 if success else 1)
    
    elif action == "stop":
        success = stop_video()
        sys.exit(0 if success else 1)
    
    else:
        print(f"Error: Unknown action '{action}'")
        sys.exit(1)




