import { LLMTool } from "../../type";
import axios from "axios";

const SERPER_API_KEY = process.env.SERPER_API_KEY;

interface SerperResult {
  title: string;
  link: string;
  snippet: string;
}

interface SerperResponse {
  organic?: SerperResult[];
  answerBox?: {
    title?: string;
    answer?: string;
    snippet?: string;
  };
  knowledgeGraph?: {
    title?: string;
    description?: string;
  };
}

const webSearchTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "searchWeb",
      description: "Search the web for current information. Use this when you need up-to-date information, news, weather, facts, or anything you don't know or are unsure about.",
      parameters: {
        type: "object",
        properties: {
          query: {
            type: "string",
            description: "The search query"
          }
        },
        required: ["query"]
      }
    },
    func: async (params) => {
      const { query } = params;

      if (!query) {
        return "[error] No search query provided";
      }

      if (!SERPER_API_KEY) {
        return "[error] Web search not configured - SERPER_API_KEY not set";
      }

      try {
        console.log(`[WebSearch] Searching for: ${query}`);

        const response = await axios.post<SerperResponse>(
          "https://google.serper.dev/search",
          { q: query, num: 5 },
          {
            headers: {
              "X-API-KEY": SERPER_API_KEY,
              "Content-Type": "application/json"
            },
            timeout: 10000
          }
        );

        const data = response.data;
        let results: string[] = [];

        // Include answer box if available (direct answers)
        if (data.answerBox) {
          const ab = data.answerBox;
          if (ab.answer) {
            results.push(`**Direct Answer:** ${ab.answer}`);
          } else if (ab.snippet) {
            results.push(`**Direct Answer:** ${ab.snippet}`);
          }
        }

        // Include knowledge graph if available
        if (data.knowledgeGraph?.description) {
          results.push(`**Summary:** ${data.knowledgeGraph.description}`);
        }

        // Include organic search results
        if (data.organic && data.organic.length > 0) {
          const organicResults = data.organic.slice(0, 5).map((r, i) => 
            `${i + 1}. **${r.title}**\n   ${r.snippet}\n   Source: ${r.link}`
          );
          results.push(...organicResults);
        }

        if (results.length === 0) {
          return `[info] No results found for "${query}"`;
        }

        console.log(`[WebSearch] Found ${results.length} results`);
        return `Search results for "${query}":\n\n${results.join("\n\n")}`;

      } catch (error: any) {
        console.error("[WebSearch] Error:", error.message);
        
        if (error.response?.status === 401) {
          return "[error] Invalid Serper API key";
        } else if (error.response?.status === 429) {
          return "[error] Search rate limit exceeded";
        } else if (error.code === "ECONNABORTED") {
          return "[error] Search timed out - please try again";
        }
        
        return `[error] Search failed: ${error.message}`;
      }
    }
  }
];

export default webSearchTools;



