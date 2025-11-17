import { LLMTool } from "../../type";
import { exec, spawn, ChildProcess } from "child_process";
import { promisify } from "util";
import path from "path";
import { setVideoPlaybackMarker, setPendingVisualMode } from "../../utils/image";
import fs from "fs";

const execAsync = promisify(exec);

// Paths
const VIDEO_DIR = path.join(__dirname, "../../../data/videos");
const VIDEO_CAPTURE_SCRIPT = path.join(__dirname, "../../../python/video_capture.py");
const VIDEO_PLAYER_SCRIPT = path.join(__dirname, "../../../python/video_player_lcd.py");
const VIDEO_FRAME_PATH = "/tmp/whisplay_current_video_frame.jpg";
const RECORDING_PREVIEW_FRAME = "/tmp/whisplay_video_preview_latest.jpg";

// Ensure video directory exists
if (!fs.existsSync(VIDEO_DIR)) {
  fs.mkdirSync(VIDEO_DIR, { recursive: true });
}

// Global state for active recording
let activeRecordingProcess: ChildProcess | null = null;
let activeRecordingPath: string | null = null;

// Global state for video playback
let activePlaybackProcess: ChildProcess | null = null;

const videoTools: LLMTool[] = [
  // Record video for specific duration
  {
    type: "function",
    function: {
      name: "recordVideoForDuration",
      description: "Record a video for a specific number of seconds",
      parameters: {
        type: "object",
        properties: {
          duration: {
            type: "number",
            description: "Duration in seconds to record (e.g., 5, 10, 30)",
          },
        },
        required: ["duration"],
      },
    },
    func: async (params) => {
      try {
        const { duration } = params;
        
        if (!duration || duration <= 0 || duration > 300) {
          return "[error]Duration must be between 1 and 300 seconds.";
        }

        // Check if already recording
        if (activeRecordingProcess) {
          return "[error]Already recording. Please stop current recording first.";
        }

        const fileName = `video-${Date.now()}.h264`;
        const videoPath = path.join(VIDEO_DIR, fileName);

        console.log(`[Tool] Preparing to record video for ${duration} seconds: ${videoPath}`);

        // Store the path for later use
        activeRecordingPath = videoPath;

        // DON'T start the recording process here!
        // Instead, pass the info to ChatFlow via pending visual mode
        // ChatFlow will start the recording process in startVisualMode()
        // This ensures the preview runs concurrently with recording (like playback does)
        
        setPendingVisualMode({
          type: 'recording',
          framePath: RECORDING_PREVIEW_FRAME,
          videoPath: videoPath,
          duration: duration,
          recordingScript: VIDEO_CAPTURE_SCRIPT
        });

        return `[success]Recording ${duration}s video with live preview`;
      } catch (error: any) {
        console.error("Error preparing video recording:", error);
        return `[error]Failed to prepare recording: ${error.message}`;
      }
    },
  },

  // Start continuous recording
  {
    type: "function",
    function: {
      name: "startVideoRecording",
      description: "Start recording a video continuously until explicitly stopped by the user",
      parameters: {},
    },
    func: async (params) => {
      try {
        // Check if already recording
        if (activeRecordingProcess) {
          return "[error]Already recording. Please stop current recording first.";
        }

        const fileName = `video-${Date.now()}.h264`;
        const videoPath = path.join(VIDEO_DIR, fileName);

        console.log(`[Tool] Preparing continuous video recording: ${videoPath}`);

        // Store the path for later use
        activeRecordingPath = videoPath;

        // DON'T start the recording process here!
        // Pass info to ChatFlow via pending visual mode (like timed recording)
        setPendingVisualMode({
          type: 'recording',
          framePath: RECORDING_PREVIEW_FRAME,
          videoPath: videoPath,
          duration: undefined,  // Continuous - no duration
          recordingScript: VIDEO_CAPTURE_SCRIPT
        });

        return "[success]Starting video recording with live preview";
      } catch (error: any) {
        console.error("Error preparing video recording:", error);
        return `[error]Failed to prepare recording: ${error.message}`;
      }
    },
  },

  // Stop continuous recording
  {
    type: "function",
    function: {
      name: "stopVideoRecording",
      description: "Stop the current continuous video recording",
      parameters: {},
    },
    func: async (params) => {
      try {
        if (!activeRecordingProcess) {
          return "[error]No active recording to stop.";
        }

        console.log("Stopping video recording...");

        // Send SIGTERM to gracefully stop recording
        activeRecordingProcess.kill("SIGTERM");

        // Wait for process to exit
        await new Promise((resolve) => {
          if (activeRecordingProcess) {
            activeRecordingProcess.on("exit", resolve);
            // Timeout after 3 seconds
            setTimeout(resolve, 3000);
          } else {
            resolve(null);
          }
        });

        activeRecordingProcess = null;

        // Check if file was created
        if (activeRecordingPath && fs.existsSync(activeRecordingPath)) {
          const fileSizeBytes = fs.statSync(activeRecordingPath).size;
          const fileSizeMB = (fileSizeBytes / (1024 * 1024)).toFixed(2);

          console.log(`Video saved: ${activeRecordingPath} (${fileSizeMB}MB)`);
          return `[success]Recording stopped. Video saved (${fileSizeMB}MB). Ready to play.`;
        } else {
          return "[error]Recording stopped but video file not found.";
        }
      } catch (error: any) {
        console.error("Error stopping video recording:", error);
        activeRecordingProcess = null;
        return `[error]Failed to stop recording: ${error.message}`;
      }
    },
  },

  // Play the most recent video
  {
    type: "function",
    function: {
      name: "playVideo",
      description: "Play the most recently recorded video on the display",
      parameters: {},
    },
    func: async (params) => {
      try {
        // Use the last recorded video or find the most recent one
        let videoPath = activeRecordingPath;

        if (!videoPath || !fs.existsSync(videoPath)) {
          // Find most recent video in directory
          const files = fs
            .readdirSync(VIDEO_DIR)
            .filter((f) => f.endsWith(".mp4") || f.endsWith(".h264"))
            .map((f) => ({
              name: f,
              path: path.join(VIDEO_DIR, f),
              time: fs.statSync(path.join(VIDEO_DIR, f)).mtime.getTime(),
            }))
            .sort((a, b) => b.time - a.time);

          if (files.length === 0) {
            return "[error]No videos found to play.";
          }

          videoPath = files[0].path;
        }

        console.log(`Preparing video for playback: ${videoPath}`);

        // Store video path for ChatFlow to use
        // Don't start playback yet - ChatFlow will start it in visual mode
        activeRecordingPath = videoPath;  // Reuse this variable to store video path
        
        // Set pending visual mode - ChatFlow will start display AND playback after TTS
        setVideoPlaybackMarker(videoPath); // Pass video path, not frame path
        setPendingVisualMode({
          type: 'playback',
          framePath: videoPath  // Store video path here temporarily
        });

        return "[success]Starting video playback";
      } catch (error: any) {
        console.error("Error playing video:", error);
        activePlaybackProcess = null;
        return `[error]Failed to play video: ${error.message}`;
      }
    },
  },

  // Stop video playback
  {
    type: "function",
    function: {
      name: "stopVideo",
      description: "Stop the currently playing video",
      parameters: {},
    },
    func: async (params) => {
      try {
        console.log("Stopping video playback...");

        // Send stop command to player
        const command = `python3 ${VIDEO_PLAYER_SCRIPT} stop`;
        const { stdout, stderr } = await execAsync(command);

        if (stdout) console.log("Stop output:", stdout);
        if (stderr && !stderr.includes("No active")) {
          console.error("Stop stderr:", stderr);
        }

        // Kill process if still active
        if (activePlaybackProcess) {
          activePlaybackProcess.kill("SIGTERM");
          activePlaybackProcess = null;
        }

        return "[success]Video playback stopped.";
      } catch (error: any) {
        console.error("Error stopping video:", error);
        
        if (activePlaybackProcess) {
          activePlaybackProcess.kill("SIGTERM");
          activePlaybackProcess = null;
        }
        
        return `[error]Failed to stop video: ${error.message}`;
      }
    },
  },
];

export default videoTools;
