import { LLMTool } from "../../type";
import { exec, spawn, ChildProcess } from "child_process";
import { promisify } from "util";
import path from "path";

const execAsync = promisify(exec);
const SCRIPT_PATH = path.join(__dirname, "../../../python/meshtastic_client.py");

// Global state for monitor process
let monitorProcess: ChildProcess | null = null;
let monitorCallback: ((msg: any) => void) | null = null;
let isManualStop = false; // Flag to prevent auto-restart when we intentionally stop it

export const stopMeshtasticMonitor = async () => {
  if (monitorProcess) {
    isManualStop = true; // Mark as intentional
    console.log("[Meshtastic] Stopping monitor to release port...");
    
    const killPromise = new Promise<void>((resolve) => {
        if (!monitorProcess) return resolve();
        if (monitorProcess.killed || monitorProcess.exitCode !== null) return resolve();
        
        monitorProcess.once('exit', () => resolve());
        try {
          monitorProcess.kill('SIGTERM');
          setTimeout(() => {
            if (monitorProcess && !monitorProcess.killed) {
              try { monitorProcess.kill('SIGKILL'); } catch(e){}
            }
          }, 2000);
        } catch(e) {
          resolve();
        }
    });

    try {
        await killPromise;
        console.log("[Meshtastic] Monitor process exited.");
    } catch(e) {
        console.error("Error waiting for monitor exit:", e);
    }
    monitorProcess = null;
  }
};

export const startMeshtasticMonitor = (onMessage?: (msg: any) => void) => {
  if (onMessage) {
    monitorCallback = onMessage;
  }
  
  if (monitorProcess) return; // Already running

  isManualStop = false; // Reset flag
  console.log(`[Meshtastic] Starting monitor...`);
  monitorProcess = spawn("python3", [SCRIPT_PATH, "monitor"]);
  
  monitorProcess.stdout?.on("data", (data: Buffer) => {
    const line = data.toString().trim();
    if (line.includes("JSON_MSG:")) {
        const jsonStr = line.split("JSON_MSG:")[1];
        try {
            const msg = JSON.parse(jsonStr);
            if (monitorCallback) monitorCallback(msg);
        } catch (e) {
            console.error("Error parsing Meshtastic message:", e);
        }
    }
  });
  
  monitorProcess.stderr?.on("data", (data: Buffer) => {
      const msg = data.toString().trim();
      if (msg && !msg.includes("Listening")) {
         // console.log(`[Meshtastic Monitor Log]: ${msg}`);
      }
  });

  monitorProcess.on("exit", (code) => {
      console.log(`[Meshtastic] Monitor exited (code ${code})`);
      monitorProcess = null;
      
      // Auto-restart if not manually stopped and exited with error
      if (!isManualStop && code !== 0) {
          console.log("[Meshtastic] Monitor crashed or lost connection. Retrying in 5 seconds...");
          setTimeout(() => {
              startMeshtasticMonitor();
          }, 5000);
      }
  });
};

// Helper to run a command exclusively (stops monitor temporarily)
async function runExclusiveCommand(command: string): Promise<string> {
    const wasRunning = !!monitorProcess;
    // Even if not currently running, we should make sure it's stopped (e.g. pending restart)
    // stopping it sets isManualStop=true, preventing the auto-restart from firing while we work
    await stopMeshtasticMonitor();
    
    // Give a brief moment for OS to release port handle fully
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    try {
        console.log(`[Meshtastic] Running exclusive command: ${command}`);
        const { stdout } = await execAsync(command);
        return stdout;
    } finally {
        // Restart only if it was running or if we want it to always run
        // For now, restart if it was running, OR if we have a callback registered (implies it should be running)
        if (wasRunning || monitorCallback) {
            setTimeout(() => startMeshtasticMonitor(), 2000);
        }
    }
}

const meshtasticTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "listMeshtasticNodes",
      description: "List all nodes currently visible on the Meshtastic mesh network. Returns names, battery levels, and signal strength.",
      parameters: {},
    },
    func: async () => {
      try {
        const stdout = await runExclusiveCommand(`python3 ${SCRIPT_PATH} nodes`);
        try {
          const nodes = JSON.parse(stdout);
          if (nodes.length === 0) {
            return "No nodes found in the mesh (or device is still initializing).";
          }
          
          return nodes.map((n: any) => {
            const timeAgo = n.lastHeard ? Math.round((Date.now()/1000 - n.lastHeard)/60) + "m ago" : "Never";
            return `- ${n.longName} (${n.shortName}): SNR ${n.snr}, Bat ${n.batteryLevel}%, Last Heard ${timeAgo}`;
          }).join("\n");
          
        } catch (e) {
          return `Error parsing node list: ${stdout}`;
        }
      } catch (error: any) {
        return `Error listing nodes: ${error.message}. Make sure device is connected via USB.`;
      }
    },
  },
  {
    type: "function",
    function: {
      name: "sendMeshtasticMessage",
      description: "Send a text message to the Meshtastic mesh network. Can broadcast to all or send to a specific node.",
      parameters: {
        type: "object",
        properties: {
          message: {
            type: "string",
            description: "The text message to send",
          },
          destination: {
            type: "string",
            description: "Optional: Short name or Long name of the destination node. Defaults to '^all' (broadcast).",
          },
        },
        required: ["message"],
      },
    },
    func: async (params) => {
      try {
        const { message, destination } = params;
        const destArg = destination ? `--dest "${destination}"` : "";
        const safeMessage = message.replace(/"/g, '\\"');
        
        await runExclusiveCommand(`python3 ${SCRIPT_PATH} send "${safeMessage}" ${destArg}`);
        return `Message sent to ${destination || "Broadcast"}: "${message}"`;
      } catch (error: any) {
        return `Error sending message: ${error.message}`;
      }
    },
  },
  {
    type: "function",
    function: {
      name: "readMeshtasticMessages",
      description: "Listen for new Meshtastic messages for a short period (10 seconds). Note: This only catches new messages arriving right now.",
      parameters: {
        type: "object",
        properties: {
          timeout: {
            type: "number",
            description: "How many seconds to listen (default 10)",
          },
        },
        required: [],
      },
    },
    func: async (params) => {
      try {
        const timeout = params.timeout || 10;
        const stdout = await runExclusiveCommand(`python3 ${SCRIPT_PATH} read --timeout ${timeout}`);
        
        try {
          const messages = JSON.parse(stdout);
          if (messages.length === 0) {
            return "No new messages received during the listening period.";
          }
          
          return messages.map((m: any) => {
            return `[${m.from}]: ${m.text}`;
          }).join("\n");
          
        } catch (e) {
          return `Error parsing messages: ${stdout}`;
        }
      } catch (error: any) {
        return `Error reading messages: ${error.message}`;
      }
    },
  },
];

export default meshtasticTools;
