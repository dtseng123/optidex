import { LLMTool } from "../../type";
import { spawn, ChildProcess } from "child_process";
import path from "path";
import fs from "fs";
import { setPendingVisualMode } from "../../utils/image";

const DETECTION_SCRIPT = path.join(__dirname, "../../../python/live_detection.py");
const DETECTION_FRAME = "/tmp/whisplay_detection_frame.jpg";
const VIDEO_DIR = path.join(__dirname, "../../../data/videos");

// Ensure video directory exists
if (!fs.existsSync(VIDEO_DIR)) {
  fs.mkdirSync(VIDEO_DIR, { recursive: true });
}

// Global state
let activeDetectionProcess: ChildProcess | null = null;

const liveDetectionTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "startLiveDetection",
      description:
        "Start live object detection with camera showing real-time bounding boxes around detected objects on the display. "
        + "Optional: enable segmentation overlay. "
        + "Segmentation works best for 'person' (EdgeTPU DeepLab semantic mask if configured) or COCO objects (YOLO instance masks if a YOLO *seg* model is available).",
      parameters: {
        type: "object",
        properties: {
          objects: {
            type: "array",
            items: {
              type: "string",
            },
            description: "List of objects to detect (e.g., ['person', 'cup', 'phone']). Can detect thousands of objects - try: person, hand, face, cup, bottle, phone, laptop, keyboard, mouse, book, pen, plant, chair, table, door, window, car, dog, cat, bird, etc.",
          },
          segmentation: {
            type: "boolean",
            description:
              "Optional: Enable segmentation overlay. For 'person', prefers EdgeTPU DeepLab semantic segmentation if available. Otherwise uses YOLO instance segmentation if a YOLO *seg* model is available (COCO objects only).",
          },
          segModel: {
            type: "string",
            description:
              "Optional: Segmentation model file/path (default: YOLO_SEG_MODEL env or 'yolov8n-seg.pt').",
          },
          duration: {
            type: "number",
            description: "Optional: How many seconds to run detection (default: continuous until stopped)",
          },
        },
        required: ["objects"],
      },
    },
    func: async (params) => {
      try {
        const { objects, duration, segmentation, segModel } = params;

        if (!Array.isArray(objects) || objects.length === 0) {
          return "[error]Please specify at least one object to detect.";
        }

        // Check if already running
        if (activeDetectionProcess) {
          return "[error]Detection already running. Say 'stop detection' first.";
        }

        console.log(`[Tool] Preparing live detection for: ${objects.join(", ")}`);

        // DON'T start the detection process here!
        // Instead, pass the info to ChatFlow via pending visual mode
        // ChatFlow will start the detection process in startVisualMode()
        // This ensures the frames stream in real-time (like recording/playback)
        
        // Generate a video path for recording the detection output
        const videoFileName = `detection-${Date.now()}.mp4`;
        const videoPath = path.join(VIDEO_DIR, videoFileName);

        setPendingVisualMode({
          type: 'detection',
          framePath: DETECTION_FRAME,
          detectionScript: DETECTION_SCRIPT,
          targetObjects: objects,
          detectionSegmentation: Boolean(segmentation),
          detectionSegModel: typeof segModel === "string" && segModel.trim() ? segModel.trim() : undefined,
          duration: duration,
          videoPath: videoPath // Pass the video path for recording
        });

        const objectsList = objects.join(", ");
        const durationText = duration ? ` for ${duration} seconds` : " until you say stop";
        
        const segText = segmentation ? " (with segmentation)" : "";
        return `[success]Starting detection${segText}${durationText} for: ${objectsList}. Recording to video.`;
      } catch (error: any) {
        console.error("Error starting detection:", error);
        activeDetectionProcess = null;
        return `[error]Failed to start detection: ${error.message}`;
      }
    },
  },
  {
    type: "function",
    function: {
      name: "startPersonSegmentation",
      description:
        "Start live person detection with segmentation overlay. "
        + "If EdgeTPU DeepLab segmentation server is enabled, it overlays a semantic person mask; otherwise it may fall back to YOLO segmentation if available.",
      parameters: {
        type: "object",
        properties: {
          duration: {
            type: "number",
            description: "Optional: How many seconds to run (default: continuous until stopped)",
          },
        },
      },
    },
    func: async (params) => {
      // Just delegate to startLiveDetection with the right params
      const duration = params?.duration;
      return await (liveDetectionTools[0] as any).func({
        objects: ["person"],
        segmentation: true,
        duration,
      });
    },
  },

  {
    type: "function",
    function: {
      name: "stopLiveDetection",
      description: "Stop the currently running live object detection",
      parameters: {},
    },
    func: async (params) => {
      try {
        if (!activeDetectionProcess) {
          return "[error]No detection currently running.";
        }

        console.log("Stopping live detection...");

        // Send stop signal to Python script (it monitors state file)
        const { exec } = require("child_process");
        const { promisify } = require("util");
        const execAsync = promisify(exec);
        
        await execAsync(`python3 ${DETECTION_SCRIPT} stop`);

        // Give it a moment to stop gracefully
        await new Promise((resolve) => setTimeout(resolve, 1000));

        // Force kill if still running
        if (activeDetectionProcess) {
          activeDetectionProcess.kill("SIGTERM");
          activeDetectionProcess = null;
        }

        return "[success]Live detection stopped.";
      } catch (error: any) {
        console.error("Error stopping detection:", error);
        
        // Cleanup anyway
        activeDetectionProcess = null;
        return `[error]Failed to stop detection cleanly: ${error.message}`;
      }
    },
  },
];

export default liveDetectionTools;
