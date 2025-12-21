import { LLMTool } from "../../type";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";
import { telegramBot } from "../../utils/telegram";
import { ttsProcessor } from "../../cloud-api/server";
import { setPendingVisualMode } from "../../utils/image";

const SCRIPT_PATH = path.join(__dirname, "../../../python/semantic_sentry.py");
const STATE_FILE = "/tmp/sentry_state.json";
const FRAME_OUTPUT = "/tmp/whisplay_sentry_frame.jpg";

let sentryProcess: any = null;

const semanticSentryTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "startSemanticSentry",
      description: "Start Semantic Sentry mode with live video display. Detects interactions between objects (e.g., 'dog on couch', 'person near door'). Shows camera feed on screen with detection boxes. Alerts when objects interact. Can record the session.",
      parameters: {
        type: "object",
        properties: {
          objects: {
            type: "array",
            items: { type: "string" },
            description: "List of objects to monitor for interactions (e.g., ['dog', 'couch'] to detect dog on couch)"
          },
          allCombinations: {
            type: "boolean",
            description: "If true, check ALL pairwise combinations of objects. If false, provide explicit pairs."
          },
          pairs: {
            type: "array",
            items: {
              type: "object",
              properties: {
                object1: { type: "string", description: "First object" },
                object2: { type: "string", description: "Second object" }
              },
              required: ["object1", "object2"]
            },
            description: "Explicit object pairs to watch for interaction"
          },
          record: {
            type: "boolean",
            description: "Whether to record video while monitoring (default: false)"
          }
        },
      },
    },
    func: async (params) => {
      try {
        const { objects, allCombinations, pairs, record } = params;

        // Kill any existing sentry
        if (sentryProcess) {
          try {
            sentryProcess.kill();
          } catch(e) {}
          sentryProcess = null;
        }
        
        if (fs.existsSync(STATE_FILE)) fs.unlinkSync(STATE_FILE);

        let pairsList: string[] = [];
        let description = "";
        let neededObjects: string[] = [];

        if (objects && allCombinations) {
          if (!objects || objects.length < 2) {
            return "Please provide at least 2 objects for all-combinations mode.";
          }
          pairsList = ["--all-combinations", ...objects];
          description = `all combinations of: ${objects.join(", ")}`;
          neededObjects = objects;
        } else if (pairs && pairs.length > 0) {
          pairsList = pairs.map((p: any) => `${p.object1},${p.object2}`);
          description = pairsList.join(", ");
          neededObjects = [...new Set(pairs.flatMap((p: any) => [p.object1, p.object2]))] as string[];
        } else if (objects && objects.length >= 2) {
          // Default to all combinations if just objects provided
          pairsList = ["--all-combinations", ...objects];
          description = `all combinations of: ${objects.join(", ")}`;
          neededObjects = objects;
        } else {
          return "Please provide at least 2 objects to watch for interactions.";
        }

        console.log(`[SemanticSentry] Starting for: ${description}`);
        console.log(`[SemanticSentry] Record: ${record}`);

        // Set pending visual mode
        setPendingVisualMode({
          type: 'detection',
          framePath: FRAME_OUTPUT,
          detectionScript: SCRIPT_PATH,
          targetObjects: neededObjects,
          sentryPairs: pairsList,
          sentryRecord: record,
        } as any);

        const recordText = record ? " I'll also record a video." : "";
        return `[success]Starting Semantic Sentry. Watching for interactions between ${description}.${recordText} You'll see the live camera feed on the display.`;
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
      let interactions = 0;
      
      if (fs.existsSync(STATE_FILE)) {
        try {
          const state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
          interactions = state.interactions || 0;
        } catch(e) {}
        fs.unlinkSync(STATE_FILE);
      }
      
      if (sentryProcess) {
        sentryProcess.kill();
        sentryProcess = null;
      }
      
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      if (fs.existsSync(FRAME_OUTPUT)) {
        try { fs.unlinkSync(FRAME_OUTPUT); } catch(e) {}
      }
      
      if (interactions > 0) {
        return `Semantic Sentry stopped. Detected ${interactions} interaction(s).`;
      }
      return "Semantic Sentry stopped.";
    }
  }
];

export default semanticSentryTools;
export { sentryProcess, SCRIPT_PATH, STATE_FILE, FRAME_OUTPUT };
