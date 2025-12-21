import { LLMTool } from "../../type";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";
import { telegramBot } from "../../utils/telegram";
import { ttsProcessor } from "../../cloud-api/server";
import { setPendingVisualMode } from "../../utils/image";

const SCRIPT_PATH = path.join(__dirname, "../../../python/pose_estimation.py");
const STATE_FILE = "/tmp/pose_state.json";
const POSE_FRAME = "/tmp/whisplay_pose_frame.jpg";

let poseProcess: any = null;

// Helper to stop pose detection and release camera
export const stopPoseAndReleaseCamera = async (): Promise<boolean> => {
  let stopped = false;
  let pidToKill: number | null = null;
  
  // Signal stop via state file removal
  if (fs.existsSync(STATE_FILE)) {
    // Try to read the PID so we can force-stop if it doesn't exit promptly.
    try {
      const stateContent = fs.readFileSync(STATE_FILE, "utf-8");
      const state = JSON.parse(stateContent);
      if (typeof state?.pid === "number") {
        pidToKill = state.pid;
      }
    } catch (e) {
      // ignore parse errors; we'll fall back to just unlinking the state file
    }

    console.log("[PoseEstimation] Stopping via state file removal...");
    fs.unlinkSync(STATE_FILE);
    stopped = true;
  }
  
  // Also kill legacy process if it exists
  if (poseProcess) {
    console.log("[PoseEstimation] Killing legacy process...");
    poseProcess.kill('SIGTERM');
    poseProcess = null;
    stopped = true;
  }
  
  if (stopped) {
    // If the pose process doesn't exit quickly, force-stop it so picamera2 releases /dev/media*.
    if (pidToKill) {
      const isAlive = (pid: number) => {
        try {
          process.kill(pid, 0);
          return true;
        } catch (e) {
          return false;
        }
      };

      try {
        if (isAlive(pidToKill)) {
          console.log(`[PoseEstimation] Sending SIGTERM to PID ${pidToKill}...`);
          process.kill(pidToKill, "SIGTERM");
        }
      } catch (e) {
        // ignore permission/race errors
      }

      const start = Date.now();
      while (isAlive(pidToKill) && Date.now() - start < 3000) {
        await new Promise((resolve) => setTimeout(resolve, 150));
      }

      try {
        if (isAlive(pidToKill)) {
          console.warn(`[PoseEstimation] PID ${pidToKill} still alive; sending SIGKILL...`);
          process.kill(pidToKill, "SIGKILL");
        }
      } catch (e) {
        // ignore
      }
    }

    // Wait briefly for camera to be released
    await new Promise(resolve => setTimeout(resolve, 750));
    console.log("[PoseEstimation] Camera should be released now");
    
    // Clean up frame file
    if (fs.existsSync(POSE_FRAME)) {
      try {
        fs.unlinkSync(POSE_FRAME);
      } catch(e) {}
    }
  }
  
  return stopped;
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

        // Kill any existing pose process
        if (poseProcess) {
          try {
            poseProcess.kill();
          } catch(e) {}
          poseProcess = null;
        }
        
        // Remove state file if exists
        if (fs.existsSync(STATE_FILE)) fs.unlinkSync(STATE_FILE);

        console.log(`[Tool] Preparing pose detection for action: ${action}`);

        // Use the visual mode system so frames appear on display
        setPendingVisualMode({
          type: 'pose',
          framePath: POSE_FRAME,
          poseScript: SCRIPT_PATH,
          poseAction: action || "detect",
          poseCount: false,
          poseGoal: undefined,
        });

        const actionDesc = action === "detect" ? "any pose or action" : action;
        return `[success]Starting pose detection for: ${actionDesc}. Watch the display for the camera view with skeleton overlay.`;
      } catch (error: any) {
        return `[error]Failed to start pose detection: ${error.message}`;
      }
    },
  },
  {
    type: "function",
    function: {
      name: "startExerciseCounter",
      description: "Count exercise repetitions in real-time. Tracks push-ups, squats, or pull-ups and counts each complete rep. Optionally set a goal to stop when reached. Can also record the exercise session.",
      parameters: {
        type: "object",
        properties: {
          exercise: {
            type: "string",
            enum: ["pushup", "squat", "pullup", "crunch"],
            description: "Exercise to count: 'pushup', 'squat', 'pullup', or 'crunch'"
          },
          goal: {
            type: "number",
            description: "Target number of reps (optional). If set, counting stops when goal is reached."
          },
          record: {
            type: "boolean",
            description: "Whether to record a video of the exercise session with pose overlay (default: false)"
          }
        },
        required: ["exercise"],
      },
    },
    func: async (params) => {
      try {
        const { exercise, goal, record } = params;

        // Kill any existing pose process
        if (poseProcess) {
          try {
            poseProcess.kill();
          } catch(e) {}
          poseProcess = null;
        }
        
        // Remove state file if exists
        if (fs.existsSync(STATE_FILE)) fs.unlinkSync(STATE_FILE);

        console.log(`[Tool] Preparing exercise counter for: ${exercise}${goal ? ` (goal: ${goal})` : ''}${record ? ' (recording)' : ''}`);

        // Use the visual mode system so frames appear on display
        setPendingVisualMode({
          type: 'pose',
          framePath: POSE_FRAME,
          poseScript: SCRIPT_PATH,
          poseAction: exercise,
          poseCount: true,
          poseGoal: goal,
          poseRecord: record,
        } as any);

        const goalText = goal ? ` Your goal is ${goal} reps.` : "";
        const recordText = record ? " I'll also record a video of your workout." : "";
        return `[success]Starting exercise counter for ${exercise}s.${goalText}${recordText} Watch the display for the camera view with pose tracking!`;
      } catch (error: any) {
        return `[error]Failed to start exercise counter: ${error.message}`;
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
      // Read state BEFORE stopping
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
        
        // Delete state file to signal Python script to stop
        // (the script checks for STATE_FILE existence in its loop)
        fs.unlinkSync(STATE_FILE);
      }
      
      // Also kill legacy process if it exists
      if (poseProcess) {
        try {
          poseProcess.kill('SIGTERM');
        } catch(e) {}
        poseProcess = null;
      }
      
      // Wait for process to exit and release camera
      await new Promise(resolve => setTimeout(resolve, 1500));
      
      // Clean up frame file
      if (fs.existsSync(POSE_FRAME)) {
        try {
          fs.unlinkSync(POSE_FRAME);
        } catch(e) {}
      }
      
      // Build final message with ACTUAL count
      if (reps > 0) {
        finalMessage = `Exercise counting stopped. You completed ${reps} ${exercise}s${goal ? ` (goal was ${goal})` : ''}.`;
        await ttsProcessor(`You did ${reps} ${exercise}s!`);
      } else if (exercise !== "exercise") {
        finalMessage = `Exercise counting stopped. No ${exercise}s were detected.`;
      }
      
      return finalMessage;
    }
  },
  {
    type: "function",
    function: {
      name: "playExerciseVideo",
      description: "Play the most recently recorded exercise video on the display. Use this when the user asks to see their workout video, exercise recording, or proof of their exercise.",
      parameters: {},
    },
    func: async () => {
      try {
        const EXERCISE_VIDEO_DIR = path.join(process.env.HOME || "/home/dash", "ai-pi/captures/pose");
        
        // Find most recent exercise video
        if (!fs.existsSync(EXERCISE_VIDEO_DIR)) {
          return "[error]No exercise videos found.";
        }
        
        const files = fs.readdirSync(EXERCISE_VIDEO_DIR)
          .filter(f => f.endsWith(".mp4") && f.startsWith("exercise-"))
          .map(f => ({
            name: f,
            path: path.join(EXERCISE_VIDEO_DIR, f),
            time: fs.statSync(path.join(EXERCISE_VIDEO_DIR, f)).mtime.getTime(),
          }))
          .sort((a, b) => b.time - a.time);

        if (files.length === 0) {
          return "[error]No exercise videos found. Try recording an exercise session first with 'count my pushups and record a video'.";
        }

        const videoPath = files[0].path;
        console.log(`[PlayExerciseVideo] Playing: ${videoPath}`);

        // Set pending visual mode for playback
        setPendingVisualMode({
          type: 'playback',
          framePath: videoPath
        });

        return `[success]Playing your most recent exercise video.`;
      } catch (error: any) {
        console.error("Error playing exercise video:", error);
        return `[error]Failed to play exercise video: ${error.message}`;
      }
    }
  }
];

export default poseEstimationTools;

