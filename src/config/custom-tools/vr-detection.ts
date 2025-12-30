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

// COCO classes supported by the Coral EdgeTPU detector (SSD MobileNet)
// We use this to decide when we can fall back to the in-headset Coral overlay
// (vr_passthrough watches /tmp/vr_detection_state.json) instead of requiring
// the 5580 YOLO-World detection server.
const COCO_CLASSES = new Set<string>([
  "person","bicycle","car","motorcycle","airplane","bus","train","truck","boat","traffic light","fire hydrant",
  "stop sign","parking meter","bench","bird","cat","dog","horse","sheep","cow","elephant","bear","zebra","giraffe",
  "backpack","umbrella","handbag","tie","suitcase","frisbee","skis","snowboard","sports ball","kite","baseball bat",
  "baseball glove","skateboard","surfboard","tennis racket","bottle","wine glass","cup","fork","knife","spoon","bowl",
  "banana","apple","sandwich","orange","broccoli","carrot","hot dog","pizza","donut","cake","chair","couch",
  "potted plant","bed","dining table","toilet","tv","laptop","mouse","remote","keyboard","cell phone","microwave",
  "oven","toaster","sink","refrigerator","book","clock","vase","scissors","teddy bear","hair drier","toothbrush"
]);

function canUseCoralOverlay(objects: string[]): boolean {
  if (!Array.isArray(objects) || objects.length === 0) return false;
  return objects.every((o) => COCO_CLASSES.has(String(o).toLowerCase().trim()));
}

function enableInHeadsetOverlay(objects: string[], confidence = 0.3, duration?: number, segmentation = false, smoothing = "low"): void {
  const now = Date.now() / 1000;
  const stopAt = typeof duration === "number" && duration > 0 ? now + duration : undefined;
  const state: any = {
    target_objects: objects,
    is_running: true,
    timestamp: now,
    confidence,
    segmentation,
    smoothing,
  };
  if (stopAt) state.stop_at = stopAt;
  fs.writeFileSync("/tmp/vr_detection_state.json", JSON.stringify(state));
}

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
        "Alias for VR passthrough live detection. Starts stereo camera detection overlays directly in the VR headset. Prefer this for VR/stereo/passthrough requests. Optionally enable segmentation for person silhouette masks. Kalman filtering provides temporal smoothing.",
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
          segmentation: {
            type: "boolean",
            description:
              "Enable semantic segmentation overlay (person silhouette mask). Requires EdgeTPU segmentation server.",
          },
          smoothing: {
            type: "string",
            enum: ["none", "low", "medium", "high"],
            description:
              "Kalman filter smoothing level. Default: 'low' (responsive).",
          },
        },
      },
    },
    func: async (params) => {
      const objects = Array.isArray(params?.objects) && params.objects.length ? params.objects : ["person"];
      const duration = typeof params?.duration === "number" ? params.duration : undefined;
      const segmentation = Boolean(params?.segmentation);
      const smoothing = typeof params?.smoothing === "string" ? params.smoothing : "low";
      // Reuse the existing implementation by calling the same command path
      const tool = vrDetectionTools.find((t) => t.function.name === "vrStartLiveDetectionDisplay");
      if (!tool) return "[error]VR detection tool not available.";
      return await tool.func({ objects, duration, segmentation, smoothing } as any);
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

        // Prefer Coral in-headset overlay for COCO classes (e.g., "person").
        // This does NOT require the 5580 YOLO-World server and avoids breaking passthrough.
        const serverUp = await isServerRunning();
        if (!serverUp) {
          if (canUseCoralOverlay(objects)) {
            enableInHeadsetOverlay(objects, confidence);
            return `[success]Enabled in-headset Coral detection overlay for: ${objects.join(", ")}. Green boxes should appear in VR passthrough.`;
          }
          return "[error]VR detection server not running (YOLO-World, port 5580). For non-COCO objects, start it with: python3 /home/dash/vr-passthrough/python/detection_server.py";
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
          if (canUseCoralOverlay(objects)) {
            enableInHeadsetOverlay(objects, 0.3);
            return `[success]Enabled in-headset Coral detection overlay for: ${objects.join(", ")}. (Continuous overlay mode in VR passthrough.)`;
          }
          return "[error]VR detection server not running (YOLO-World, port 5580).";
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
        "Enable live VR/stereo passthrough detection overlays (green boxes) directly inside the main vr_passthrough app. This toggles an in-app Coral/EdgeTPU overlay mode via /tmp/vr_detection_state.json (no separate detection_display app). Optionally enable segmentation for person silhouette masks. Kalman filtering provides temporal smoothing to reduce jitter.",
      parameters: {
        type: "object",
        properties: {
          objects: {
            type: "array",
            items: { type: "string" },
            description:
              "List of objects to detect and display (e.g., ['person', 'hand', 'cup'])",
          },
          confidence: {
            type: "number",
            description:
              "Detection confidence threshold 0.0-1.0 (higher = fewer false positives). Default 0.55.",
          },
          duration: {
            type: "number",
            description: "Duration in seconds (optional, default: until stopped)",
          },
          segmentation: {
            type: "boolean",
            description:
              "Enable semantic segmentation overlay (person silhouette mask). Requires EdgeTPU segmentation server to be running (ENABLE_SEGMENTATION_SERVER=1).",
          },
          smoothing: {
            type: "string",
            enum: ["none", "low", "medium", "high"],
            description:
              "Kalman filter smoothing level for detection boxes and masks. 'none'=raw, 'low'=responsive (default), 'medium'=balanced, 'high'=very smooth.",
          },
        },
        required: ["objects"],
      },
    },
    func: async (params) => {
      try {
        const { objects, duration, confidence, segmentation, smoothing } = params;

        if (!Array.isArray(objects) || objects.length === 0) {
          return "[error]Please specify at least one object to detect.";
        }

        // Toggle in-app overlay mode by writing the shared state file.
        // vr_passthrough.py watches this and draws green boxes in-headset.
        const fs = require("fs");
        const now = Date.now() / 1000;
        const stopAt =
          typeof duration === "number" && duration > 0 ? now + duration : undefined;
        const validSmoothing = ["none", "low", "medium", "high"].includes(smoothing) ? smoothing : "low";
        const state: any = {
          target_objects: objects,
          is_running: true,
          timestamp: now,
          confidence:
            typeof confidence === "number" && isFinite(confidence)
              ? Math.max(0, Math.min(1, confidence))
              : 0.55,
          segmentation: Boolean(segmentation),
          smoothing: validSmoothing,
        };
        if (stopAt) state.stop_at = stopAt;
        fs.writeFileSync("/tmp/vr_detection_state.json", JSON.stringify(state));

        const durationText = duration ? ` for ${duration} seconds` : "";
        const segText = segmentation ? " with segmentation" : "";
        const smoothText = validSmoothing !== "low" ? ` (smoothing: ${validSmoothing})` : "";
        return `[success]Enabled VR in-app detection overlay${segText}${durationText} for: ${objects.join(", ")}${smoothText}. Green boxes should appear inside the main VR passthrough. Say "stop VR detection" to turn it off.`;
      } catch (error: any) {
        return `[error]Failed to start: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "vrStartPersonSegmentation",
      description:
        "Start live person segmentation in VR passthrough. Shows a green silhouette overlay on detected people. Requires EdgeTPU segmentation server (ENABLE_SEGMENTATION_SERVER=1). Kalman filtering provides temporal smoothing for stable masks.",
      parameters: {
        type: "object",
        properties: {
          duration: {
            type: "number",
            description: "Duration in seconds (optional, default: until stopped)",
          },
          confidence: {
            type: "number",
            description: "Detection confidence threshold 0.0-1.0. Default 0.55.",
          },
          smoothing: {
            type: "string",
            enum: ["none", "low", "medium", "high"],
            description:
              "Kalman filter smoothing level for masks and boxes. Default: 'low' (responsive).",
          },
        },
      },
    },
    func: async (params) => {
      const duration = typeof params?.duration === "number" ? params.duration : undefined;
      const confidence = typeof params?.confidence === "number" ? params.confidence : 0.55;
      const smoothing = typeof params?.smoothing === "string" ? params.smoothing : "low";
      // Reuse vrStartLiveDetectionDisplay with segmentation enabled
      const tool = vrDetectionTools.find((t) => t.function.name === "vrStartLiveDetectionDisplay");
      if (!tool) return "[error]VR detection tool not available.";
      return await tool.func({ objects: ["person"], duration, confidence, segmentation: true, smoothing } as any);
    },
  },

  {
    type: "function",
    function: {
      name: "vrSetDetectionSensitivity",
      description:
        "Set the sensitivity (confidence threshold) for the in-headset VR detection overlay. Higher confidence = less sensitive (fewer boxes).",
      parameters: {
        type: "object",
        properties: {
          confidence: {
            type: "number",
            description: "Confidence threshold 0.0-1.0 (recommended 0.45-0.75).",
          },
        },
        required: ["confidence"],
      },
    },
    func: async (params) => {
      try {
        const fs = require("fs");
        const conf =
          typeof params?.confidence === "number" && isFinite(params.confidence)
            ? Math.max(0, Math.min(1, params.confidence))
            : null;
        if (conf === null) return "[error]Please provide a numeric confidence 0.0-1.0.";

        let state: any = {};
        try {
          state = JSON.parse(fs.readFileSync("/tmp/vr_detection_state.json", "utf-8"));
        } catch {
          state = { is_running: true, target_objects: ["person"] };
        }
        state.confidence = conf;
        state.timestamp = Date.now() / 1000;
        fs.writeFileSync("/tmp/vr_detection_state.json", JSON.stringify(state));
        return `[success]Set in-headset VR detection confidence to ${conf.toFixed(
          2
        )}. (Higher = less sensitive)`;
      } catch (error: any) {
        return `[error]Failed to set sensitivity: ${error.message}`;
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
        try {
          fs.writeFileSync("/tmp/vr_detection_state.json", JSON.stringify(state));
        } catch {
          // ignore
        }
        // Strong stop: remove the file so vr_passthrough disables immediately
        try {
          fs.unlinkSync("/tmp/vr_detection_state.json");
        } catch {
          // ignore
        }

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

  // ===================== CLASSIFICATION TOOLS =====================
  {
    type: "function",
    function: {
      name: "vrClassifyView",
      description:
        "Classify what's in the VR headset view using image classification. " +
        "Uses MobileNet V2 (ImageNet), Popular Products V1 (100k products), or iNaturalist (birds/insects/plants). " +
        "Takes a snapshot from VR stereo cameras and identifies objects.",
      parameters: {
        type: "object",
        properties: {
          model: {
            type: "string",
            enum: ["imagenet", "products", "bird", "insect", "plant"],
            description: "Model: 'imagenet' (general), 'products' (100k US), 'bird', 'insect', or 'plant' (iNaturalist). Default: imagenet",
          },
          topK: {
            type: "number",
            description: "Number of top predictions to return (1-20, default: 5)",
          },
          eye: {
            type: "string",
            enum: ["left", "right"],
            description: "Which eye camera to use (default: left)",
          },
        },
      },
    },
    func: async (params) => {
      try {
        // Determine model type
        const modelParam = String(params?.model || "imagenet").toLowerCase();
        let model = "imagenet";
        if (modelParam === "products") model = "products";
        else if (modelParam === "bird") model = "bird";
        else if (modelParam === "insect") model = "insect";
        else if (modelParam === "plant") model = "plant";
        
        const topK = typeof params?.topK === "number" ? Math.min(20, Math.max(1, params.topK)) : 5;
        const eye = params?.eye === "right" ? "right" : "left";
        
        // Classification ports
        const PORTS: Record<string, number> = {
          imagenet: 5594,
          products: 5595,
          bird: 5596,
          insect: 5597,
          plant: 5598,
        };
        const port = PORTS[model] || 5594;
        
        // First capture a frame from VR cameras
        const captureResponse = await sendCommand({
          cmd: "capture",
          eye,
          save: true
        });
        
        if (!captureResponse.success || !captureResponse.path) {
          // Fall back to direct camera capture
          const { execSync } = require("child_process");
          const tempPath = `/tmp/vr_classify_${Date.now()}.jpg`;
          try {
            execSync(`libcamera-still -o ${tempPath} -t 500 --width 640 --height 480 -n 2>/dev/null`, { timeout: 3000 });
          } catch {
            return "[error]Failed to capture image from cameras.";
          }
          
          if (!fs.existsSync(tempPath)) {
            return "[error]Failed to capture image.";
          }
          
          // Send to classification server
          const result = await classifyViaSocket(tempPath, port, topK, 0.05);
          try { fs.unlinkSync(tempPath); } catch {}
          
          if (!result.success) {
            return `[error]Classification failed: ${result.error}`;
          }
          
          return formatClassificationResult(result, model);
        }
        
        // Use captured VR frame
        const result = await classifyViaSocket(captureResponse.path, port, topK, 0.05);
        
        if (!result.success) {
          return `[error]Classification failed: ${result.error}`;
        }
        
        return formatClassificationResult(result, model);
      } catch (error: any) {
        return `[error]VR classification failed: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "vrStartClassificationOverlay",
      description:
        "Start live classification overlay in VR headset. Shows top predictions on screen continuously. " +
        "Choose: ImageNet (general), Products (100k US), or iNaturalist (birds/insects/plants).",
      parameters: {
        type: "object",
        properties: {
          model: {
            type: "string",
            enum: ["imagenet", "products", "bird", "insect", "plant"],
            description: "Model: 'imagenet', 'products', 'bird', 'insect', or 'plant'. Default: imagenet",
          },
          duration: {
            type: "number",
            description: "Duration in seconds (omit for continuous)",
          },
        },
      },
    },
    func: async (params) => {
      try {
        const modelParam = String(params?.model || "imagenet").toLowerCase();
        let model = "imagenet";
        if (modelParam === "products") model = "products";
        else if (modelParam === "bird") model = "bird";
        else if (modelParam === "insect") model = "insect";
        else if (modelParam === "plant") model = "plant";
        
        const duration = typeof params?.duration === "number" && params.duration > 0 ? params.duration : undefined;
        
        const now = Date.now() / 1000;
        const stopAt = duration ? now + duration : undefined;
        
        const state: any = {
          classification_mode: model,
          is_running: true,
          timestamp: now,
        };
        if (stopAt) state.stop_at = stopAt;
        
        fs.writeFileSync("/tmp/vr_classification_state.json", JSON.stringify(state));
        
        const modelNames: Record<string, string> = {
          imagenet: "MobileNet V2 (ImageNet 1000 classes)",
          products: "Popular Products V1 (100k US products)",
          bird: "iNaturalist Birds",
          insect: "iNaturalist Insects",
          plant: "iNaturalist Plants",
        };
        const modelName = modelNames[model] || model;
        const durationStr = duration ? ` for ${duration}s` : "";
        
        return `[success]Started VR classification overlay with ${modelName}${durationStr}. Top predictions will appear in headset.`;
      } catch (error: any) {
        return `[error]Failed to start classification overlay: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "vrStopClassificationOverlay",
      description: "Stop the VR classification overlay",
      parameters: {},
    },
    func: async () => {
      try {
        const state = {
          classification_mode: null,
          is_running: false,
          timestamp: Date.now() / 1000,
        };
        try {
          fs.writeFileSync("/tmp/vr_classification_state.json", JSON.stringify(state));
        } catch {}
        try {
          fs.unlinkSync("/tmp/vr_classification_state.json");
        } catch {}
        
        return "[success]VR classification overlay stopped.";
      } catch (error: any) {
        return `[error]Failed to stop classification overlay: ${error.message}`;
      }
    },
  },
];

// Helper function to classify via socket
async function classifyViaSocket(
  imagePath: string,
  port: number,
  topK: number,
  threshold: number
): Promise<any> {
  return new Promise((resolve) => {
    if (!fs.existsSync(imagePath)) {
      resolve({ success: false, error: `Image not found: ${imagePath}` });
      return;
    }

    const imageData = fs.readFileSync(imagePath);
    const client = new net.Socket();
    let buffer = Buffer.alloc(0);
    let resolved = false;

    const timeout = setTimeout(() => {
      if (!resolved) {
        resolved = true;
        client.destroy();
        resolve({ success: false, error: "Classification timeout" });
      }
    }, 10000);

    client.connect(port, "localhost", () => {
      // Binary request format: [4 bytes threshold][1 byte top_k][image bytes]
      const thresholdBuf = Buffer.alloc(4);
      thresholdBuf.writeFloatBE(threshold, 0);
      const topKBuf = Buffer.from([Math.min(20, Math.max(1, topK))]);
      
      const payload = Buffer.concat([thresholdBuf, topKBuf, imageData]);
      const lengthBuf = Buffer.alloc(4);
      lengthBuf.writeUInt32BE(payload.length, 0);
      
      client.write(lengthBuf);
      client.write(payload);
    });

    client.on("data", (data) => {
      buffer = Buffer.concat([buffer, data]);
      
      if (buffer.length >= 4) {
        const responseLength = buffer.readUInt32BE(0);
        if (buffer.length >= 4 + responseLength) {
          clearTimeout(timeout);
          try {
            const jsonStr = buffer.slice(4, 4 + responseLength).toString("utf-8");
            resolved = true;
            client.destroy();
            resolve(JSON.parse(jsonStr));
          } catch {
            resolved = true;
            client.destroy();
            resolve({ success: false, error: "Invalid response" });
          }
        }
      }
    });

    client.on("error", (err: any) => {
      clearTimeout(timeout);
      if (!resolved) {
        resolved = true;
        resolve({ success: false, error: err.message });
      }
    });

    client.on("close", () => {
      clearTimeout(timeout);
      if (!resolved) {
        resolved = true;
        resolve({ success: false, error: "Connection closed" });
      }
    });
  });
}

// Format classification result for display
function formatClassificationResult(result: any, model: string): string {
  const classifications = result.classifications || [];
  if (classifications.length === 0) {
    const hints: Record<string, string> = {
      bird: "Make sure a bird is clearly visible in frame.",
      insect: "Make sure an insect is clearly visible in frame.",
      plant: "Make sure a plant/flower/leaf is clearly visible in frame.",
      products: "Make sure a product is clearly visible in frame.",
      imagenet: "",
    };
    return `[success]No objects identified with sufficient confidence. ${hints[model] || ""}`;
  }

  const modelNames: Record<string, string> = {
    imagenet: "Object",
    products: "Product",
    bird: "Bird species",
    insect: "Insect species",
    plant: "Plant species",
  };
  const modelName = modelNames[model] || "Image";
  let response = `[success]${modelName} identified (${result.inference_time_ms || "?"}ms):\n`;
  
  for (const cls of classifications) {
    const confidence = (cls.confidence * 100).toFixed(1);
    response += `  - ${cls.class_name}: ${confidence}%\n`;
  }
  
  return response;
}

export default vrDetectionTools;

