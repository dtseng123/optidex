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
      description: "Start the Semantic Sentry mode to detect interaction between pairs of objects. You can specify multiple pairs. Triggers when any pair overlaps/interacts.",
      parameters: {
        type: "object",
        properties: {
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
            description: "List of object pairs to watch for interactions (e.g. [{'object1':'dog', 'object2':'couch'}, {'object1':'cat', 'object2':'bed'}])"
          },
        },
        required: ["pairs"],
      },
    },
    func: async (params) => {
      try {
        const { pairs } = params;

        if (!pairs || pairs.length === 0) {
            return "Please provide at least one pair of objects to watch.";
        }

        if (sentryProcess) {
          // Kill existing
           try {
            sentryProcess.kill();
           } catch(e) {}
           sentryProcess = null;
        }
        
        // Remove state file if exists
        if (fs.existsSync(STATE_FILE)) fs.unlinkSync(STATE_FILE);

        // Format args: "obj1,obj2" "obj3,obj4"
        const args = pairs.map((p: any) => `${p.object1},${p.object2}`);

        sentryProcess = spawn("python3", [SCRIPT_PATH, ...args]);
        
        console.log(`[SemanticSentry] Started for pairs: ${args.join(" | ")}`);
        
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

        return `Semantic Sentry started. I am watching for interactions between: ${args.join(", ")}.`;
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
