/**
 * Memory Display Tool
 * 
 * Allows Jarvis to display a visualization of its memory/knowledge graph
 * on the Whisplay screen.
 */

import { LLMTool } from "../../type";
import { exec } from "child_process";
import { promisify } from "util";
import path from "path";
import fs from "fs";
import { setLatestGenImg } from "../../utils/image";

const execAsync = promisify(exec);

const MEMORY_DISPLAY_SCRIPT = path.join(__dirname, "../../../python/memory_display.py");
const OUTPUT_PATH = "/tmp/jarvis_memory_display.png";

const memoryDisplayTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "displayMemory",
      description: "Display a visualization of Jarvis's memory and knowledge graph on the screen. Shows stats (nodes, edges, episodes, missions), recent activity, and optionally a mini graph visualization.",
      parameters: {
        type: "object",
        properties: {
          detail: {
            type: "string",
            enum: ["summary", "graph"],
            description: "Detail level: 'summary' shows stats and recent activity, 'graph' adds a mini knowledge graph visualization"
          }
        }
      }
    },
    func: async (params) => {
      try {
        const detail = params?.detail || "graph";
        
        console.log(`[MemoryDisplay] Generating visualization (detail: ${detail})...`);
        
        // Generate the visualization
        const command = `python3 ${MEMORY_DISPLAY_SCRIPT} --detail ${detail} --output ${OUTPUT_PATH}`;
        
        const { stdout, stderr } = await execAsync(command, {
          timeout: 15000,
          env: { ...process.env, PYTHONUNBUFFERED: "1" }
        });
        
        if (stdout) console.log("[MemoryDisplay] Output:", stdout);
        if (stderr) console.log("[MemoryDisplay] Stderr:", stderr);
        
        // Check if the image was generated
        if (!fs.existsSync(OUTPUT_PATH)) {
          return "[error]Failed to generate memory visualization.";
        }
        
        // Display the image on the Whisplay screen
        setLatestGenImg(OUTPUT_PATH);
        
        console.log(`[MemoryDisplay] Displaying: ${OUTPUT_PATH}`);
        
        return "[success]Memory visualization displayed on screen. It shows your knowledge graph stats, recent episodes, and node connections.";
        
      } catch (error: any) {
        console.error("[MemoryDisplay] Error:", error);
        return `[error]Failed to display memory: ${error.message}`;
      }
    }
  },
  {
    type: "function",
    function: {
      name: "getMemoryStats",
      description: "Get statistics about Jarvis's memory without displaying visualization. Returns counts of nodes, edges, episodes, and missions.",
      parameters: {}
    },
    func: async () => {
      try {
        // Run Python to get stats as JSON
        const command = `python3 -c "
import sys
sys.path.insert(0, '/home/dash/optidex/python')
from memory import get_memory
import json
m = get_memory()
stats = m.get_stats()
print(json.dumps(stats))
"`;
        
        const { stdout } = await execAsync(command, { timeout: 10000 });
        const stats = JSON.parse(stdout.trim());
        
        const total_nodes = stats.total_nodes || stats.entities || 0;
        const total_edges = stats.total_edges || stats.relationships || 0;
        const episodes = stats.episodes || 0;
        const missions = stats.active_missions || 0;
        
        return `Memory Stats:
- Nodes: ${total_nodes}
- Edges/Links: ${total_edges}
- Episodes: ${episodes}
- Active Missions: ${missions}`;
        
      } catch (error: any) {
        console.error("[MemoryDisplay] Stats error:", error);
        return `[error]Failed to get memory stats: ${error.message}`;
      }
    }
  }
];

export default memoryDisplayTools;

