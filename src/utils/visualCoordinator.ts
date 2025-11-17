import { display } from "../device/display";
import fs from "fs";
import { 
  setLiveDetectionActive, 
  setVideoRecordingActive,
  clearVideoPlayback,
  isLiveDetectionRunning,
  isVideoRecording,
  isVideoPlaybackActive
} from "./image";

// Paths for visual mode frames
export const DETECTION_FRAME = "/tmp/whisplay_detection_frame.jpg";
export const RECORDING_PREVIEW_LATEST = "/tmp/whisplay_video_preview_latest.jpg";
export const VIDEO_PLAYBACK_FRAME = "/tmp/whisplay_current_video_frame.jpg";

// Active intervals
let detectionInterval: NodeJS.Timeout | null = null;
let recordingInterval: NodeJS.Timeout | null = null;
let playbackInterval: NodeJS.Timeout | null = null;

// Start live detection display (called by ChatFlow after TTS)
export const startDetectionDisplay = () => {
  console.log("[VisualCoordinator] Starting detection display");
  setLiveDetectionActive(true);
  
  // Clear any text from display
  display({
    RGB: "#00FFFF", // Cyan for detection mode
    text: "",
    emoji: "",
    image: "",
  });
  
  // Start updating display with detection frames
  detectionInterval = setInterval(() => {
    if (fs.existsSync(DETECTION_FRAME)) {
      display({
        RGB: "#00FFFF",
        image: DETECTION_FRAME,
      });
    }
  }, 100);
};

// Stop live detection display
export const stopDetectionDisplay = () => {
  console.log("[VisualCoordinator] Stopping detection display");
  if (detectionInterval) {
    clearInterval(detectionInterval);
    detectionInterval = null;
  }
  setLiveDetectionActive(false);
  
  display({
    RGB: "#00c8a3",
    emoji: "⏹️",
    text: "Detection stopped",
    image: "",
  });
};

// Start recording preview display (called by ChatFlow after TTS)
export const startRecordingDisplay = () => {
  console.log("[VisualCoordinator] Starting recording display");
  setVideoRecordingActive(true);
  
  let lastFrameNum = 0;
  recordingInterval = setInterval(() => {
    if (fs.existsSync(RECORDING_PREVIEW_LATEST)) {
      display({
        RGB: "#FF0000", // Red for recording
        image: RECORDING_PREVIEW_LATEST,
      });
    } else {
      // Fallback to rotating frames
      const frame0 = "/tmp/whisplay_video_preview_0.jpg";
      const frame1 = "/tmp/whisplay_video_preview_1.jpg";
      const checkFrame = lastFrameNum === 0 ? frame1 : frame0;
      if (fs.existsSync(checkFrame)) {
        display({
          RGB: "#FF0000",
          image: checkFrame,
        });
        lastFrameNum = 1 - lastFrameNum;
      }
    }
  }, 150);
};

// Stop recording preview display
export const stopRecordingDisplay = () => {
  console.log("[VisualCoordinator] Stopping recording display");
  if (recordingInterval) {
    clearInterval(recordingInterval);
    recordingInterval = null;
  }
  setVideoRecordingActive(false);
  
  display({
    RGB: "#00c8a3",
    emoji: "✅",
    text: "Recording complete",
    image: "",
  });
};

// Start video playback display (called by ChatFlow after TTS)
export const startPlaybackDisplay = () => {
  console.log("[VisualCoordinator] Starting playback display");
  if (playbackInterval) {
    // Already running
    return;
  }

  playbackInterval = setInterval(() => {
    if (fs.existsSync(VIDEO_PLAYBACK_FRAME)) {
      display({
        RGB: "#0000FF", // Blue for playback
        image: VIDEO_PLAYBACK_FRAME,
      });
    }
  }, 50);
};

// Stop video playback display
export const stopPlaybackDisplay = () => {
  console.log("[VisualCoordinator] Stopping playback display");
  if (playbackInterval) {
    clearInterval(playbackInterval);
    playbackInterval = null;
  }
  clearVideoPlayback();
  
  display({
    RGB: "#00c8a3",
    emoji: "✅",
    text: "Video finished",
    image: "",
  });
};

// Check if any display is active
export const isAnyDisplayActive = () => {
  return detectionInterval !== null || recordingInterval !== null || playbackInterval !== null;
};

// Stop all displays
export const stopAllDisplays = () => {
  stopDetectionDisplay();
  stopRecordingDisplay();
  stopPlaybackDisplay();
};
