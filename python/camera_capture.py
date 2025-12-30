#!/usr/bin/env python3
"""
Camera capture script using picamera2
"""
import sys
import os
from picamera2 import Picamera2
from PIL import Image
import time
import fcntl
import signal

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
    picam2 = None
    for attempt in range(1, 6):
        try:
            # Initialize camera
            picam2 = Picamera2()
            
            # Configure camera for still capture
            capture_config = picam2.create_still_configuration(
                main={"size": (width, height)},
                display=None,  # No preview window
            )
            
            picam2.configure(capture_config)
            
            # Start camera
            picam2.start()
            
            # Let camera warm up and adjust settings
            time.sleep(0.6)
            
            # Capture image
            image = picam2.capture_image("main")
            
            # Save image
            image.save(output_path, quality=95)
            
            print(f"Image captured successfully: {output_path}")
            return True
            
        except Exception as e:
            msg = str(e)
            # libcamera pipeline is commonly held by other vision processes; retry briefly
            if (
                "Pipeline handler in use by another process" in msg
                or "Device or resource busy" in msg
                or "Resource temporarily unavailable" in msg
            ):
                print(
                    f"Camera busy (attempt {attempt}/5): {msg}",
                    file=sys.stderr,
                )
                time.sleep(0.7)
                continue
            print(f"Error capturing image: {e}", file=sys.stderr)
            return False
        finally:
            try:
                if picam2 is not None:
                    try:
                        picam2.stop()
                    except Exception:
                        pass
                    try:
                        picam2.close()
                    except Exception:
                        pass
            except Exception:
                pass
            picam2 = None
    print("Error capturing image: camera remained busy after retries", file=sys.stderr)
    return False


def _acquire_lock(lock_path="/tmp/optidex_picamera2.lock", timeout_s=10):
    """
    Prevent concurrent picamera2 usage, which can wedge libcamera or the kernel driver.
    """
    start = time.time()
    lock_f = open(lock_path, "w")
    while True:
        try:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_f
        except BlockingIOError:
            if time.time() - start > timeout_s:
                lock_f.close()
                raise TimeoutError("camera lock timeout")
            time.sleep(0.1)


def _with_timeout(seconds: int):
    def _handler(signum, frame):
        raise TimeoutError("camera capture timeout")
    signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: camera_capture.py <output_path> [width] [height]")
        sys.exit(1)
    
    output_path = sys.argv[1]
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    height = int(sys.argv[3]) if len(sys.argv) > 3 else 1024
    
    lock_f = None
    try:
        lock_f = _acquire_lock()
        _with_timeout(20)
        success = capture_image(output_path, width, height)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Error capturing image: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            signal.alarm(0)
        except Exception:
            pass
        try:
            if lock_f is not None:
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
                lock_f.close()
        except Exception:
            pass
