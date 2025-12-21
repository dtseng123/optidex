/**
 * VR Passthrough Detection Tool
 * Calls the vr-passthrough detection server via socket
 * 
 * This tool allows optidex to use YOLO detection on the VR stereo cameras
 * without embedding the vr-passthrough code directly (licensing separation)
 */

import { LLMTool } from "../../type";
import * as net from "net";
import * as fs from "fs";
import path from "path";

const VR_DETECTION_HOST = "localhost";
const VR_DETECTION_PORT = 5580;
const DETECTION_TIMEOUT = 10000; // 10 seconds

// Store latest frame path for image analysis
let lastDetectionFramePath: string | null = null;

interface DetectionResult {
  class_name: string;
  confidence: number;
  bbox: number[];
  eye: string;
}

interface ServerResponse {
  success?: boolean;
  error?: string;
  detections?: DetectionResult[];
  path?: string;
  exists?: boolean;
  [key: string]: any;
}

/**
 * Send command to VR detection server and get response
 */
async function sendCommand(command: object): Promise<ServerResponse> {
  return new Promise((resolve, reject) => {
    const client = new net.Socket();
    let buffer = "";
    let resolved = false;

    const timeout = setTimeout(() => {
      if (!resolved) {
        resolved = true;
        client.destroy();
        reject(new Error("Connection timeout"));
      }
    }, DETECTION_TIMEOUT);

    client.connect(VR_DETECTION_PORT, VR_DETECTION_HOST, () => {
      const message = JSON.stringify(command) + "\n";
      client.write(message);
    });

    client.on("data", (data) => {
      buffer += data.toString();
      if (buffer.includes("\n")) {
        clearTimeout(timeout);
        const line = buffer.split("\n")[0];
        try {
          const response = JSON.parse(line);
          resolved = true;
          client.destroy();
          resolve(response);
        } catch (e) {
          resolved = true;
          client.destroy();
          reject(new Error("Invalid JSON response"));
        }
      }
    });

    client.on("error", (err) => {
      clearTimeout(timeout);
      if (!resolved) {
        resolved = true;
        reject(err);
      }
    });

    client.on("close", () => {
      clearTimeout(timeout);
      if (!resolved) {
        resolved = true;
        reject(new Error("Connection closed"));
      }
    });
  });
}

/**
 * Check if VR detection server is running
 */
async function isServerRunning(): Promise<boolean> {
  try {
    const response = await sendCommand({ cmd: "ping" });
    return response.status === "ok";
  } catch {
    return false;
  }
}

/**
 * Get path to latest detection frame for image analysis
 */
export function getLastDetectionFramePath(): string | null {
  return lastDetectionFramePath;
}

const vrDetectionTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "startStereoLiveDetection",
      description:
        "Alias for VR passthrough live detection. Starts stereo camera detection overlays directly in the VR headset. Prefer this for VR/stereo/passthrough requests.",
      parameters: {
        type: "object",
        properties: {
          objects: {
            type: "array",
            items: { type: "string" },
            description:
              "Objects to detect (default: ['person'] if omitted).",
          },
          duration: {
            type: "number",
            description: "Duration in seconds (optional)",
          },
        },
      },
    },
    func: async (params) => {
      const objects = Array.isArray(params?.objects) && params.objects.length ? params.objects : ["person"];
      const duration = typeof params?.duration === "number" ? params.duration : undefined;
      // Reuse the existing implementation by calling the same command path
      const tool = vrDetectionTools.find((t) => t.function.name === "vrStartLiveDetectionDisplay");
      if (!tool) return "[error]VR detection tool not available.";
      return await tool.func({ objects, duration } as any);
    },
  },
  {
    type: "function",
    function: {
      name: "vrDetectObjects",
      description:
        "Detect objects using the VR headset's stereo cameras with YOLO-World. Returns detected objects with their locations in left and right eye views. Use this for spatial awareness through the VR passthrough cameras.",
      parameters: {
        type: "object",
        properties: {
          objects: {
            type: "array",
            items: { type: "string" },
            description:
              "List of objects to detect (e.g., ['person', 'hand', 'cup', 'phone']). YOLO-World supports open vocabulary - you can detect almost any object by name.",
          },
          confidence: {
            type: "number",
            description:
              "Minimum confidence threshold (0.0-1.0, default 0.3)",
          },
        },
        required: ["objects"],
      },
    },
    func: async (params) => {
      try {
        const { objects, confidence = 0.3 } = params;

        if (!Array.isArray(objects) || objects.length === 0) {
          return "[error]Please specify at least one object to detect.";
        }

        // Check if server is running
        const serverUp = await isServerRunning();
        if (!serverUp) {
          return "[error]VR detection server not running. Start it with: python3 /home/dash/vr-passthrough/python/detection_server.py";
        }

        // Set confidence
        await sendCommand({ cmd: "set_confidence", confidence });

        // Set classes
        const classResponse = await sendCommand({
          cmd: "set_classes",
          classes: objects,
        });
        if (!classResponse.success) {
          return `[error]Failed to set detection classes: ${classResponse.error}`;
        }

        // Run detection
        console.log(`[VR Detection] Looking for: ${objects.join(", ")}`);
        const result = await sendCommand({ cmd: "detect" });

        if (!result.success) {
          return `[error]Detection failed: ${result.error}`;
        }

        const detections = result.detections || [];

        // Get frame path for potential image analysis
        const frameResponse = await sendCommand({ cmd: "get_frame_path" });
        if (frameResponse.success && frameResponse.exists && frameResponse.path) {
          lastDetectionFramePath = frameResponse.path;
        }

        if (detections.length === 0) {
          return `[success]No objects detected matching: ${objects.join(", ")}`;
        }

        // Format results
        const leftEye = detections.filter((d: DetectionResult) => d.eye === "left");
        const rightEye = detections.filter((d: DetectionResult) => d.eye === "right");

        let summary = `[success]Detected ${detections.length} object(s):\n`;

        if (leftEye.length > 0) {
          summary += `\nLeft eye (${leftEye.length}):\n`;
          for (const det of leftEye) {
            summary += `  - ${det.class_name}: ${(det.confidence * 100).toFixed(1)}% confidence\n`;
          }
        }

        if (rightEye.length > 0) {
          summary += `\nRight eye (${rightEye.length}):\n`;
          for (const det of rightEye) {
            summary += `  - ${det.class_name}: ${(det.confidence * 100).toFixed(1)}% confidence\n`;
          }
        }

        return summary;
      } catch (error: any) {
        console.error("VR detection error:", error);
        return `[error]VR detection failed: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "vrStartContinuousDetection",
      description:
        "Start continuous object detection on VR cameras. Objects will be detected repeatedly until stopped.",
      parameters: {
        type: "object",
        properties: {
          objects: {
            type: "array",
            items: { type: "string" },
            description: "List of objects to continuously detect",
          },
        },
        required: ["objects"],
      },
    },
    func: async (params) => {
      try {
        const { objects } = params;

        if (!Array.isArray(objects) || objects.length === 0) {
          return "[error]Please specify at least one object to detect.";
        }

        const serverUp = await isServerRunning();
        if (!serverUp) {
          return "[error]VR detection server not running.";
        }

        // Set classes
        await sendCommand({ cmd: "set_classes", classes: objects });

        // Start continuous
        const result = await sendCommand({ cmd: "start_continuous" });

        if (result.success) {
          return `[success]Started continuous detection for: ${objects.join(", ")}. Say "stop VR detection" to stop.`;
        } else {
          return `[error]Failed to start: ${result.error}`;
        }
      } catch (error: any) {
        return `[error]Failed: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "vrStopContinuousDetection",
      description: "Stop continuous object detection on VR cameras",
      parameters: {},
    },
    func: async () => {
      try {
        const result = await sendCommand({ cmd: "stop_continuous" });
        if (result.success) {
          return "[success]Continuous detection stopped.";
        } else {
          return `[error]${result.error}`;
        }
      } catch (error: any) {
        return `[error]Failed to stop: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "vrGetLatestDetections",
      description:
        "Get the most recent detection results from continuous VR detection",
      parameters: {},
    },
    func: async () => {
      try {
        const result = await sendCommand({ cmd: "get_latest" });

        if (!result.success) {
          return `[error]${result.error}`;
        }

        const detections = result.detections || [];
        if (detections.length === 0) {
          return "[success]No recent detections.";
        }

        let summary = `[success]Latest detections (${detections.length}):\n`;
        for (const det of detections) {
          summary += `  - ${det.class_name}: ${(det.confidence * 100).toFixed(1)}% (${det.eye} eye)\n`;
        }

        return summary;
      } catch (error: any) {
        return `[error]Failed: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "vrDetectionStatus",
      description: "Get the status of the VR detection server",
      parameters: {},
    },
    func: async () => {
      try {
        const serverUp = await isServerRunning();
        if (!serverUp) {
          return "[error]VR detection server is not running. Start with: python3 /home/dash/vr-passthrough/python/detection_server.py";
        }

        const status = await sendCommand({ cmd: "status" });

        return `[success]VR Detection Server Status:
  - Model loaded: ${status.model_loaded ? "Yes" : "No"}
  - Camera active: ${status.camera_active ? "Yes" : "No"}
  - Continuous detection: ${status.continuous_detection ? "Running" : "Stopped"}
  - Target objects: ${status.target_objects?.join(", ") || "None set"}
  - Confidence threshold: ${status.confidence_threshold}`;
      } catch (error: any) {
        return `[error]Failed to get status: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "vrStartLiveDetectionDisplay",
      description:
        "Start live VR/stereo passthrough detection with video display showing bounding boxes around detected objects directly on the VR headset screen (stereo cameras). Use this when the user mentions VR, headset, passthrough, stereo cameras, or wants green boxes in-headset.",
      parameters: {
        type: "object",
        properties: {
          objects: {
            type: "array",
            items: { type: "string" },
            description:
              "List of objects to detect and display (e.g., ['person', 'hand', 'cup'])",
          },
          duration: {
            type: "number",
            description: "Duration in seconds (optional, default: until stopped)",
          },
        },
        required: ["objects"],
      },
    },
    func: async (params) => {
      try {
        const { objects, duration } = params;

        if (!Array.isArray(objects) || objects.length === 0) {
          return "[error]Please specify at least one object to detect.";
        }

        const { exec } = require("child_process");
        const { promisify } = require("util");
        const execAsync = promisify(exec);

        // Build command
        let cmd = `/home/dash/vr-passthrough/startup.sh detect ${objects.join(" ")}`;
        if (duration) {
          cmd += ` -d ${duration}`;
        }

        console.log(`[VR Detection] Starting live display: ${cmd}`);

        // Start in background
        exec(cmd, (error: any, stdout: string, stderr: string) => {
          if (error) {
            console.error(`VR detection display error: ${error.message}`);
          }
        });

        const durationText = duration ? ` for ${duration} seconds` : "";
        return `[success]Started VR live detection display${durationText} for: ${objects.join(", ")}. The VR display will show camera feed with detection boxes. Say "stop VR detection" to stop.`;
      } catch (error: any) {
        return `[error]Failed to start: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "vrStopLiveDetectionDisplay",
      description: "Stop the live VR detection display",
      parameters: {},
    },
    func: async () => {
      try {
        const { exec } = require("child_process");
        const { promisify } = require("util");
        const execAsync = promisify(exec);
        const fs = require("fs");

        // Write stop signal to state file
        const state = {
          target_objects: [],
          is_running: false,
          timestamp: Date.now() / 1000,
        };
        fs.writeFileSync(
          "/tmp/vr_detection_state.json",
          JSON.stringify(state)
        );

        // Also try to kill the process
        try {
          await execAsync("pkill -f detection_display.py");
        } catch {
          // Process may have already stopped
        }

        return "[success]VR live detection display stopped.";
      } catch (error: any) {
        return `[error]Failed to stop: ${error.message}`;
      }
    },
  },
];

export default vrDetectionTools;

