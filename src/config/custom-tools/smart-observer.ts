import { LLMTool } from "../../type";
import path from "path";
import fs from "fs";
import { telegramBot } from "../../utils/telegram";
import { gemini, geminiModel } from "../../cloud-api/gemini";

const OBSERVER_SCRIPT = path.join(__dirname, "../../../python/smart_observer.py");
const TRIGGER_FILE = "/tmp/whisplay_trigger_event.json";

const smartObserverTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "startSmartObserver",
      description: "Monitor for a specific object. When found, take a photo, describe it using AI, and send a notification to Telegram. Useful for 'Tell me who comes to my desk' or 'Let me know when the package arrives'.",
      parameters: {
        type: "object",
        properties: {
          objects: {
            type: "array",
            items: { type: "string" },
            description: "Objects to watch for (e.g., 'person', 'cat', 'bottle')"
          },
          prompt: {
            type: "string",
            description: "Question to ask the AI about the object when found (e.g., 'Describe this person', 'Is this package damaged?')"
          }
        },
        required: ["objects", "prompt"],
      },
    },
    func: async (params) => {
      const { objects, prompt } = params;
      
      if (!objects || objects.length === 0) return "[error] No objects specified";

      console.log(`[SmartObserver] Starting watch for: ${objects.join(", ")}`);
      
      // Run python script in background
      const { spawn } = require("child_process");
      const process = spawn("python3", [OBSERVER_SCRIPT, ...objects]);
      
      // Handle output
      let triggered = false;
      
      process.stdout.on("data", async (data: Buffer) => {
        const line = data.toString().trim();
        console.log(`[Observer]: ${line}`);
        
        if (line.includes("JSON_TRIGGER:") && !triggered) {
            triggered = true;
            const jsonStr = line.split("JSON_TRIGGER:")[1];
            try {
                const event = JSON.parse(jsonStr);
                console.log("[SmartObserver] Trigger received!", event);
                
                telegramBot.sendMessage(`👀 Smart Observer: Detected ${event.objects.join(", ")}! Analyzing...`);
                
                // Send photo to Telegram immediately
                await telegramBot.sendPhoto(event.image_path);
                
                // Send to VLM for analysis
                if (gemini) {
                    try {
                        const imageBuffer = fs.readFileSync(event.image_path);
                        const imageBase64 = imageBuffer.toString("base64");
                        
                        // For single turn generation with image:
                        const response = await gemini.models.generateContent({
                            model: geminiModel,
                            contents: [
                                {
                                    role: 'user',
                                    parts: [
                                        { text: prompt },
                                        {
                                            inlineData: {
                                                data: imageBase64,
                                                mimeType: "image/jpeg"
                                            }
                                        }
                                    ]
                                }
                            ]
                        });
                        
                        // Access text property safely (SDK 1.x)
                        let analysis = "No analysis generated.";
                        
                        if (response && response.candidates && response.candidates[0]) {
                             const parts = response.candidates[0].content?.parts;
                             if (parts && parts[0] && parts[0].text) {
                                 analysis = parts[0].text;
                             }
                        }
                        telegramBot.sendMessage(`🧠 Analysis: ${analysis}`);
                        
                    } catch (err: any) {
                        console.error("Gemini Error:", err);
                        telegramBot.sendMessage(`Error analyzing image: ${err.message}`);
                    }
                }
                
            } catch (e) {
                console.error("Error parsing trigger:", e);
            }
        }
      });

      return `[success] Smart Observer started. I am watching for ${objects.join(", ")}. I will notify you on Telegram when I see one.`;
    }
  }
];

export default smartObserverTools;
