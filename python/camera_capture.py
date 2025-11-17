#!/usr/bin/env python3
"""
Camera capture script using picamera2
"""
import sys
import os
from picamera2 import Picamera2
from PIL import Image
import time

def capture_image(output_path, width=1024, height=1024):
    """
    Capture an image using picamera2
    
    Args:
        output_path: Path where to save the image
        width: Image width (default: 1024)
        height: Image height (default: 1024)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Initialize camera
        picam2 = Picamera2()
        
        # Configure camera for still capture
        # Using a 4:3 aspect ratio for capture, then we'll crop to square
        capture_config = picam2.create_still_configuration(
            main={"size": (width, height)},
            display=None  # No preview window
        )
        
        picam2.configure(capture_config)
        
        # Start camera
        picam2.start()
        
        # Let camera warm up and adjust settings
        time.sleep(0.5)
        
        # Capture image
        image = picam2.capture_image("main")
        
        # Save image
        image.save(output_path, quality=95)
        
        # Stop camera
        picam2.stop()
        picam2.close()
        
        print(f"Image captured successfully: {output_path}")
        return True
        
    except Exception as e:
        print(f"Error capturing image: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: camera_capture.py <output_path> [width] [height]")
        sys.exit(1)
    
    output_path = sys.argv[1]
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    height = int(sys.argv[3]) if len(sys.argv) > 3 else 1024
    
    success = capture_image(output_path, width, height)
    sys.exit(0 if success else 1)




