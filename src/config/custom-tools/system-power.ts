import { LLMTool } from "../../type";
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

const systemPowerTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "shutdownSystem",
      description: "Safely shutdown the Raspberry Pi system. Use this when the user asks to turn off, shutdown, or power down the device.",
      parameters: {
        type: "object",
        properties: {
          delay: {
            type: "number",
            description: "Optional delay in seconds before shutdown (default: 5 seconds to allow response to complete)",
          },
        },
      },
    },
    func: async (params) => {
      try {
        const delay = params.delay || 5;
        
        console.log(`[System] Initiating shutdown in ${delay} seconds...`);
        
        // Schedule shutdown with delay to allow the response to be spoken
        const command = `sleep ${delay} && sudo shutdown -h now`;
        
        // Run in background so we can return immediately
        exec(command, (error) => {
          if (error) {
            console.error(`[System] Shutdown error: ${error.message}`);
          }
        });
        
        return `[success]Shutting down in ${delay} seconds. Goodbye!`;
      } catch (error: any) {
        console.error("Error initiating shutdown:", error);
        return `[error]Failed to shutdown: ${error.message}`;
      }
    },
  },
  
  {
    type: "function",
    function: {
      name: "rebootSystem",
      description: "Safely reboot the Raspberry Pi system. Use this when the user asks to restart or reboot the device.",
      parameters: {
        type: "object",
        properties: {
          delay: {
            type: "number",
            description: "Optional delay in seconds before reboot (default: 5 seconds)",
          },
        },
      },
    },
    func: async (params) => {
      try {
        const delay = params.delay || 5;
        
        console.log(`[System] Initiating reboot in ${delay} seconds...`);
        
        // Schedule reboot with delay to allow the response to be spoken
        const command = `sleep ${delay} && sudo reboot`;
        
        // Run in background so we can return immediately
        exec(command, (error) => {
          if (error) {
            console.error(`[System] Reboot error: ${error.message}`);
          }
        });
        
        return `[success]Rebooting in ${delay} seconds. I'll be right back!`;
      } catch (error: any) {
        console.error("Error initiating reboot:", error);
        return `[error]Failed to reboot: ${error.message}`;
      }
    },
  },
];

export default systemPowerTools;


