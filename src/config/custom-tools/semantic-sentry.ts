import { LLMTool } from "../../type";
import { exec, spawn } from "child_process";
import { promisify } from "util";
import path from "path";
import fs from "fs";
import { telegramBot } from "../../utils/telegram";
import { ttsProcessor } from "../../cloud-api/server";

const execAsync = promisify(exec);
const SCRIPT_PATH = path.join(__dirname, "../../../python/semantic_sentry.py");
const STATE_FILE = "/tmp/sentry_state.json";

let sentryProcess: any = null;

const semanticSentryTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "startSemanticSentry",
      description: "Start the Semantic Sentry mode to detect interaction between objects. Use 'allCombinations' mode to check ALL pairwise interactions between multiple objects (e.g., 'dog, cat, couch' checks dog-cat, dog-couch, cat-couch), or specify explicit pairs.",
      parameters: {
        type: "object",
        properties: {
          objects: {
            type: "array",
            items: { type: "string" },
            description: "List of objects to monitor. If allCombinations=true, all pairs will be checked. Otherwise treated as explicit pairs."
          },
          allCombinations: {
            type: "boolean",
            description: "If true, check ALL pairwise combinations of the objects list (e.g., for 'dog, cat, couch' it checks dog-cat, dog-couch, cat-couch). If false, you must provide pairs explicitly."
          },
          pairs: {
            type: "array",
            items: {
                type: "object",
                properties: {
                    object1: { type: "string", description: "First object (e.g. dog)" },
                    object2: { type: "string", description: "Second object (e.g. couch)" }
                },
                required: ["object1", "object2"]
            },
            description: "List of explicit object pairs to watch (use this OR objects+allCombinations, not both)"
          },
        },
      },
    },
    func: async (params) => {
      try {
        const { objects, allCombinations, pairs } = params;

        if (sentryProcess) {
          // Kill existing
           try {
            sentryProcess.kill();
           } catch(e) {}
           sentryProcess = null;
        }
        
        // Remove state file if exists
        if (fs.existsSync(STATE_FILE)) fs.unlinkSync(STATE_FILE);

        let args: string[] = [];
        let description = "";

        if (objects && allCombinations) {
          // Mode 1: All combinations
          if (!objects || objects.length < 2) {
            return "Please provide at least 2 objects for all-combinations mode.";
          }
          
          args = ["--all-combinations", ...objects];
          description = `all combinations of: ${objects.join(", ")}`;
          
          console.log(`[SemanticSentry] Starting all-combinations mode for: ${objects.join(", ")}`);
        } else if (pairs && pairs.length > 0) {
          // Mode 2: Explicit pairs (backward compatible)
          args = pairs.map((p: any) => `${p.object1},${p.object2}`);
          description = args.join(", ");
          
          console.log(`[SemanticSentry] Starting explicit pairs mode: ${args.join(" | ")}`);
        } else if (objects && objects.length > 0) {
          // Mode 3: Objects provided but allCombinations not set - use as explicit pairs format
          return "Please set allCombinations=true to check all pairs, or use the 'pairs' parameter for explicit pairs.";
        } else {
          return "Please provide either 'objects' with 'allCombinations=true', or explicit 'pairs'.";
        }

        sentryProcess = spawn("python3", [SCRIPT_PATH, ...args]);
        
        sentryProcess.stdout.on("data", async (data: Buffer) => {
            const line = data.toString().trim();
            if (line.includes("JSON_TRIGGER:")) {
                try {
                    const jsonStr = line.split("JSON_TRIGGER:")[1];
                    const event = JSON.parse(jsonStr);
                    
                    console.log(`[SemanticSentry] Triggered:`, event);
                    
                    const message = `⚠️ Alert: I detected interaction between ${event.object1} and ${event.object2}!`;
                    
                    // 1. Speak alert
                    await ttsProcessor(message);
                    
                    // 2. Send to Telegram
                    telegramBot.sendMessage(message);
                    if (event.image_path && fs.existsSync(event.image_path)) {
                        telegramBot.sendPhoto(event.image_path);
                    }
                    
                } catch (e) {
                    console.error("Error parsing sentry trigger:", e);
                }
            }
        });

        sentryProcess.stderr.on("data", (data: Buffer) => {
           // Log only real messages to avoid clutter
           const msg = data.toString().trim();
           if (msg.startsWith("Starting") || msg.startsWith("Interaction")) {
               console.log(`[Sentry Log]: ${msg}`);
           }
        });

        return `Semantic Sentry started. I am watching for interactions between ${description}.`;
      } catch (error: any) {
        return `Error starting Semantic Sentry: ${error.message}`;
      }
    },
  },
  {
      type: "function",
      function: {
          name: "stopSemanticSentry",
          description: "Stop the currently running Semantic Sentry detection.",
          parameters: {},
      },
      func: async () => {
          if (sentryProcess) {
              sentryProcess.kill();
              sentryProcess = null;
              if (fs.existsSync(STATE_FILE)) fs.unlinkSync(STATE_FILE);
              return "Semantic Sentry stopped.";
          } else {
              return "Semantic Sentry was not running.";
          }
      }
  }
];

export default semanticSentryTools;
