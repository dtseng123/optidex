import { LLMTool } from "../../type";
import { exec } from "child_process";
import { promisify } from "util";
import path from "path";
import fs from "fs";
import { telegramBot } from "../../utils/telegram";
import { ttsProcessor } from "../../cloud-api/server";
import { gemini, geminiModel } from "../../cloud-api/gemini";

const SCRIPT_PATH = path.join(__dirname, "../../../python/object_search.py");
const STATE_FILE = "/tmp/search_state.json";

let searchProcess: any = null;

const findObjectTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "findObject",
      description: "Search for a specific object using the camera. It scans for a broad object category first, then uses AI to confirm if it matches your specific description. Example: to find a 'blue wallet', use broadClass='handbag' (or similar) and description='blue wallet'.",
      parameters: {
        type: "object",
        properties: {
          description: {
            type: "string",
            description: "Detailed description of the object you are looking for (e.g., 'my blue wallet', 'a red coffee mug')",
          },
          broadClass: {
            type: "string",
            description: "The YOLO object class to scan for. Must be one of: person, bicycle, car, motorcycle, backpack, umbrella, handbag, tie, suitcase, bottle, cup, fork, knife, spoon, bowl, chair, couch, bed, dining table, toilet, tv, laptop, mouse, remote, keyboard, cell phone, microwave, oven, toaster, sink, refrigerator, book, clock, vase, scissors, teddy bear, hair drier, toothbrush. Choose the closest match (e.g. 'handbag' for wallet, 'cup' for mug, 'bottle' for flask).",
          },
        },
        required: ["description", "broadClass"],
      },
    },
    func: async (params) => {
      try {
        const { description, broadClass } = params;

        if (searchProcess) {
           try {
            searchProcess.kill();
           } catch(e) {}
           searchProcess = null;
        }
        
        if (fs.existsSync(STATE_FILE)) fs.unlinkSync(STATE_FILE);

        const { spawn } = require("child_process");
        searchProcess = spawn("python3", [SCRIPT_PATH, broadClass]);
        
        console.log(`[FindObject] Started search for '${broadClass}' to find '${description}'`);
        
        // Notify user
        await ttsProcessor(`Okay, I'm looking for your ${description}. I'll let you know if I see it.`);
        
        searchProcess.stdout.on("data", async (data: Buffer) => {
            const line = data.toString().trim();
            if (line.includes("JSON_CANDIDATE:")) {
                try {
                    const jsonStr = line.split("JSON_CANDIDATE:")[1];
                    const candidate = JSON.parse(jsonStr);
                    
                    console.log(`[FindObject] Candidate found (${candidate.confidence}): ${candidate.image_path}`);
                    
                    // Verify with VLM
                    if (gemini) {
                        try {
                            const imageBuffer = fs.readFileSync(candidate.image_path);
                            const imageBase64 = imageBuffer.toString("base64");
                            
                            const response = await gemini.models.generateContent({
                                model: geminiModel,
                                contents: [
                                    {
                                        role: 'user',
                                        parts: [
                                            { text: `Does this image show ${description}? Answer with exactly 'YES' or 'NO' followed by a short explanation.` },
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
                            
                            let analysis = "";
                            if (response && response.candidates && response.candidates[0]) {
                                const parts = response.candidates[0].content?.parts;
                                if (parts && parts[0] && parts[0].text) {
                                    analysis = parts[0].text;
                                }
                            }
                            
                            console.log(`[FindObject] VLM Analysis: ${analysis}`);
                            
                            if (analysis.trim().toUpperCase().startsWith("YES")) {
                                console.log(`[FindObject] MATCH CONFIRMED!`);
                                
                                const successMsg = `I found it! Here is your ${description}.`;
                                await ttsProcessor(successMsg);
                                telegramBot.sendMessage(successMsg);
                                telegramBot.sendPhoto(candidate.image_path);
                                telegramBot.sendMessage(`Analysis: ${analysis}`);
                                
                                // Stop searching
                                if (searchProcess) {
                                    searchProcess.kill();
                                    searchProcess = null;
                                    if (fs.existsSync(STATE_FILE)) fs.unlinkSync(STATE_FILE);
                                }
                            } else {
                                console.log(`[FindObject] Match rejected.`);
                            }
                            
                        } catch (err) {
                            console.error("VLM Error:", err);
                        }
                    }
                    
                } catch (e) {
                    console.error("Error parsing candidate:", e);
                }
            }
        });

        return `Search started for ${description}. I am scanning for ${broadClass} candidates.`;
      } catch (error: any) {
        return `Error starting search: ${error.message}`;
      }
    },
  },
  {
      type: "function",
      function: {
          name: "stopFindObject",
          description: "Stop the current object search.",
          parameters: {},
      },
      func: async () => {
          if (searchProcess) {
              searchProcess.kill();
              searchProcess = null;
              if (fs.existsSync(STATE_FILE)) fs.unlinkSync(STATE_FILE);
              return "Search stopped.";
          } else {
              return "No search was running.";
          }
      }
  }
];

export default findObjectTools;

