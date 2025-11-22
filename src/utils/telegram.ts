import fs from 'fs';
import path from 'path';
import dotenv from 'dotenv';

// Load environment variables
dotenv.config();

class TelegramBot {
  private token: string;
  private chatId: string | null = null;
  private baseUrl: string;
  private isInitializing: boolean = false;

  constructor(token: string) {
    if (!token) {
      console.error('[Telegram] Token is missing!');
    }
    this.token = token;
    this.baseUrl = `https://api.telegram.org/bot${token}`;
    // Start polling for chat ID
    this.startPolling();
  }

  private onMessageCallback: ((text: string) => void) | null = null;

  public setOnMessageCallback(callback: (text: string) => void) {
    this.onMessageCallback = callback;
  }

  private async startPolling() {
    console.log('[Telegram] Initializing... Waiting for user interaction to get Chat ID.');
    
    // Poll until we find a chat ID
    const poll = async () => {
      if (!this.chatId) {
        await this.getUpdates();
      } else {
        // If we already have chat ID, keep polling for new messages to handle as commands
        await this.getUpdates();
      }
      
      // Always continue polling
      setTimeout(poll, 2000);
    };
    
    poll();
  }

  // Removed manual initialize() call since we use polling now
  async initialize() {
    // Deprecated, kept for compatibility if needed, but logic moved to polling
  }

  async getUpdates() {
    try {
      // We need to keep track of the last update ID to confirm we processed it
      // and to ask for only newer updates next time (Telegram long polling best practice)
      const offsetParams = this.lastUpdateId ? `?offset=${this.lastUpdateId + 1}` : '';
      const response = await fetch(`${this.baseUrl}/getUpdates${offsetParams}`);
      const data = await response.json() as any;
      
      if (data.ok && data.result && data.result.length > 0) {
        for (const update of data.result) {
          this.lastUpdateId = update.update_id;

          if (update.message && update.message.chat) {
             // Only process if we haven't found the ID yet to prevent duplicate welcome messages
            if (!this.chatId) {
                this.chatId = update.message.chat.id.toString();
                console.log(`[Telegram] Chat ID found: ${this.chatId} (from ${update.message.chat.username || update.message.chat.first_name})`);
                // Send a welcome message so the user knows we are connected
                this.sendMessage("Connected to Optidex! I will send you updates here.");
            }

            // If we have a callback for message handling (i.e. ChatFlow is listening)
            if (this.onMessageCallback && update.message.text) {
                const text = update.message.text;
                // Ignore start command for processing
                if (text !== '/start') {
                    console.log(`[Telegram] Received command: ${text}`);
                    this.onMessageCallback(text);
                }
            }
          }
        }
      }
    } catch (error) {
      console.error('[Telegram] Error fetching updates:', error);
    }
    return null;
  }

  private lastUpdateId: number = 0;

  async ensureChatId(): Promise<boolean> {
    if (this.chatId) return true;
    await this.getUpdates();
    if (!this.chatId) {
       // Throttle logs or just log once?
       // console.log('[Telegram] No Chat ID found. Send a message to the bot to connect.');
    }
    return !!this.chatId;
  }

  async sendMessage(text: string) {
    if (!await this.ensureChatId()) return;

    try {
      const response = await fetch(`${this.baseUrl}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: this.chatId,
          text: text
        })
      });
      
      if (!response.ok) {
          console.error(`[Telegram] sendMessage failed: ${response.status} ${response.statusText}`);
      }
    } catch (error) {
      console.error('[Telegram] Error sending message:', error);
    }
  }

  async sendPhoto(filePath: string) {
    if (!await this.ensureChatId()) return;

    if (!fs.existsSync(filePath)) {
        console.error(`[Telegram] Photo file not found: ${filePath}`);
        return;
    }

    try {
      console.log(`[Telegram] Sending photo: ${filePath}`);
      const formData = new FormData();
      formData.append('chat_id', this.chatId!);
      
      const blob = await fs.openAsBlob(filePath);
      formData.append('photo', blob, path.basename(filePath));

      const response = await fetch(`${this.baseUrl}/sendPhoto`, {
        method: 'POST',
        body: formData
      });

       if (!response.ok) {
          console.error(`[Telegram] sendPhoto failed: ${response.status} ${response.statusText}`);
      } else {
          console.log('[Telegram] Photo sent successfully');
      }
    } catch (error) {
      console.error('[Telegram] Error sending photo:', error);
    }
  }

  async sendVideo(filePath: string) {
    if (!await this.ensureChatId()) return;

    if (!fs.existsSync(filePath)) {
        console.error(`[Telegram] Video file not found: ${filePath}`);
        return;
    }

    try {
      console.log(`[Telegram] Sending video: ${filePath}`);
      const formData = new FormData();
      formData.append('chat_id', this.chatId!);
      
      const blob = await fs.openAsBlob(filePath);
      formData.append('video', blob, path.basename(filePath));

      const response = await fetch(`${this.baseUrl}/sendVideo`, {
        method: 'POST',
        body: formData
      });

       if (!response.ok) {
          console.error(`[Telegram] sendVideo failed: ${response.status} ${response.statusText}`);
      } else {
          console.log('[Telegram] Video sent successfully');
      }
    } catch (error) {
      console.error('[Telegram] Error sending video:', error);
    }
  }
}

export const telegramBot = new TelegramBot(process.env.TELEGRAM_BOT_TOKEN || '');


