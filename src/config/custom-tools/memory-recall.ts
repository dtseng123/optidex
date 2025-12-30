/**
 * Memory Recall Tool
 * 
 * Allows Jarvis to recall memories (episodes) by date, time, or content.
 * Enables queries like "what happened yesterday at 3pm?" or "when did you last see a dog?"
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
  const { stdout } = await execAsync(command, { timeout: 30000 });
  return stdout.trim();
}

const memoryRecallTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "recallMemory",
      description: "Recall memories from a specific date, time range, or search for specific content. Use this when the user asks 'what happened on...', 'what did you see...', 'when did...', etc.",
      parameters: {
        type: "object",
        properties: {
          date: {
            type: "string",
            description: "Date to search (formats: 'today', 'yesterday', '2024-12-28', 'December 28')"
          },
          startTime: {
            type: "string",
            description: "Start time for the search (format: 'HH:MM' or '3pm', '15:00')"
          },
          endTime: {
            type: "string",
            description: "End time for the search (format: 'HH:MM' or '5pm', '17:00')"
          },
          searchTerm: {
            type: "string",
            description: "Search term to find in episode summaries or transcriptions"
          },
          episodeType: {
            type: "string",
            enum: ["observation", "conversation", "audio", "all"],
            description: "Type of memory to search for"
          },
          limit: {
            type: "number",
            description: "Maximum number of results (default: 10)"
          }
        }
      }
    },
    func: async (params) => {
      try {
        const { date, startTime, endTime, searchTerm, episodeType, limit } = params;
        const maxResults = limit || 10;
        
        console.log(`[Recall] Searching: date=${date}, time=${startTime}-${endTime}, term=${searchTerm}`);
        
        const result = await runMemoryCommand(`
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

EPISODES_DIR = Path(os.path.expanduser("~/optidex/data/memory/episodes"))

def parse_date(date_str):
    if not date_str:
        return None
    date_str = date_str.lower().strip()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    if date_str == 'today':
        return today
    elif date_str == 'yesterday':
        return today - timedelta(days=1)
    elif date_str == 'this week':
        return today - timedelta(days=today.weekday())
    else:
        # Try parsing various formats
        for fmt in ['%Y-%m-%d', '%B %d', '%b %d', '%m/%d/%Y', '%m/%d']:
            try:
                parsed = datetime.strptime(date_str, fmt)
                if parsed.year == 1900:
                    parsed = parsed.replace(year=today.year)
                return parsed
            except:
                continue
    return None

def parse_time(time_str):
    if not time_str:
        return None
    time_str = time_str.lower().strip()
    
    # Handle am/pm format
    if 'am' in time_str or 'pm' in time_str:
        time_str = time_str.replace('am', ' am').replace('pm', ' pm').strip()
        for fmt in ['%I %p', '%I:%M %p', '%I%p', '%I:%M%p']:
            try:
                return datetime.strptime(time_str, fmt).time()
            except:
                continue
    
    # Handle 24h format
    for fmt in ['%H:%M', '%H:%M:%S', '%H']:
        try:
            return datetime.strptime(time_str, fmt).time()
        except:
            continue
    return None

# Parse parameters
target_date = parse_date("${date || ''}")
start_time = parse_time("${startTime || ''}")
end_time = parse_time("${endTime || ''}")
search_term = "${(searchTerm || '').replace(/"/g, '\\"').toLowerCase()}"
episode_type_filter = "${episodeType || 'all'}"
max_results = ${maxResults}

# Build time range
start_ts = None
end_ts = None

if target_date:
    if start_time:
        start_dt = datetime.combine(target_date.date(), start_time)
        start_ts = start_dt.timestamp()
    else:
        start_ts = target_date.timestamp()
    
    if end_time:
        end_dt = datetime.combine(target_date.date(), end_time)
        end_ts = end_dt.timestamp()
    else:
        # Default to end of day
        end_ts = (target_date + timedelta(days=1)).timestamp()

# Search episodes
results = []
for ep_file in sorted(EPISODES_DIR.glob("ep_*.json"), reverse=True):
    if len(results) >= max_results * 2:  # Get extra for filtering
        break
    try:
        with open(ep_file, 'r') as f:
            ep = json.load(f)
        
        ts = ep.get('timestamp', 0)
        
        # Filter by time range
        if start_ts and ts < start_ts:
            continue
        if end_ts and ts > end_ts:
            continue
        
        # Filter by type
        if episode_type_filter != 'all' and ep.get('episode_type') != episode_type_filter:
            continue
        
        # Filter by search term
        if search_term:
            searchable = (ep.get('summary', '') + ' ' + ep.get('transcription', '') + ' ' + ' '.join(ep.get('detected_objects', []))).lower()
            if search_term not in searchable:
                continue
        
        results.append(ep)
        
    except Exception as e:
        continue

# Sort by timestamp descending and limit
results = sorted(results, key=lambda x: x.get('timestamp', 0), reverse=True)[:max_results]

# Format output
output = []
for ep in results:
    dt = datetime.fromtimestamp(ep.get('timestamp', 0))
    output.append({
        'id': ep.get('id'),
        'datetime': dt.strftime('%Y-%m-%d %H:%M'),
        'type': ep.get('episode_type'),
        'summary': ep.get('summary', '')[:200],
        'objects': ep.get('detected_objects', []),
        'transcription': (ep.get('transcription') or '')[:100] if ep.get('transcription') else None
    })

print(json.dumps({'count': len(output), 'episodes': output}))
`);
        
        const data = JSON.parse(result);
        
        if (data.count === 0) {
          let noResultMsg = "No memories found";
          if (date) noResultMsg += ` for ${date}`;
          if (startTime) noResultMsg += ` around ${startTime}`;
          if (searchTerm) noResultMsg += ` matching "${searchTerm}"`;
          return noResultMsg + ".";
        }
        
        let response = `Found ${data.count} memory/memories:\n\n`;
        
        for (const ep of data.episodes) {
          response += `**${ep.datetime}** [${ep.type}]\n`;
          response += `${ep.summary}\n`;
          if (ep.objects && ep.objects.length > 0) {
            response += `Objects: ${ep.objects.join(', ')}\n`;
          }
          if (ep.transcription) {
            response += `Audio: "${ep.transcription}..."\n`;
          }
          response += '\n';
        }
        
        return response;
        
      } catch (error: any) {
        console.error("[Recall] Error:", error);
        return `[error]Failed to recall memories: ${error.message}`;
      }
    }
  },
  
  {
    type: "function",
    function: {
      name: "findObject",
      description: "Search memories for when a specific object was last seen. Use when user asks 'when did you last see...', 'have you seen my...'",
      parameters: {
        type: "object",
        properties: {
          object: {
            type: "string",
            description: "The object to search for in memories (e.g., 'keys', 'dog', 'person', 'package')"
          },
          limit: {
            type: "number",
            description: "Maximum number of sightings to return (default: 5)"
          }
        },
        required: ["object"]
      }
    },
    func: async (params) => {
      try {
        const { object, limit } = params;
        const maxResults = limit || 5;
        
        console.log(`[Recall] Finding object: ${object}`);
        
        const result = await runMemoryCommand(`
import json
import os
from datetime import datetime
from pathlib import Path

EPISODES_DIR = Path(os.path.expanduser("~/optidex/data/memory/episodes"))

search_obj = "${object.replace(/"/g, '\\"').toLowerCase()}"
max_results = ${maxResults}

results = []
for ep_file in sorted(EPISODES_DIR.glob("ep_*.json"), reverse=True):
    if len(results) >= max_results:
        break
    try:
        with open(ep_file, 'r') as f:
            ep = json.load(f)
        
        # Check detected objects
        objects = [o.lower() for o in ep.get('detected_objects', [])]
        summary = ep.get('summary', '').lower()
        
        if search_obj in objects or search_obj in summary:
            dt = datetime.fromtimestamp(ep.get('timestamp', 0))
            results.append({
                'datetime': dt.strftime('%Y-%m-%d %H:%M'),
                'summary': ep.get('summary', '')[:150],
                'objects': ep.get('detected_objects', [])
            })
    except:
        continue

print(json.dumps({'count': len(results), 'sightings': results}))
`);
        
        const data = JSON.parse(result);
        
        if (data.count === 0) {
          return `I don't have any memories of seeing "${object}".`;
        }
        
        let response = `Found ${data.count} sighting(s) of "${object}":\n\n`;
        
        for (const sighting of data.sightings) {
          response += `**${sighting.datetime}**\n`;
          response += `${sighting.summary}\n\n`;
        }
        
        return response;
        
      } catch (error: any) {
        console.error("[Recall] Find object error:", error);
        return `[error]Failed to search for object: ${error.message}`;
      }
    }
  },
  
  {
    type: "function",
    function: {
      name: "getRecentActivity",
      description: "Get recent activity/observations from Jarvis's memory. Use for questions like 'what have you been doing?', 'what's been happening?'",
      parameters: {
        type: "object",
        properties: {
          hours: {
            type: "number",
            description: "How many hours back to look (default: 24)"
          },
          limit: {
            type: "number",
            description: "Maximum number of activities to return (default: 10)"
          }
        }
      }
    },
    func: async (params) => {
      try {
        const { hours, limit } = params;
        const lookbackHours = hours || 24;
        const maxResults = limit || 10;
        
        const result = await runMemoryCommand(`
import json
import os
import time
from datetime import datetime
from pathlib import Path

EPISODES_DIR = Path(os.path.expanduser("~/optidex/data/memory/episodes"))

cutoff_ts = time.time() - (${lookbackHours} * 3600)
max_results = ${maxResults}

results = []
for ep_file in sorted(EPISODES_DIR.glob("ep_*.json"), reverse=True):
    if len(results) >= max_results:
        break
    try:
        with open(ep_file, 'r') as f:
            ep = json.load(f)
        
        ts = ep.get('timestamp', 0)
        if ts < cutoff_ts:
            continue
        
        dt = datetime.fromtimestamp(ts)
        results.append({
            'time': dt.strftime('%H:%M'),
            'date': dt.strftime('%Y-%m-%d'),
            'type': ep.get('episode_type'),
            'summary': ep.get('summary', '')[:100]
        })
    except:
        continue

print(json.dumps({'count': len(results), 'activities': results}))
`);
        
        const data = JSON.parse(result);
        
        if (data.count === 0) {
          return `No activity recorded in the last ${lookbackHours} hours.`;
        }
        
        let response = `Recent Activity (last ${lookbackHours}h):\n\n`;
        
        let currentDate = '';
        for (const activity of data.activities) {
          if (activity.date !== currentDate) {
            currentDate = activity.date;
            response += `**${currentDate}**\n`;
          }
          response += `  ${activity.time} - ${activity.summary}\n`;
        }
        
        return response;
        
      } catch (error: any) {
        console.error("[Recall] Recent activity error:", error);
        return `[error]Failed to get recent activity: ${error.message}`;
      }
    }
  }
];

export default memoryRecallTools;

