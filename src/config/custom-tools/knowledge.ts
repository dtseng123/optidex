/**
 * Knowledge Base Tool
 * 
 * Allows Jarvis to query the local Wikipedia/Wikidata knowledge base
 * for factual information without needing internet access.
 */

import { LLMTool } from "../../type";
import { exec } from "child_process";
import { promisify } from "util";
import path from "path";

const execAsync = promisify(exec);

const KNOWLEDGE_SCRIPT = path.join(__dirname, "../../../python/knowledge_base.py");

const knowledgeTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "searchKnowledge",
      description: "Search the local Wikipedia knowledge base for information about a topic. Use this for factual questions about people, places, things, concepts, history, science, etc. Works offline.",
      parameters: {
        type: "object",
        properties: {
          query: {
            type: "string",
            description: "The topic or question to search for (e.g., 'Albert Einstein', 'photosynthesis', 'World War 2')"
          },
          limit: {
            type: "number",
            description: "Maximum number of results to return (default: 3)"
          }
        },
        required: ["query"]
      }
    },
    func: async (params) => {
      try {
        const { query, limit } = params;
        const maxResults = limit || 3;
        
        console.log(`[Knowledge] Searching for: ${query}`);
        
        const command = `python3 ${KNOWLEDGE_SCRIPT} search "${query.replace(/"/g, '\\"')}" --limit ${maxResults} --json`;
        
        const { stdout, stderr } = await execAsync(command, { 
          timeout: 30000,
          maxBuffer: 1024 * 1024
        });
        
        if (stderr) {
          console.log("[Knowledge] Stderr:", stderr);
        }
        
        try {
          const results = JSON.parse(stdout);
          
          if (!results || results.length === 0) {
            return `No information found for "${query}" in the knowledge base.`;
          }
          
          let response = `Knowledge Base Results for "${query}":\n\n`;
          
          for (const result of results) {
            response += `**${result.title}**\n`;
            // Truncate content to reasonable length
            const content = result.content || result.text || "";
            const truncated = content.length > 500 ? content.substring(0, 500) + "..." : content;
            response += `${truncated}\n\n`;
          }
          
          return response;
          
        } catch (parseError) {
          // If not JSON, return raw output
          return stdout || `No results found for "${query}".`;
        }
        
      } catch (error: any) {
        console.error("[Knowledge] Search error:", error);
        
        if (error.message.includes("No such file")) {
          return "[error]Knowledge base not initialized. Run 'jarvis knowledge download' first.";
        }
        
        return `[error]Knowledge search failed: ${error.message}`;
      }
    }
  },
  
  {
    type: "function",
    function: {
      name: "getArticle",
      description: "Get a specific Wikipedia article by its exact title. Use when you know the exact article name.",
      parameters: {
        type: "object",
        properties: {
          title: {
            type: "string",
            description: "The exact title of the Wikipedia article"
          }
        },
        required: ["title"]
      }
    },
    func: async (params) => {
      try {
        const { title } = params;
        
        console.log(`[Knowledge] Getting article: ${title}`);
        
        const command = `python3 ${KNOWLEDGE_SCRIPT} get "${title.replace(/"/g, '\\"')}" --json`;
        
        const { stdout } = await execAsync(command, { 
          timeout: 15000,
          maxBuffer: 2 * 1024 * 1024
        });
        
        try {
          const article = JSON.parse(stdout);
          
          if (!article || article.error) {
            return `Article "${title}" not found in the knowledge base.`;
          }
          
          let response = `**${article.title}**\n\n`;
          
          // Truncate long articles
          const content = article.content || article.text || "";
          const truncated = content.length > 2000 ? content.substring(0, 2000) + "\n\n[Article truncated - " + content.length + " characters total]" : content;
          
          response += truncated;
          
          return response;
          
        } catch (parseError) {
          return stdout || `Article "${title}" not found.`;
        }
        
      } catch (error: any) {
        console.error("[Knowledge] Get article error:", error);
        return `[error]Failed to get article: ${error.message}`;
      }
    }
  },
  
  {
    type: "function",
    function: {
      name: "knowledgeStats",
      description: "Get statistics about the local knowledge base - how many articles, entities, etc.",
      parameters: {}
    },
    func: async () => {
      try {
        const command = `python3 ${KNOWLEDGE_SCRIPT} stats --json`;
        
        const { stdout } = await execAsync(command, { timeout: 10000 });
        
        try {
          const stats = JSON.parse(stdout);
          
          let response = "Knowledge Base Statistics:\n";
          response += `- Articles: ${stats.articles?.toLocaleString() || 'N/A'}\n`;
          response += `- Entities: ${stats.entities?.toLocaleString() || 'N/A'}\n`;
          response += `- Database Size: ${stats.size || 'N/A'}\n`;
          
          if (stats.last_updated) {
            response += `- Last Updated: ${stats.last_updated}\n`;
          }
          
          return response;
          
        } catch (parseError) {
          return stdout || "Knowledge base statistics unavailable.";
        }
        
      } catch (error: any) {
        console.error("[Knowledge] Stats error:", error);
        return `[error]Failed to get knowledge base stats: ${error.message}`;
      }
    }
  }
];

export default knowledgeTools;

