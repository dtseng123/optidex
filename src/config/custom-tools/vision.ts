import { LLMTool } from "../../type";
import { exec } from "child_process";
import { promisify } from "util";
import path from "path";
import fs from "fs";
import axios from "axios";

const execAsync = promisify(exec);

// Check which LLM is active
const isOnline = () => {
  try {
    require('child_process').execSync("ping -c 1 -W 1 8.8.8.8", { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
};

const OLLAMA_ENDPOINT = process.env.OLLAMA_ENDPOINT || "http://localhost:11434";
// Default to moondream for low-RAM devices (8GB Pi5)
const OLLAMA_VISION_MODEL = process.env.OLLAMA_VISION_MODEL || "moondream";

// OpenAI vision analysis (GPT-4o supports vision natively)
async function analyzeImageWithOpenAI(imagePath: string, prompt: string): Promise<string> {
  try {
    const openai = require("../cloud-api/openai").openai;
    if (!openai) {
      return "[error]OpenAI not configured";
    }

    // Read image and convert to base64
    const imageBuffer = fs.readFileSync(imagePath);
    const base64Image = imageBuffer.toString('base64');
    const mimeType = imagePath.endsWith('.png') ? 'image/png' : 'image/jpeg';

    const response = await openai.chat.completions.create({
      model: "gpt-4o",
      messages: [
        {
          role: "user",
          content: [
            { type: "text", text: prompt },
            {
              type: "image_url",
              image_url: {
                url: `data:${mimeType};base64,${base64Image}`,
              },
            },
          ],
        },
      ],
      max_tokens: 500,
    });

    return response.choices[0].message.content || "[error]No response from OpenAI";
  } catch (error: any) {
    console.error("OpenAI vision error:", error);
    return `[error]Failed to analyze with OpenAI: ${error.message}`;
  }
}

// Ollama vision analysis (local vision model)
async function analyzeImageWithOllama(imagePath: string, prompt: string): Promise<string> {
  try {
    // Read image and convert to base64
    const imageBuffer = fs.readFileSync(imagePath);
    const base64Image = imageBuffer.toString('base64');

    console.log(`Analyzing image with Ollama ${OLLAMA_VISION_MODEL}...`);

    const response = await axios.post(
      `${OLLAMA_ENDPOINT}/api/generate`,
      {
        model: OLLAMA_VISION_MODEL,
        prompt: prompt,
        images: [base64Image],
        stream: false,
      },
      {
        headers: {
          "Content-Type": "application/json",
        },
        timeout: 60000, // 60 second timeout for vision models
      }
    );

    if (response.data && response.data.response) {
      return response.data.response;
    } else {
      return "[error]No response from Ollama vision model";
    }
  } catch (error: any) {
    console.error("Ollama vision error:", error);
    if (error.code === 'ECONNREFUSED') {
      return `[error]Ollama not running or vision model not available. Install with: ollama pull ${OLLAMA_VISION_MODEL}`;
    }
    return `[error]Failed to analyze with Ollama: ${error.message}`;
  }
}

const visionTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "analyzeImage",
      description: "Analyze a photo or image to describe what's in it, recognize objects, people, text, or answer questions about the image content",
      parameters: {
        type: "object",
        properties: {
          question: {
            type: "string",
            description: "What to analyze or ask about the image (e.g., 'What do you see?', 'What objects are in this picture?', 'Is there text in the image?')",
          },
        },
        required: ["question"],
      },
    },
    func: async (params) => {
      try {
        const { question } = params;

        // Find most recent photo (from camera or generated)
        const imageDir = path.join(__dirname, "../../../data/images");
        const files = fs
          .readdirSync(imageDir)
          .filter((f) => f.endsWith(".jpg") || f.endsWith(".png"))
          .map((f) => ({
            name: f,
            path: path.join(imageDir, f),
            time: fs.statSync(path.join(imageDir, f)).mtime.getTime(),
          }))
          .sort((a, b) => b.time - a.time);

        if (files.length === 0) {
          return "[error]No images found. Take a photo first.";
        }

        const latestImage = files[0].path;
        console.log(`Analyzing image: ${latestImage}`);

        // Use OpenAI if online, Ollama if offline
        let result: string;
        if (isOnline()) {
          console.log("Using OpenAI GPT-4o for vision analysis...");
          result = await analyzeImageWithOpenAI(latestImage, question);
        } else {
          console.log(`Using Ollama ${OLLAMA_VISION_MODEL} for vision analysis...`);
          result = await analyzeImageWithOllama(latestImage, question);
        }

        return `[success]${result}`;
      } catch (error: any) {
        console.error("Error analyzing image:", error);
        return `[error]Failed to analyze image: ${error.message}`;
      }
    },
  },

  {
    type: "function",
    function: {
      name: "analyzeVideoFrame",
      description: "Analyze a frame from the most recent video recording to describe what's in it",
      parameters: {
        type: "object",
        properties: {
          question: {
            type: "string",
            description: "What to analyze about the video content",
          },
        },
        required: ["question"],
      },
    },
    func: async (params) => {
      try {
        const { question } = params;

        // Find most recent video
        const videoDir = path.join(__dirname, "../../../data/videos");
        const files = fs
          .readdirSync(videoDir)
          .filter((f) => f.endsWith(".h264") || f.endsWith(".mp4"))
          .map((f) => ({
            name: f,
            path: path.join(videoDir, f),
            time: fs.statSync(path.join(videoDir, f)).mtime.getTime(),
          }))
          .sort((a, b) => b.time - a.time);

        if (files.length === 0) {
          return "[error]No videos found. Record a video first.";
        }

        const latestVideo = files[0].path;
        console.log(`Extracting frame from video: ${latestVideo}`);

        // Extract a middle frame from the video
        const frameOutput = `/tmp/video_analysis_frame.jpg`;
        const extractCmd = `ffmpeg -i ${latestVideo} -vf "select=eq(n\\,15)" -vframes 1 -y ${frameOutput}`;
        
        await execAsync(extractCmd);

        if (!fs.existsSync(frameOutput)) {
          return "[error]Failed to extract frame from video.";
        }

        // Analyze the extracted frame
        let result: string;
        if (isOnline()) {
          console.log("Using OpenAI GPT-4o for video frame analysis...");
          result = await analyzeImageWithOpenAI(frameOutput, question);
        } else {
          console.log(`Using Ollama ${OLLAMA_VISION_MODEL} for video frame analysis...`);
          result = await analyzeImageWithOllama(frameOutput, question);
        }

        // Clean up
        fs.unlinkSync(frameOutput);

        return `[success]${result}`;
      } catch (error: any) {
        console.error("Error analyzing video frame:", error);
        return `[error]Failed to analyze video: ${error.message}`;
      }
    },
  },
];

export default visionTools;

