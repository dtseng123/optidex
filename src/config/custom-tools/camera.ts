import { LLMTool } from "../../type";
import { exec } from "child_process";
import { promisify } from "util";
import path from "path";
import { imageDir } from "../../utils/dir";
import { setLatestGenImg } from "../../utils/image";
import { telegramBot } from "../../utils/telegram";
import fs from "fs";
import { stopPoseAndReleaseCamera } from "./pose-estimation";

const execAsync = promisify(exec);

// Path to the Python camera capture script
const CAMERA_SCRIPT = path.join(__dirname, "../../../python/camera_capture.py");

// Serialize camera usage: libcamera/Picamera2 is not robust to concurrent opens,
// and can also conflict with OpenCV-based vision tools.
let cameraQueue: Promise<unknown> = Promise.resolve();
async function withCameraLock<T>(fn: () => Promise<T>): Promise<T> {
  const run = cameraQueue.then(fn, fn);
  cameraQueue = run.then(
    () => undefined,
    () => undefined
  );
  return run;
}

async function logThrottlingTag(tag: string) {
  try {
    const { stdout } = await execAsync("vcgencmd get_throttled");
    console.log(`[Camera][${tag}] vcgencmd get_throttled: ${stdout.trim()}`);
  } catch {
    // ignore if not available
  }
}

const cameraTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "takePicture",
      description: "Take a picture using the camera and display it on the screen",
      parameters: {},
    },
    func: async (params) => {
      return await withCameraLock(async () => {
      try {
          await logThrottlingTag("before");
        // Stop pose detection if running to release the camera
        const wasRunning = await stopPoseAndReleaseCamera();
        if (wasRunning) {
          console.log("Stopped pose detection to use camera");
        }

        const fileName = `camera-${Date.now()}.jpg`;
        const imagePath = path.join(imageDir, fileName);

        console.log(`Taking picture and saving to: ${imagePath}`);

        // Use picamera2 via Python script to take a picture
        const command = `python3 ${CAMERA_SCRIPT} ${imagePath} 1024 1024`;

          const { stdout, stderr } = await execAsync(command, {
            timeout: 20000,
            maxBuffer: 10 * 1024 * 1024,
          });
        
        if (stdout) {
          console.log("Camera output:", stdout);
        }
        if (stderr) {
          console.error("Camera stderr:", stderr);
        }

        // Verify the file was created
        if (!fs.existsSync(imagePath)) {
          console.error("Picture file was not created");
          return "[error]Failed to take picture. Camera may not be connected.";
        }

        // Set this as the latest generated image so it will be displayed
        setLatestGenImg(imagePath);

        // Send to Telegram
        telegramBot.sendPhoto(imagePath);

        console.log(`Picture saved successfully: ${imagePath}`);
          await logThrottlingTag("after");
        return `[success]Picture taken and saved.`;
      } catch (error: any) {
          const message = error?.message || String(error);
        console.error("Error taking picture:", error);
          if (
            message.includes("Pipeline handler in use by another process") ||
            message.includes("Device or resource busy")
          ) {
            return `[error]Camera is busy (another process is using libcamera). Stop other vision modes and try again.`;
          }
          if (message.includes("timed out") || message.includes("ETIMEDOUT")) {
            return `[error]Camera capture timed out. The camera may be wedged; try again after a few seconds.`;
          }
          return `[error]Failed to take picture: ${message}`;
      }
      });
    },
  },
];

export default cameraTools;

