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

const cameraTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "takePicture",
      description: "Take a picture using the camera and display it on the screen",
      parameters: {},
    },
    func: async (params) => {
      try {
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

        const { stdout, stderr } = await execAsync(command);
        
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
        return `[success]Picture taken and saved.`;
      } catch (error: any) {
        console.error("Error taking picture:", error);
        return `[error]Failed to take picture: ${error.message}`;
      }
    },
  },
];

export default cameraTools;

