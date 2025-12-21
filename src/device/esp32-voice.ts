import { spawn } from "child_process";
import path from "path";

export interface Esp32VoiceEventUtterance {
  event: "utterance";
  session_id: number;
  path: string;
  reason: number;
  duration_ms: number;
  bytes: number;
}

type Esp32VoiceEvent =
  | { event: "status"; status: string; [k: string]: any }
  | { event: "start"; session_id: number; sample_rate: number; channels: number; frame_samples: number }
  | Esp32VoiceEventUtterance;

export interface Esp32VoiceGateway {
  stop: () => void;
}

export function startEsp32VoiceGateway(
  onUtterance: (evt: Esp32VoiceEventUtterance) => void,
  opts?: {
    deviceName?: string;
    outDir?: string;
  }
): Esp32VoiceGateway {
  const deviceName = opts?.deviceName || process.env.ESP32_VOICE_BLE_NAME || "optidex-voice";
  const outDir = opts?.outDir || process.env.ESP32_VOICE_OUT_DIR || "/home/dash/optidex/data/recordings";
  const pythonExe =
    process.env.ESP32_VOICE_PYTHON ||
    "/home/dash/optidex/python/.venv/bin/python";

  const scriptPath = path.join(__dirname, "../../python/ble_voice_receiver.py");
  const child = spawn(pythonExe, [scriptPath, deviceName, outDir], {
    stdio: ["ignore", "pipe", "pipe"],
  });

  let buf = "";
  child.stdout.setEncoding("utf8");
  child.stdout.on("data", (chunk: string) => {
    buf += chunk;
    while (true) {
      const idx = buf.indexOf("\n");
      if (idx < 0) break;
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (!line) continue;
      try {
        const evt = JSON.parse(line) as Esp32VoiceEvent;
        if (evt.event === "utterance") {
          onUtterance(evt);
        } else {
          // keep status logs concise
          if (evt.event === "status") {
            console.log(`[ESP32Voice] ${evt.status}`);
          }
        }
      } catch (e) {
        console.warn("[ESP32Voice] Bad JSON from receiver:", line);
      }
    }
  });

  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk: string) => {
    const msg = chunk.trim();
    if (msg) console.error("[ESP32Voice:stderr]", msg);
  });

  child.on("exit", (code) => {
    console.warn(`[ESP32Voice] receiver exited: ${code}`);
  });

  return {
    stop: () => {
      try {
        child.kill("SIGTERM");
      } catch {}
    },
  };
}


