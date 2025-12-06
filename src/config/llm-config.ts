require("dotenv").config();
import * as fs from "fs";

// default 5 minutes
export const CHAT_HISTORY_RESET_TIME = parseInt(process.env.CHAT_HISTORY_RESET_TIME || "300" , 10) * 1000; // convert to milliseconds

export let lastMessageTime = 0;

export const updateLastMessageTime = (): void => {
  lastMessageTime = Date.now();
}

export const shouldResetChatHistory = (): boolean => {
  return Date.now() - lastMessageTime > CHAT_HISTORY_RESET_TIME;
}

const baseSystemPrompt =
  process.env.SYSTEM_PROMPT ||
  "You are a young and cheerful girl who loves to talk, chat, help others, and learn new things. You enjoy using emoji expressions. Never answer longer than 200 words. Always keep your answers concise and to the point.";

// Get current context (e.g., active exercise session)
const getActiveContext = (): string => {
  const STATE_FILE = "/tmp/pose_state.json";
  try {
    if (fs.existsSync(STATE_FILE)) {
      const state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
      if (state.counting && state.action) {
        return `\n\n[ACTIVE SESSION: You are currently counting ${state.action}s for the user. They have done ${state.reps || 0} reps so far. If they say "done", "finished", "stop", or similar, call stopPoseDetection to end the session.]`;
      }
    }
  } catch (e) {
    // Ignore errors reading state
  }
  return "";
};

// Dynamic system prompt that includes current context
export const getSystemPrompt = (): string => {
  return baseSystemPrompt + getActiveContext();
};

// Keep for backwards compatibility
export const systemPrompt = baseSystemPrompt;
