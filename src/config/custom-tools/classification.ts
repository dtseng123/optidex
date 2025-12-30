/**
 * Unified Image Classification Tools using TPU Service Manager
 * 
 * Uses a single manager that loads models on-demand and unloads after idle.
 * This prevents TPU overload from having multiple classification servers.
 * 
 * Models available:
 * - imagenet: 1,000 general objects (MobileNet V2)
 * - products: 100,000 US retail products
 * - bird: 965 bird species (iNaturalist)
 * - insect: 1,022 insect species (iNaturalist)
 * - plant: 2,102 plant species (iNaturalist)
 */

import { LLMTool } from "../../type";
import * as net from "net";
import * as fs from "fs";
import { exec } from "child_process";
import { promisify } from "util";
import * as path from "path";

const execAsync = promisify(exec);

const MANAGER_HOST = "localhost";
const MANAGER_PORT = 5600;
const TIMEOUT = 30000;

// Path to the Python camera capture script (same as camera.ts)
const CAMERA_SCRIPT = path.join(__dirname, "../../../python/camera_capture.py");

interface ClassificationResult {
  class_id: number;
  class_name: string;
  confidence: number;
}

interface ManagerResponse {
  success?: boolean;
  error?: string;
  model?: string;
  classifications?: ClassificationResult[];
  count?: number;
  inference_time_ms?: number;
  classification?: {
    loaded_model: string | null;
    description: string;
    idle_seconds: number | null;
    available_models: string[];
  };
  models?: Record<string, string>;
}

/**
 * Send command to TPU Manager
 */
async function sendManagerCommand(command: object): Promise<ManagerResponse> {
  return new Promise((resolve) => {
    const client = new net.Socket();
    let buffer = Buffer.alloc(0);
    let resolved = false;

    const timeout = setTimeout(() => {
      if (!resolved) {
        resolved = true;
        client.destroy();
        resolve({ success: false, error: "Connection timeout" });
      }
    }, TIMEOUT);

    client.connect(MANAGER_PORT, MANAGER_HOST, () => {
      const payload = Buffer.from(JSON.stringify(command), "utf-8");
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

/**
 * Check if TPU manager is running
 */
async function isManagerRunning(): Promise<boolean> {
  const result = await sendManagerCommand({ cmd: "ping" });
  return result.success === true;
}

/**
 * Capture a photo for classification using picamera2 (same method as camera.ts)
 */
async function capturePhoto(): Promise<string> {
  const outputPath = `/tmp/classification_capture_${Date.now()}.jpg`;
  
  try {
    // Use picamera2 via Python script (same as camera.ts)
    const command = `python3 ${CAMERA_SCRIPT} ${outputPath} 640 480`;
    
    const { stdout, stderr } = await execAsync(command, {
      timeout: 20000,
      maxBuffer: 10 * 1024 * 1024,
    });
    
    if (stdout) {
      console.log("[Classification] Camera output:", stdout);
    }
    if (stderr) {
      console.error("[Classification] Camera stderr:", stderr);
    }
    
    if (!fs.existsSync(outputPath)) {
      throw new Error("Camera capture produced no file");
    }
    
    return outputPath;
  } catch (error: any) {
    const msg = error?.message || String(error);
    if (msg.includes("Pipeline handler in use") || msg.includes("Device or resource busy")) {
      throw new Error("Camera is busy (another process is using it). Try again.");
    }
    if (msg.includes("timed out") || msg.includes("timeout")) {
      throw new Error("Camera capture timed out. Try again.");
    }
    throw new Error(`Camera capture failed: ${msg}`);
  }
}

/**
 * Classify with automatic model loading
 */
async function classifyWithModel(
  imagePath: string,
  model: string,
  topK: number = 5,
  threshold: number = 0.1
): Promise<ManagerResponse> {
  if (!fs.existsSync(imagePath)) {
    return { success: false, error: `Image not found: ${imagePath}` };
  }
  
  const imageData = fs.readFileSync(imagePath);
  const imageB64 = imageData.toString("base64");
  
  return sendManagerCommand({
    cmd: "classify",
    model,
    image_b64: imageB64,
    top_k: topK,
    threshold,
  });
}

/**
 * Format classification results
 */
function formatResults(result: ManagerResponse, modelName: string): string {
  if (!result.success) {
    return `[error]Classification failed: ${result.error}`;
  }
  
  const classifications = result.classifications || [];
  if (classifications.length === 0) {
    return `[success]No ${modelName} identified with sufficient confidence.`;
  }
  
  let response = `[success]${modelName} identified (${result.inference_time_ms || "?"}ms, model: ${result.model}):\n`;
  for (const cls of classifications) {
    response += `  - ${cls.class_name}: ${(cls.confidence * 100).toFixed(1)}%\n`;
  }
  
  return response;
}

const classificationUnifiedTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "identifyObject",
      description:
        "Identify objects in camera view using ImageNet model (1000 general categories). " +
        "Good for animals, vehicles, food, furniture, electronics, etc.",
      parameters: {
        type: "object",
        properties: {
          topK: {
            type: "number",
            description: "Number of top predictions (default: 5)",
          },
        },
      },
    },
    func: async (params) => {
      try {
        if (!(await isManagerRunning())) {
          return "[error]TPU Manager not running. Start it with: python3 /home/dash/coral-models/tpu_service_manager.py";
        }
        
        const topK = typeof params?.topK === "number" ? params.topK : 5;
        const imagePath = await capturePhoto();
        const result = await classifyWithModel(imagePath, "imagenet", topK, 0.1);
        
        try { fs.unlinkSync(imagePath); } catch {}
        
        return formatResults(result, "Object");
      } catch (error: any) {
        return `[error]Classification failed: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "identifyProduct",
      description:
        "PREFERRED for product identification. Uses EdgeTPU AI to identify retail products from 100,000 US products database. " +
        "Much faster than general image analysis for products. Use this instead of analyzeImage for retail products.",
      parameters: {
        type: "object",
        properties: {
          topK: {
            type: "number",
            description: "Number of top predictions (default: 5)",
          },
        },
      },
    },
    func: async (params) => {
      try {
        if (!(await isManagerRunning())) {
          return "[error]TPU Manager not running.";
        }
        
        const topK = typeof params?.topK === "number" ? params.topK : 5;
        const imagePath = await capturePhoto();
        const result = await classifyWithModel(imagePath, "products", topK, 0.1);
        
        try { fs.unlinkSync(imagePath); } catch {}
        
        return formatResults(result, "Product");
      } catch (error: any) {
        return `[error]Product identification failed: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "identifyBird",
      description:
        "PREFERRED for bird identification. Uses EdgeTPU AI to identify bird species from 965 known species (iNaturalist dataset). " +
        "Much faster and more accurate than general image analysis for birds. Use this instead of analyzeImage for birds.",
      parameters: {
        type: "object",
        properties: {
          topK: {
            type: "number",
            description: "Number of top predictions (default: 5)",
          },
        },
      },
    },
    func: async (params) => {
      try {
        if (!(await isManagerRunning())) {
          return "[error]TPU Manager not running.";
        }
        
        const topK = typeof params?.topK === "number" ? params.topK : 5;
        const imagePath = await capturePhoto();
        const result = await classifyWithModel(imagePath, "bird", topK, 0.05);
        
        try { fs.unlinkSync(imagePath); } catch {}
        
        return formatResults(result, "Bird species");
      } catch (error: any) {
        return `[error]Bird identification failed: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "identifyInsect",
      description:
        "PREFERRED for insect/bug identification. Uses EdgeTPU AI to identify insect species from 1,022 known species (iNaturalist dataset). " +
        "Much faster and more accurate than general image analysis for insects. Use this instead of analyzeImage for bugs/insects.",
      parameters: {
        type: "object",
        properties: {
          topK: {
            type: "number",
            description: "Number of top predictions (default: 5)",
          },
        },
      },
    },
    func: async (params) => {
      try {
        if (!(await isManagerRunning())) {
          return "[error]TPU Manager not running.";
        }
        
        const topK = typeof params?.topK === "number" ? params.topK : 5;
        const imagePath = await capturePhoto();
        const result = await classifyWithModel(imagePath, "insect", topK, 0.05);
        
        try { fs.unlinkSync(imagePath); } catch {}
        
        return formatResults(result, "Insect species");
      } catch (error: any) {
        return `[error]Insect identification failed: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "identifyPlant",
      description:
        "PREFERRED for plant/flower identification. Uses EdgeTPU AI to identify plant species from 2,102 known species (iNaturalist dataset). " +
        "Much faster and more accurate than general image analysis for plants. Use this instead of analyzeImage for plants/flowers.",
      parameters: {
        type: "object",
        properties: {
          topK: {
            type: "number",
            description: "Number of top predictions (default: 5)",
          },
        },
      },
    },
    func: async (params) => {
      try {
        if (!(await isManagerRunning())) {
          return "[error]TPU Manager not running.";
        }
        
        const topK = typeof params?.topK === "number" ? params.topK : 5;
        const imagePath = await capturePhoto();
        const result = await classifyWithModel(imagePath, "plant", topK, 0.05);
        
        try { fs.unlinkSync(imagePath); } catch {}
        
        return formatResults(result, "Plant species");
      } catch (error: any) {
        return `[error]Plant identification failed: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "classifyImage",
      description:
        "Classify an image with any model. Choose: imagenet, products, bird, insect, or plant.",
      parameters: {
        type: "object",
        properties: {
          model: {
            type: "string",
            enum: ["imagenet", "products", "bird", "insect", "plant"],
            description: "Classification model to use",
          },
          imagePath: {
            type: "string",
            description: "Optional: path to existing image file. If omitted, takes a photo.",
          },
          topK: {
            type: "number",
            description: "Number of top predictions (default: 5)",
          },
        },
        required: ["model"],
      },
    },
    func: async (params) => {
      try {
        if (!(await isManagerRunning())) {
          return "[error]TPU Manager not running.";
        }
        
        const model = params?.model || "imagenet";
        const topK = typeof params?.topK === "number" ? params.topK : 5;
        const threshold = ["bird", "insect", "plant"].includes(model) ? 0.05 : 0.1;
        
        let imagePath = params?.imagePath;
        let needsCleanup = false;
        
        if (!imagePath) {
          imagePath = await capturePhoto();
          needsCleanup = true;
        }
        
        if (!fs.existsSync(imagePath)) {
          return `[error]Image not found: ${imagePath}`;
        }
        
        const result = await classifyWithModel(imagePath, model, topK, threshold);
        
        if (needsCleanup) {
          try { fs.unlinkSync(imagePath); } catch {}
        }
        
        const modelNames: Record<string, string> = {
          imagenet: "Object",
          products: "Product",
          bird: "Bird species",
          insect: "Insect species",
          plant: "Plant species",
        };
        
        return formatResults(result, modelNames[model] || "Object");
      } catch (error: any) {
        return `[error]Classification failed: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "classificationStatus",
      description: "Check TPU Manager status, see which model is loaded and available models.",
      parameters: {},
    },
    func: async () => {
      try {
        const running = await isManagerRunning();
        if (!running) {
          return "[error]TPU Manager not running.\n\nTo start:\n  python3 /home/dash/coral-models/tpu_service_manager.py";
        }
        
        const status = await sendManagerCommand({ cmd: "status" });
        const models = await sendManagerCommand({ cmd: "list_models" });
        
        let response = "[success]TPU Manager Status:\n";
        
        if (status.classification) {
          const cls = status.classification;
          response += `  Currently loaded: ${cls.loaded_model || "None"}\n`;
          if (cls.loaded_model) {
            response += `  Description: ${cls.description}\n`;
            response += `  Idle: ${cls.idle_seconds}s (unloads after 300s)\n`;
          }
        }
        
        response += "\n  Available models:\n";
        if (models.models) {
          for (const [name, desc] of Object.entries(models.models)) {
            response += `    - ${name}: ${desc}\n`;
          }
        }
        
        return response;
      } catch (error: any) {
        return `[error]Failed to get status: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "preloadClassificationModel",
      description: "Pre-load a classification model for faster first inference.",
      parameters: {
        type: "object",
        properties: {
          model: {
            type: "string",
            enum: ["imagenet", "products", "bird", "insect", "plant"],
            description: "Model to pre-load",
          },
        },
        required: ["model"],
      },
    },
    func: async (params) => {
      try {
        if (!(await isManagerRunning())) {
          return "[error]TPU Manager not running.";
        }
        
        const model = params?.model || "imagenet";
        const result = await sendManagerCommand({ cmd: "load", model });
        
        if (result.success) {
          return `[success]Pre-loaded ${model} model. Ready for fast classification.`;
        } else {
          return `[error]Failed to load ${model}: ${result.error}`;
        }
      } catch (error: any) {
        return `[error]Failed to preload: ${error.message}`;
      }
    },
  },
];

export default classificationUnifiedTools;

