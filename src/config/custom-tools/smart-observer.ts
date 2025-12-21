import { LLMTool } from "../../type";
import path from "path";
import fs from "fs";
import { telegramBot } from "../../utils/telegram";
import { gemini, geminiModel } from "../../cloud-api/gemini";
import { setPendingVisualMode } from "../../utils/image";
import { ttsProcessor } from "../../cloud-api/server";

const OBSERVER_SCRIPT = path.join(__dirname, "../../../python/smart_observer.py");
const STATE_FILE = "/tmp/observer_state.json";
const FRAME_OUTPUT = "/tmp/whisplay_observer_frame.jpg";

let observerProcess: any = null;

const smartObserverTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "startSmartObserver",
      description: "Monitor for specific objects with live video display. Shows camera feed on screen with detection boxes. When target object is found, takes a photo, analyzes it with AI, and sends notification to Telegram. Can also record the monitoring session.",
      parameters: {
        type: "object",
        properties: {
          objects: {
            type: "array",
            items: { type: "string" },
            description: "Objects to watch for (e.g., 'person', 'cat', 'bottle', 'package')"
          },
          prompt: {
            type: "string",
            description: "Question to ask the AI about the object when found (e.g., 'Describe this person', 'Is this package damaged?')"
          },
          record: {
            type: "boolean",
            description: "Whether to record video while monitoring (default: false)"
          },
          continuous: {
            type: "boolean",
            description: "Continue watching and saving clips after detections instead of stopping (default: true for monitoring)"
          }
        },
        required: ["objects", "prompt"],
      },
    },
    func: async (params) => {
      const { objects, prompt, record, continuous } = params;
      
      if (!objects || objects.length === 0) return "[error] No objects specified";

      // Kill any existing observer
      if (observerProcess) {
        try {
          observerProcess.kill();
        } catch(e) {}
        observerProcess = null;
      }
      
      // Remove state file if exists
      if (fs.existsSync(STATE_FILE)) fs.unlinkSync(STATE_FILE);

      console.log(`[SmartObserver] Starting watch for: ${objects.join(", ")}`);
      console.log(`[SmartObserver] Record: ${record}, Continuous: ${continuous}`);

      // Set pending visual mode for live display
      setPendingVisualMode({
        type: 'detection',
        framePath: FRAME_OUTPUT,
        detectionScript: OBSERVER_SCRIPT,
        targetObjects: objects,
        // Store extra params for ChatFlow
        observerPrompt: prompt,
        observerRecord: record,
        observerContinuous: continuous,
      } as any);

      const recordText = record ? " I'll also record a video." : "";
      const modeText = continuous ? " I'll keep watching even after finding something." : "";
      return `[success]Starting Smart Observer. Watching for ${objects.join(", ")}.${recordText}${modeText} You'll see the live camera feed on the display.`;
    }
  },
  {
    type: "function",
    function: {
      name: "stopSmartObserver",
      description: "Stop the Smart Observer monitoring.",
      parameters: {},
    },
    func: async () => {
      let detections = 0;
      
      if (fs.existsSync(STATE_FILE)) {
        try {
          const state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
          detections = state.detections || 0;
        } catch(e) {}
        fs.unlinkSync(STATE_FILE);
      }
      
      if (observerProcess) {
        observerProcess.kill();
        observerProcess = null;
      }
      
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      if (fs.existsSync(FRAME_OUTPUT)) {
        try { fs.unlinkSync(FRAME_OUTPUT); } catch(e) {}
      }
      
      if (detections > 0) {
        return `Smart Observer stopped. Detected ${detections} time(s).`;
      }
      return "Smart Observer stopped.";
    }
  }
];

export default smartObserverTools;
export { observerProcess, OBSERVER_SCRIPT, STATE_FILE, FRAME_OUTPUT };
