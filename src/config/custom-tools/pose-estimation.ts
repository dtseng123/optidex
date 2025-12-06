import { LLMTool } from "../../type";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";
import { telegramBot } from "../../utils/telegram";
import { ttsProcessor } from "../../cloud-api/server";

const SCRIPT_PATH = path.join(__dirname, "../../../python/pose_estimation.py");
const STATE_FILE = "/tmp/pose_state.json";

let poseProcess: any = null;

// Helper to stop pose detection and release camera
export const stopPoseAndReleaseCamera = async (): Promise<boolean> => {
  if (poseProcess) {
    console.log("[PoseEstimation] Stopping to release camera...");
    poseProcess.kill('SIGTERM');
    poseProcess = null;
    if (fs.existsSync(STATE_FILE)) {
      fs.unlinkSync(STATE_FILE);
    }
    // Wait for camera to be released
    await new Promise(resolve => setTimeout(resolve, 1500));
    console.log("[PoseEstimation] Camera should be released now");
    return true;
  }
  return false;
};

const poseEstimationTools: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "startPoseDetection",
      description: "Start pose estimation to detect human body poses and actions like waving, hands up, sitting, or standing. Useful for gesture detection or monitoring activities. For exercise counting, use startExerciseCounter instead.",
      parameters: {
        type: "object",
        properties: {
          action: {
            type: "string",
            enum: ["detect", "waving", "hands_up", "sitting", "standing"],
            description: "Action to detect: 'waving' (hand raised), 'hands_up' (both hands up), 'sitting', 'standing', or 'detect' (any action)"
          },
        },
        required: ["action"],
      },
    },
    func: async (params) => {
      try {
        const { action } = params;

        if (poseProcess) {
          // Kill existing
          try {
            poseProcess.kill();
          } catch(e) {}
          poseProcess = null;
        }
        
        // Remove state file if exists
        if (fs.existsSync(STATE_FILE)) fs.unlinkSync(STATE_FILE);

        const args = [
          SCRIPT_PATH,
          "--action", action || "detect",
          "--visualize"  // Draw skeleton on saved images
        ];

        poseProcess = spawn("python3", args);
        
        console.log(`[PoseEstimation] Started for action: ${action}`);
        
        poseProcess.stdout.on("data", async (data: Buffer) => {
          const line = data.toString().trim();
          if (line.includes("JSON_TRIGGER:")) {
            try {
              const jsonStr = line.split("JSON_TRIGGER:")[1];
              const event = JSON.parse(jsonStr);
              
              console.log(`[PoseEstimation] Triggered:`, event);
              
              let message = `👋 Alert: I detected someone ${event.action}!`;
              
              // Add details
              if (event.details) {
                if (event.details.hand) {
                  message += ` (${event.details.hand} hand)`;
                }
              }
              
              // 1. Speak alert
              await ttsProcessor(message);
              
              // 2. Send to Telegram
              telegramBot.sendMessage(message);
              if (event.image_path && fs.existsSync(event.image_path)) {
                telegramBot.sendPhoto(event.image_path);
              }
              
            } catch (e) {
              console.error("Error parsing pose trigger:", e);
            }
          }
        });

        poseProcess.stderr.on("data", (data: Buffer) => {
          const msg = data.toString().trim();
          if (msg.startsWith("Starting") || msg.startsWith("Action") || msg.startsWith("Model")) {
            console.log(`[Pose Log]: ${msg}`);
          }
        });

        const actionDesc = action === "detect" ? "any pose or action" : action;
        return `Pose detection started. I am watching for: ${actionDesc}.`;
      } catch (error: any) {
        return `Error starting pose detection: ${error.message}`;
      }
    },
  },
  {
    type: "function",
    function: {
      name: "startExerciseCounter",
      description: "Count exercise repetitions in real-time. Tracks push-ups, squats, or pull-ups and counts each complete rep. Optionally set a goal to stop when reached.",
      parameters: {
        type: "object",
        properties: {
          exercise: {
            type: "string",
            enum: ["pushup", "squat", "pullup"],
            description: "Exercise to count: 'pushup', 'squat', or 'pullup'"
          },
          goal: {
            type: "number",
            description: "Target number of reps (optional). If set, counting stops when goal is reached."
          }
        },
        required: ["exercise"],
      },
    },
    func: async (params) => {
      try {
        const { exercise, goal } = params;

        if (poseProcess) {
          // Kill existing
          try {
            poseProcess.kill();
          } catch(e) {}
          poseProcess = null;
        }
        
        // Remove state file if exists
        if (fs.existsSync(STATE_FILE)) fs.unlinkSync(STATE_FILE);

        const args = [
          SCRIPT_PATH,
          "--action", exercise,
          "--count",
          "--visualize"
        ];
        
        if (goal) {
          args.push("--goal", goal.toString());
        }

        poseProcess = spawn("python3", args);
        
        console.log(`[ExerciseCounter] Started counting ${exercise}${goal ? ` (goal: ${goal})` : ''}`);
        
        let currentCount = 0;
        
        poseProcess.stdout.on("data", async (data: Buffer) => {
          const line = data.toString().trim();
          
          // Audio feedback for "down" state
          if (line.includes("JSON_AUDIO:down")) {
            console.log(`[ExerciseCounter] Down detected`);
            ttsProcessor("down").catch(e => 
              console.error("[ExerciseCounter] TTS error:", e)
            );
          }
          
          // Rep progress updates
          if (line.includes("JSON_PROGRESS:")) {
            try {
              const jsonStr = line.split("JSON_PROGRESS:")[1];
              const progress = JSON.parse(jsonStr);
              currentCount = progress.reps;
              
              console.log(`[ExerciseCounter] Rep ${currentCount}${progress.goal ? `/${progress.goal}` : ''}`);
              
              // Speak the count out loud (non-blocking so pose detection continues smoothly)
              ttsProcessor(currentCount.toString()).catch(e => 
                console.error("[ExerciseCounter] TTS error:", e)
              );
              
            } catch (e) {
              console.error("Error parsing progress:", e);
            }
          }
          
          // Goal reached
          if (line.includes("JSON_TRIGGER:")) {
            try {
              const jsonStr = line.split("JSON_TRIGGER:")[1];
              const event = JSON.parse(jsonStr);
              
              if (event.event === "goal_reached") {
                console.log(`[ExerciseCounter] Goal reached: ${event.reps} reps!`);
                
                const message = `🎉 Great job! You completed ${event.reps} ${exercise}s! Goal reached!`;
                
                // 1. Speak congratulations
                await ttsProcessor(message);
                
                // 2. Send to Telegram
                telegramBot.sendMessage(message);
                
                // Stop the process gracefully
                if (poseProcess) {
                  console.log("[ExerciseCounter] Stopping pose process...");
                  poseProcess.kill('SIGTERM');
                  // Wait a bit for cleanup
                  setTimeout(() => {
                    poseProcess = null;
                    console.log("[ExerciseCounter] Pose process stopped, camera released");
                  }, 1000);
                }
              }
              
            } catch (e) {
              console.error("Error parsing trigger:", e);
            }
          }
        });

        poseProcess.stderr.on("data", (data: Buffer) => {
          const msg = data.toString().trim();
          if (msg.startsWith("Starting") || msg.startsWith("Rep") || msg.startsWith("Goal") || msg.startsWith("Model")) {
            console.log(`[Exercise Log]: ${msg}`);
          }
        });

        const goalText = goal ? ` Your goal is ${goal} reps.` : "";
        return `Exercise counter started for ${exercise}s.${goalText} I'll count each rep!`;
      } catch (error: any) {
        return `Error starting exercise counter: ${error.message}`;
      }
    },
  },
  {
    type: "function",
    function: {
      name: "stopPoseDetection",
      description: "Stop the currently running pose detection or exercise counter. Call this when the user says they are 'done', 'finished', 'stop', 'that's enough', 'I'm done exercising', or any similar phrase indicating they want to end the exercise session.",
      parameters: {},
    },
    func: async () => {
      if (poseProcess) {
        // Read state BEFORE killing process
        let finalMessage = "Pose detection stopped.";
        let reps = 0;
        let exercise = "exercise";
        let goal = 0;
        
        if (fs.existsSync(STATE_FILE)) {
          try {
            const stateContent = fs.readFileSync(STATE_FILE, 'utf-8');
            const state = JSON.parse(stateContent);
            reps = state.reps || 0;
            exercise = state.action || "exercise";
            goal = state.goal || 0;
            console.log(`[StopPose] Read state: reps=${reps}, exercise=${exercise}, goal=${goal}`);
          } catch (e) {
            console.error("[StopPose] Error reading state:", e);
          }
        }
        
        // Kill the process
        poseProcess.kill('SIGTERM');
        poseProcess = null;
        
        // Wait for process to exit and release camera
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // Delete state file if still exists
        if (fs.existsSync(STATE_FILE)) fs.unlinkSync(STATE_FILE);
        
        // Build final message with ACTUAL count
        if (reps > 0) {
          finalMessage = `Exercise counting stopped. You actually completed ${reps} ${exercise}s (goal was ${goal}).`;
          await ttsProcessor(`You did ${reps} ${exercise}s!`);
        } else {
          finalMessage = `Exercise counting stopped. No ${exercise}s were detected.`;
        }
        
        return finalMessage;
      } else {
        return "Pose detection was not running.";
      }
    }
  }
];

export default poseEstimationTools;

