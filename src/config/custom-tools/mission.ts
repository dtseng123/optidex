/**
 * Mission Management Tool
 * 
 * Allows Jarvis to create and manage missions - goal-focused surveillance,
 * reminders, monitoring tasks, and searches.
 */

import { LLMTool } from "../../type";
import { exec } from "child_process";
import { promisify } from "util";
import path from "path";

const execAsync = promisify(exec);

const PYTHON_DIR = path.join(__dirname, "../../../python");

async function runMemoryCommand(pythonCode: string): Promise<string> {
  const command = `python3 -c "
import sys
sys.path.insert(0, '${PYTHON_DIR}')
${pythonCode}
"`;
  const { stdout } = await execAsync(command, { timeout: 15000 });
  return stdout.trim();
}

const missionTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "createMission",
      description: "Create a new mission for Jarvis to track. Missions can be surveillance tasks (watch for something), reminders, monitoring tasks, or searches. Jarvis will work towards completing the mission.",
      parameters: {
        type: "object",
        properties: {
          objective: {
            type: "string",
            description: "What the mission should accomplish (e.g., 'Alert me when a package arrives', 'Watch for the dog getting on the couch', 'Remind me to take medication at 3pm')"
          },
          missionType: {
            type: "string",
            enum: ["surveillance", "reminder", "search", "monitor"],
            description: "Type of mission: surveillance (watch for something), reminder (time-based alert), search (find something), monitor (ongoing observation)"
          },
          priority: {
            type: "string",
            enum: ["low", "normal", "high", "critical"],
            description: "Priority level of the mission"
          },
          targetEntities: {
            type: "array",
            items: { type: "string" },
            description: "Objects or entities to watch for (e.g., ['package', 'person'], ['dog', 'couch'])"
          }
        },
        required: ["objective", "missionType"]
      }
    },
    func: async (params) => {
      try {
        const { objective, missionType, priority, targetEntities } = params;
        
        const targetsJson = JSON.stringify(targetEntities || []);
        const result = await runMemoryCommand(`
from memory import get_memory
import json

memory = get_memory()
mission = memory.create_mission(
    objective="${objective.replace(/"/g, '\\"')}",
    mission_type="${missionType}",
    priority="${priority || 'normal'}",
    target_entities=${targetsJson}
)
print(json.dumps({
    'id': mission.id,
    'objective': mission.objective,
    'type': mission.mission_type,
    'priority': mission.priority
}))
`);
        
        const mission = JSON.parse(result);
        console.log(`[Mission] Created: ${mission.id} - ${mission.objective}`);
        
        return `[success]Mission created: "${mission.objective}" (${mission.type}, ${mission.priority} priority). I will actively work on this.`;
        
      } catch (error: any) {
        console.error("[Mission] Create error:", error);
        return `[error]Failed to create mission: ${error.message}`;
      }
    }
  },
  
  {
    type: "function",
    function: {
      name: "listMissions",
      description: "List all active missions that Jarvis is currently working on",
      parameters: {}
    },
    func: async () => {
      try {
        const result = await runMemoryCommand(`
from memory import get_memory
import json

memory = get_memory()
missions = memory.get_active_missions()
output = []
for m in missions:
    output.append({
        'id': m.id,
        'objective': m.objective,
        'type': m.mission_type,
        'priority': m.priority,
        'status': m.status
    })
print(json.dumps(output))
`);
        
        const missions = JSON.parse(result);
        
        if (missions.length === 0) {
          return "No active missions. You can create one by telling me what to watch for or remind you about.";
        }
        
        let response = `Active Missions (${missions.length}):\n`;
        for (const m of missions) {
          const priorityIcon = m.priority === 'critical' ? '🔴' : 
                               m.priority === 'high' ? '🟠' : 
                               m.priority === 'normal' ? '🟢' : '⚪';
          response += `${priorityIcon} [${m.type}] ${m.objective}\n`;
        }
        
        return response;
        
      } catch (error: any) {
        console.error("[Mission] List error:", error);
        return `[error]Failed to list missions: ${error.message}`;
      }
    }
  },
  
  {
    type: "function",
    function: {
      name: "completeMission",
      description: "Mark a mission as completed. Use when the user says a mission is done or no longer needed.",
      parameters: {
        type: "object",
        properties: {
          objective: {
            type: "string",
            description: "The objective text of the mission to complete (partial match OK)"
          }
        },
        required: ["objective"]
      }
    },
    func: async (params) => {
      try {
        const { objective } = params;
        
        const result = await runMemoryCommand(`
from memory import get_memory
import json

memory = get_memory()
missions = memory.get_active_missions()

# Find matching mission
search = "${objective.replace(/"/g, '\\"').toLowerCase()}"
matched = None
for m in missions:
    if search in m.objective.lower():
        matched = m
        break

if matched:
    memory.complete_mission(matched.id, {'completed_by': 'user_request'})
    print(json.dumps({'success': True, 'objective': matched.objective}))
else:
    print(json.dumps({'success': False, 'error': 'No matching mission found'}))
`);
        
        const response = JSON.parse(result);
        
        if (response.success) {
          return `[success]Mission completed: "${response.objective}"`;
        } else {
          return `[error]Could not find a mission matching "${objective}". Use listMissions to see active missions.`;
        }
        
      } catch (error: any) {
        console.error("[Mission] Complete error:", error);
        return `[error]Failed to complete mission: ${error.message}`;
      }
    }
  },
  
  {
    type: "function",
    function: {
      name: "cancelMission",
      description: "Cancel an active mission. Use when the user no longer wants Jarvis to work on something.",
      parameters: {
        type: "object",
        properties: {
          objective: {
            type: "string",
            description: "The objective text of the mission to cancel (partial match OK)"
          }
        },
        required: ["objective"]
      }
    },
    func: async (params) => {
      try {
        const { objective } = params;
        
        const result = await runMemoryCommand(`
from memory import get_memory
import json

memory = get_memory()
missions = memory.get_active_missions()

search = "${objective.replace(/"/g, '\\"').toLowerCase()}"
matched = None
for m in missions:
    if search in m.objective.lower():
        matched = m
        break

if matched:
    # Update status in graph
    if memory.graph.has_node(matched.id):
        memory.graph.nodes[matched.id]['status'] = 'cancelled'
        memory._save_graph()
    print(json.dumps({'success': True, 'objective': matched.objective}))
else:
    print(json.dumps({'success': False}))
`);
        
        const response = JSON.parse(result);
        
        if (response.success) {
          return `[success]Mission cancelled: "${response.objective}"`;
        } else {
          return `[error]Could not find a mission matching "${objective}".`;
        }
        
      } catch (error: any) {
        console.error("[Mission] Cancel error:", error);
        return `[error]Failed to cancel mission: ${error.message}`;
      }
    }
  }
];

export default missionTools;

