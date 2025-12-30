import { getCurrentTimeTag, splitSentences } from "./../utils/index";
import { get, noop } from "lodash";
import { telegramBot } from "../utils/telegram";
import { startMeshtasticMonitor } from "../config/custom-tools/meshtastic";
import { gemini, geminiModel } from "../cloud-api/gemini";
import {
  onButtonPressed,
  onButtonReleased,
  display,
  getCurrentStatus,
} from "../device/display";
import { recordAudioManually, recordFileFormat } from "../device/audio";
import {
  recognizeAudio,
  chatWithLLMStream,
  ttsProcessor,
} from "../cloud-api/server";
import { extractEmojis } from "../utils";
import { StreamResponser } from "./StreamResponsor";
import { recordingsDir } from "../utils/dir";
import { 
  getLatestGenImg, 
  isVisualModeActive,
  getPendingVisualMode,
  hasVisualPending,
  setLiveDetectionActive,
  setVideoRecordingActive,
  clearVideoPlayback
} from "../utils/image";
import fs from "fs";
import { resolve } from "path";

class ChatFlow {
  currentFlowName: string = "";
  recordingsDir: string = "";
  currentRecordFilePath: string = "";
  asrText: string = "";
  streamResponser: StreamResponser;
  partialThinking: string = "";
  thinkingSentences: string[] = [];
  answerId: number = 0;

  constructor() {
    console.log(`[${getCurrentTimeTag()}] ChatBot started.`);
    this.recordingsDir = recordingsDir;
    this.setCurrentFlow("sleep");
    
    // Listen for Telegram messages
    telegramBot.setOnMessageCallback((text) => {
      console.log(`[ChatFlow] Received Telegram message: ${text}`);
      
      // If a visual mode is active, we must stop it to give control to the answer flow
      if (isVisualModeActive()) {
        console.log(`[ChatFlow] Stopping visual mode for incoming Telegram message`);
        this.stopVisualMode();
      }
      
      this.asrText = text;
      display({ status: "recognizing", text: text });
      this.setCurrentFlow("answer");
    });

    // Listen for Meshtastic messages (disabled - no device connected)
    // startMeshtasticMonitor((msg: any) => {
    //    console.log("[ChatFlow] Received Meshtastic message:", msg);
    //    
    //    // Format message for TTS
    //    const spokenText = `New message from ${msg.from}: ${msg.text}`;
    //    
    //    // If visual mode active, stop it
    //    if (isVisualModeActive()) {
    //        this.stopVisualMode();
    //    }
    //    
    //    // Display and Speak
    //    this.asrText = spokenText;
    //    display({ status: "recognizing", text: `Msg from ${msg.from}` });
    //    
    //    // Trigger answer flow to read it out
    //    this.asrText = `I just received a message on the mesh network from ${msg.from}. It says: "${msg.text}". Please read this out to me.`;
    //    this.setCurrentFlow("answer");
    // });

    this.streamResponser = new StreamResponser(
      ttsProcessor,
      (sentences: string[]) => {
        if (this.currentFlowName !== "answer") return;
        // Don't update display if any visual mode is active or pending
        if (isVisualModeActive() || hasVisualPending()) return;
        const fullText = sentences.join(" ");
        display({
          status: "answering",
          emoji: extractEmojis(fullText) || "😊",
          text: fullText,
          RGB: "#0000ff",
          scroll_speed: 3,
        });
      },
      (text: string) => {
        if (this.currentFlowName !== "answer") return;
        // Don't update display if any visual mode is active or pending
        if (isVisualModeActive() || hasVisualPending()) return;
        display({
          status: "answering",
          text: text || undefined,
          scroll_speed: 3,
        });
      }
    );
  }

  /**
   * Inject an externally-recorded audio file (e.g., from ESP32 BLE mic stream)
   * into the normal ASR -> LLM -> tools pipeline.
   */
  handleExternalAudioFile = (audioFilePath: string): void => {
    try {
      if (!audioFilePath) return;

      console.log(`[ChatFlow] External audio file received: ${audioFilePath}`);

      // If a visual mode is active, stop it so we can run command handling.
      if (isVisualModeActive()) {
        console.log(`[ChatFlow] Stopping visual mode for external audio`);
        this.stopVisualMode();
      }

      this.currentRecordFilePath = audioFilePath;
      this.setCurrentFlow("asr");
    } catch (e) {
      console.error("[ChatFlow] handleExternalAudioFile error:", e);
    }
  };

  partialThinkingCallback = (
    partialThinking: string,
    answerId: number
  ): void => {
    if (this.currentFlowName !== "answer" || answerId < this.answerId) return;
    // Don't update display if any visual mode is active or pending
    if (isVisualModeActive() || hasVisualPending()) return;
    this.partialThinking += partialThinking;
    const { sentences, remaining } = splitSentences(this.partialThinking);
    if (sentences.length > 0) {
      this.thinkingSentences.push(...sentences);
      const displayText = this.thinkingSentences.join(" ");
      display({
        status: "Thinking",
        emoji: "🤔",
        text: displayText,
        RGB: "#ff6800", // yellow
        scroll_speed: 6,
      });
    }
    this.partialThinking = remaining;
  };

  // Visual mode display intervals
  private visualModeInterval: NodeJS.Timeout | null = null;
  private activeVisualProcess: any = null; // Track spawned Python processes

  startVisualMode = (visualMode: { type: string; framePath: string }): void => {
    console.log(`[ChatFlow] ========================================`);
    console.log(`[ChatFlow] Starting visual mode: ${visualMode.type}`);
    console.log(`[ChatFlow] Frame path: ${visualMode.framePath}`);
    console.log(`[ChatFlow] Current flow before: ${this.currentFlowName}`);
    
    // Stop any existing visual mode and clean up
    this.stopVisualMode();
    
    // Wait a moment for cleanup to complete
    const startTime = Date.now();
    
    // Set appropriate state flags
    if (visualMode.type === 'detection') {
      const detectionScript = (visualMode as any).detectionScript;
      const targetObjects = (visualMode as any).targetObjects || [];
      const duration = (visualMode as any).duration;
      const videoPath = (visualMode as any).videoPath;
      
      // Check if this is Smart Observer or Semantic Sentry
      const isObserver = detectionScript?.includes('smart_observer');
      const isSentry = detectionScript?.includes('semantic_sentry');
      const observerPrompt = (visualMode as any).observerPrompt;
      const observerRecord = (visualMode as any).observerRecord;
      const observerContinuous = (visualMode as any).observerContinuous;
      const sentryPairs = (visualMode as any).sentryPairs;
      const sentryRecord = (visualMode as any).sentryRecord;
      
      console.log(`[ChatFlow] ========================================`);
      console.log(`[ChatFlow] DETECTION MODE - Starting ${isObserver ? 'Smart Observer' : isSentry ? 'Semantic Sentry' : 'Live Detection'}`);
      console.log(`[ChatFlow] Frame path: ${visualMode.framePath}`);
      console.log(`[ChatFlow] Target objects:`, targetObjects);
      console.log(`[ChatFlow] observerRecord: ${observerRecord}, observerContinuous: ${observerContinuous}`);
      console.log(`[ChatFlow] sentryRecord: ${sentryRecord}`);
      console.log(`[ChatFlow] Script: ${detectionScript}`);
      console.log(`[ChatFlow] ========================================`);
      
      setLiveDetectionActive(true);
      this.currentFlowName = isObserver ? "observer" : isSentry ? "sentry" : "detection";
      
      // Build command args based on type
      let args: string[] = [];
      
      if (isObserver) {
        args = [...targetObjects, "--visualize"];
        // Default to recording ON unless explicitly disabled
        if (observerRecord !== false) args.push("--record");
        // Default to continuous ON for monitoring
        if (observerContinuous !== false) args.push("--continuous");
      } else if (isSentry) {
        args = [...(sentryPairs || []), "--visualize"];
        // Default to recording ON unless explicitly disabled
        if (sentryRecord !== false) args.push("--record");
        // Default to continuous ON for monitoring
        args.push("--continuous");
      } else {
        // Original live_detection
        args = ["start", ...targetObjects];
        if (duration) args.push("--duration", String(duration));
        if (videoPath) args.push("--video_out", videoPath);
        const segmentation = Boolean((visualMode as any).detectionSegmentation);
        const segModel = (visualMode as any).detectionSegModel;
        if (segmentation) args.push("--segmentation");
        if (segmentation && typeof segModel === "string" && segModel.trim()) {
          args.push("--seg_model", segModel.trim());
        }
      }
      
      console.log(`[ChatFlow] Final args:`, args);
      
      // Start the detection process
      const { spawn } = require("child_process");
      const detectionProcess = spawn("python3", [detectionScript, ...args]);
      this.activeVisualProcess = detectionProcess;
      
      let lastDetectionLog = 0;

      detectionProcess.stdout?.on("data", async (data: Buffer) => {
        const lines = data.toString().trim().split('\n');
        
        for (const line of lines) {
          // Log periodically
          if (Date.now() - lastDetectionLog > 2000) {
            console.log(`[Detector]: ${line}`);
            lastDetectionLog = Date.now();
          }
          
          // Handle trigger events
          if (line.includes("JSON_TRIGGER:")) {
            try {
              const jsonStr = line.split("JSON_TRIGGER:")[1];
              const event = JSON.parse(jsonStr);
              console.log(`[Detector] Trigger:`, event);
              
              if (isObserver && event.event === "object_detected") {
                const message = `Detected ${event.objects?.join(", ")}! (${event.count} total)`;
                await ttsProcessor(message);
                telegramBot.sendMessage(`👀 ${message}`);
                
                if (event.image_path && fs.existsSync(event.image_path)) {
                  telegramBot.sendPhoto(event.image_path);
                  
                  // AI analysis if prompt provided
                  if (observerPrompt && gemini) {
                    try {
                      const imageBuffer = fs.readFileSync(event.image_path);
                      const imageBase64 = imageBuffer.toString("base64");
                      const response = await gemini.models.generateContent({
                        model: geminiModel,
                        contents: [{
                          role: 'user',
                          parts: [
                            { text: observerPrompt },
                            { inlineData: { data: imageBase64, mimeType: "image/jpeg" } }
                          ]
                        }]
                      });
                      let analysis = "No analysis generated.";
                      if (response?.candidates?.[0]?.content?.parts?.[0]?.text) {
                        analysis = response.candidates[0].content.parts[0].text;
                      }
                      telegramBot.sendMessage(`🧠 Analysis: ${analysis}`);
                    } catch (err: any) {
                      console.error("Gemini Error:", err);
                    }
                  }
                }
              } else if (isSentry && event.event === "interaction_detected") {
                const message = `Alert! ${event.object1} interacting with ${event.object2}! (${event.count} total)`;
                await ttsProcessor(message);
                telegramBot.sendMessage(`⚠️ ${message}`);
                
                if (event.image_path && fs.existsSync(event.image_path)) {
                  telegramBot.sendPhoto(event.image_path);
                }
              }
            } catch (e) {
              console.error("[Detector] Error parsing trigger:", e);
            }
          }
          
          // Handle video saved event
          if (line.includes("JSON_VIDEO:")) {
            try {
              const jsonStr = line.split("JSON_VIDEO:")[1];
              const event = JSON.parse(jsonStr);
              console.log(`[Detector] Video saved:`, event);
              
              if (event.video_path && fs.existsSync(event.video_path)) {
                telegramBot.sendMessage(`🎬 Monitoring video saved!`);
                telegramBot.sendVideo(event.video_path);
              }
            } catch (e) {
              console.error("[Detector] Error parsing video event:", e);
            }
          }
        }
      });
      
      detectionProcess.stderr?.on("data", (data: Buffer) => {
        const msg = data.toString().trim();
        if (msg.includes("Starting") || msg.includes("Using") || msg.includes("Detected") || msg.includes("TRIGGER")) {
          console.log(`[Detector]: ${msg}`);
        }
      });
      
      detectionProcess.on("exit", (code: number) => {
        console.log(`[ChatFlow] Detection process exited with code ${code}`);

        // Auto-stop visual mode
        setTimeout(() => {
          if (this.visualModeInterval) {
            console.log(`[ChatFlow] Cleaning up after detection completion`);
            this.stopVisualMode();
            this.setCurrentFlow("sleep");
          }
        }, 1000);
      });
      
      detectionProcess.on("error", (error: Error) => {
        console.error(`[ChatFlow] Detection process error:`, error);
        this.stopVisualMode();
        this.setCurrentFlow("sleep");
      });
      
    } else if (visualMode.type === 'recording') {
      const videoPath = (visualMode as any).videoPath;
      const duration = (visualMode as any).duration;
      const recordingScript = (visualMode as any).recordingScript;
      
      console.log(`[ChatFlow] ========================================`);
      console.log(`[ChatFlow] RECORDING MODE - Starting video recording process`);
      console.log(`[ChatFlow] Preview frame path: ${visualMode.framePath}`);
      console.log(`[ChatFlow] Video path: ${videoPath}`);
      console.log(`[ChatFlow] Duration: ${duration ? duration + 's' : 'continuous'}`);
      console.log(`[ChatFlow] Script: ${recordingScript}`);
      console.log(`[ChatFlow] ========================================`);
      
      setVideoRecordingActive(true);
      this.currentFlowName = "recording";
      
      // Build recording command args
      const args = [recordingScript, videoPath];
      
      // Add optional parameters only if provided
      if (duration !== undefined) {
        args.push(String(duration), "1280", "720", "30");
      }
      // If no duration, Python script will record continuously (no additional args needed)
      
      // Start the recording process NOW (just like playback does)
      const { spawn } = require("child_process");
      const recordingProcess = spawn("python3", args);
      this.activeVisualProcess = recordingProcess; // Track it for cleanup
      
      recordingProcess.stdout?.on("data", (data: Buffer) => {
        console.log(`[Recorder]: ${data.toString().trim()}`);
      });
      
      recordingProcess.stderr?.on("data", (data: Buffer) => {
        console.error(`[Recorder ERROR]: ${data.toString().trim()}`);
      });
      
      recordingProcess.on("exit", (code: number) => {
        console.log(`[ChatFlow] ----------------------------------------`);
        console.log(`[ChatFlow] Recording process exited with code ${code}`);
        
        // Verify the file was created
        if (fs.existsSync(videoPath)) {
          const fileSizeBytes = fs.statSync(videoPath).size;
          const fileSizeMB = (fileSizeBytes / (1024 * 1024)).toFixed(2);
          console.log(`[ChatFlow] Video recorded successfully: ${videoPath} (${fileSizeMB}MB)`);
          
          // Send video to Telegram
          telegramBot.sendVideo(videoPath);
        } else {
          console.error(`[ChatFlow] Video file was not created: ${videoPath}`);
        }
        
        // Auto-stop visual mode after recording completes
        setTimeout(() => {
          if (this.visualModeInterval) {
            console.log(`[ChatFlow] Cleaning up after recording completion`);
            this.stopVisualMode();
            this.setCurrentFlow("sleep");
          }
        }, 1000); // Give 1 second to see the last frame
      });
      
      recordingProcess.on("error", (error: Error) => {
        console.error(`[ChatFlow] Recording process error:`, error);
        this.stopVisualMode();
        this.setCurrentFlow("sleep");
      });
      
    } else if (visualMode.type === 'pose') {
      const poseScript = (visualMode as any).poseScript;
      const poseAction = (visualMode as any).poseAction || "detect";
      const poseCount = (visualMode as any).poseCount;
      const poseGoal = (visualMode as any).poseGoal;
      const poseRecord = (visualMode as any).poseRecord;
      
      console.log(`[ChatFlow] ========================================`);
      console.log(`[ChatFlow] POSE MODE - Starting pose estimation process`);
      console.log(`[ChatFlow] Frame path: ${visualMode.framePath}`);
      console.log(`[ChatFlow] Action: ${poseAction}`);
      console.log(`[ChatFlow] Counting: ${poseCount}`);
      console.log(`[ChatFlow] Goal: ${poseGoal || 'None'}`);
      console.log(`[ChatFlow] Recording: ${poseRecord || false}`);
      console.log(`[ChatFlow] Script: ${poseScript}`);
      console.log(`[ChatFlow] ========================================`);
      
      setLiveDetectionActive(true); // Reuse flag for visual mode
      this.currentFlowName = "pose";
      
      // Build pose command args
      const args = [poseScript, "--action", poseAction, "--visualize"];
      if (poseCount) {
        args.push("--count");
      }
      if (poseGoal) {
        args.push("--goal", String(poseGoal));
      }
      if (poseRecord) {
        args.push("--record");
      }
      
      // Start the pose process
      const { spawn } = require("child_process");
      const poseProcess = spawn("python3", args);
      this.activeVisualProcess = poseProcess;
      
      poseProcess.stdout?.on("data", (data: Buffer) => {
        const line = data.toString().trim();
        
        // Handle audio feedback for down state
        if (line.includes("JSON_AUDIO:down")) {
          console.log(`[Pose] Down detected`);
          ttsProcessor("down").catch((e: Error) => 
            console.error("[Pose] TTS error:", e)
          );
        }
        
        // Handle rep progress updates
        if (line.includes("JSON_PROGRESS:")) {
          try {
            const jsonStr = line.split("JSON_PROGRESS:")[1];
            const progress = JSON.parse(jsonStr);
            console.log(`[Pose] Rep ${progress.reps}${progress.goal ? `/${progress.goal}` : ''}`);
            
            // Speak the count
            ttsProcessor(progress.reps.toString()).catch((e: Error) => 
              console.error("[Pose] TTS error:", e)
            );
          } catch (e) {
            console.error("[Pose] Error parsing progress:", e);
          }
        }
        
        // Handle goal reached or pose trigger
        if (line.includes("JSON_TRIGGER:")) {
          try {
            const jsonStr = line.split("JSON_TRIGGER:")[1];
            const event = JSON.parse(jsonStr);
            
            if (event.event === "goal_reached") {
              console.log(`[Pose] Goal reached: ${event.reps} reps!`);
              const message = `Great job! You completed ${event.reps} ${poseAction}s!`;
              ttsProcessor(message);
              telegramBot.sendMessage(`🎉 ${message}`);
            } else if (event.event === "pose_detected") {
              console.log(`[Pose] Pose detected:`, event);
              const message = `I detected someone ${event.action}!`;
              ttsProcessor(message);
              telegramBot.sendMessage(`👋 ${message}`);
              if (event.image_path && fs.existsSync(event.image_path)) {
                telegramBot.sendPhoto(event.image_path);
              }
            }
          } catch (e) {
            console.error("[Pose] Error parsing trigger:", e);
          }
        }
        
        // Handle video saved event
        if (line.includes("JSON_VIDEO:")) {
          try {
            const jsonStr = line.split("JSON_VIDEO:")[1];
            const event = JSON.parse(jsonStr);
            
            if (event.event === "video_saved" && event.video_path) {
              console.log(`[Pose] Exercise video saved: ${event.video_path}`);
              const message = `Your ${event.action} workout video with ${event.reps} reps has been saved!`;
              telegramBot.sendMessage(`🎬 ${message}`);
              
              // Send video to Telegram
              if (fs.existsSync(event.video_path)) {
                telegramBot.sendVideo(event.video_path);
              }
            }
          } catch (e) {
            console.error("[Pose] Error parsing video event:", e);
          }
        }
      });
      
      poseProcess.stderr?.on("data", (data: Buffer) => {
        const msg = data.toString().trim();
        if (msg.includes("Starting") || msg.includes("Rep") || msg.includes("Goal") || msg.includes("Model") || msg.includes("State")) {
          console.log(`[Pose]: ${msg}`);
        }
      });
      
      poseProcess.on("exit", (code: number) => {
        console.log(`[ChatFlow] ----------------------------------------`);
        console.log(`[ChatFlow] Pose process exited with code ${code}`);
        
        // Auto-stop visual mode after pose completes
        setTimeout(() => {
          if (this.visualModeInterval) {
            console.log(`[ChatFlow] Cleaning up after pose completion`);
            this.stopVisualMode();
            this.setCurrentFlow("sleep");
          }
        }, 1000);
      });
      
      poseProcess.on("error", (error: Error) => {
        console.error(`[ChatFlow] Pose process error:`, error);
        this.stopVisualMode();
        this.setCurrentFlow("sleep");
      });
      
    } else if (visualMode.type === 'playback') {
      // isVideoPlaying is already set by setVideoPlaybackMarker
      this.currentFlowName = "videoPlayback";
      
      // Start the video playback process
      // framePath contains the video file path for playback mode
      const videoPath = visualMode.framePath;
      const VIDEO_PLAYER_SCRIPT = resolve(__dirname, "../../python/video_player_lcd.py");
      const VIDEO_FRAME_PATH = "/tmp/whisplay_current_video_frame.jpg";
      
      console.log(`[ChatFlow] ----------------------------------------`);
      console.log(`[ChatFlow] PLAYBACK MODE - Starting video playback process`);
      console.log(`[ChatFlow] Video path: ${videoPath}`);
      console.log(`[ChatFlow] Script: ${VIDEO_PLAYER_SCRIPT}`);
      console.log(`[ChatFlow] Video file exists:`, fs.existsSync(videoPath));
      console.log(`[ChatFlow] Video file size:`, fs.existsSync(videoPath) ? fs.statSync(videoPath).size : 'N/A');
      
      const { spawn } = require("child_process");
      const playbackProcess = spawn("python3", [VIDEO_PLAYER_SCRIPT, "play", videoPath]);
      this.activeVisualProcess = playbackProcess; // Track it for cleanup
      
      playbackProcess.stdout?.on("data", (data: Buffer) => {
        console.log(`[Video Player]: ${data.toString().trim()}`);
      });
      
      playbackProcess.stderr?.on("data", (data: Buffer) => {
        console.error(`[Video Player ERROR]: ${data.toString().trim()}`);
      });
      
      playbackProcess.on("exit", (code: number) => {
        const endTime = Date.now();
        const duration = ((endTime - startTime) / 1000).toFixed(2);
        console.log(`[ChatFlow] ----------------------------------------`);
        console.log(`[ChatFlow] Video playback exited with code ${code}`);
        console.log(`[ChatFlow] Playback duration: ${duration}s`);
        console.log(`[ChatFlow] Keeping last frame visible for 3 more seconds...`);
        // Don't auto-stop, let user press button or wait for natural end
        // Just clear the interval after a delay to show last frame
        setTimeout(() => {
          if (this.visualModeInterval) {
            console.log(`[ChatFlow] Cleaning up after playback completion`);
            this.stopVisualMode();
            this.setCurrentFlow("sleep");
          }
        }, 3000); // Give 3 seconds to see the last frame
      });
      
      playbackProcess.on("error", (error: Error) => {
        console.error(`[ChatFlow] Playback process error:`, error);
        this.stopVisualMode();
        this.setCurrentFlow("sleep");
      });
      
      // Update framePath to the actual frame marker
      visualMode.framePath = VIDEO_FRAME_PATH;
    }
    
    // Get color based on mode
    const colorMap = {
      detection: "#00FFFF",  // Cyan
      recording: "#FF0000",  // Red
      playback: "#0000FF",   // Blue
      pose: "#FF00FF",       // Magenta for pose
    };
    const RGB = colorMap[visualMode.type as keyof typeof colorMap] || "#FFFFFF";
    
    // Clear all display elements first
    display({
      status: "",
      RGB,
      text: "",
      emoji: "",
      image: "",
    });
    
    // Start updating display with frames
    let frameCheckCount = 0;
    let frameDisplayCount = 0;
    let lastFrameSize = 0;
    
    console.log(`[ChatFlow] Starting frame update interval (${visualMode.type === 'playback' ? '30ms' : '100ms'})`);
    
    this.visualModeInterval = setInterval(() => {
      frameCheckCount++;
      
      // Always try to update display, even if file doesn't exist (will clear if needed)
      try {
        if (fs.existsSync(visualMode.framePath)) {
          const stats = fs.statSync(visualMode.framePath);
          const currentSize = stats.size;
          
          // Log frame updates occasionally
          if (currentSize !== lastFrameSize) {
            frameDisplayCount++;
            if (visualMode.type === 'recording') {
              // More verbose logging for recording to debug
              if (frameDisplayCount % 5 === 0 || frameDisplayCount <= 5) {
                console.log(`[ChatFlow] 🎥 RECORDING Frame #${frameDisplayCount} updated (size: ${currentSize} bytes, path: ${visualMode.framePath})`);
              }
            } else if (frameDisplayCount % 10 === 0 || frameDisplayCount <= 3) {
              console.log(`[ChatFlow] Frame #${frameDisplayCount} updated (size: ${currentSize} bytes)`);
            }
            lastFrameSize = currentSize;
          }
          
          // Always update display (file might be same but needs refresh)
          display({
            status: "",
            RGB,
            text: "",
            emoji: "",
            image: visualMode.framePath,
          });
        } else {
          if (frameCheckCount === 1) {
            console.log(`[ChatFlow] WARNING: Frame file does not exist yet: ${visualMode.framePath}`);
          } else if (visualMode.type === 'recording' && frameCheckCount % 10 === 0) {
            // Check periodically for recording mode if frames aren't appearing
            console.log(`[ChatFlow] ⏳ Still waiting for recording frames... (check #${frameCheckCount})`);
          }
        }
      } catch (error) {
        // File might be in the middle of being written, skip this frame
        if (frameCheckCount < 5) {
          console.log(`[ChatFlow] Frame check error:`, error);
        }
      }
    }, visualMode.type === 'playback' ? 30 : 100); // 30ms for playback (33 FPS max), 100ms for others
    
    console.log(`[ChatFlow] Visual mode initialized, waiting for frames...`);
    
    // Set button handler to stop visual mode
    onButtonPressed(() => {
      this.stopVisualMode();
      this.setCurrentFlow("listening");
    });
    onButtonReleased(noop);
  };

  stopVisualMode = (): void => {
    if (this.visualModeInterval) {
      clearInterval(this.visualModeInterval);
      this.visualModeInterval = null;
    }
    
    // Signal processes to stop via state file removal
    const stateFiles = [
      "/tmp/pose_state.json",
      "/tmp/observer_state.json",
      "/tmp/sentry_state.json"
    ];
    
    for (const stateFile of stateFiles) {
      try {
        if (fs.existsSync(stateFile)) {
          fs.unlinkSync(stateFile);
          console.log(`[ChatFlow] Removed ${stateFile} to signal stop`);
        }
      } catch (e) {
        // Ignore cleanup errors
      }
    }
    
    // Kill any active Python visual process (detection/recording/playback/pose)
    if (this.activeVisualProcess) {
      try {
        console.log(`[ChatFlow] Killing active visual process (PID: ${this.activeVisualProcess.pid})`);
        this.activeVisualProcess.kill("SIGTERM"); // Try graceful shutdown first
        
        // Force kill after 1 second if still alive
        setTimeout(() => {
          if (this.activeVisualProcess && !this.activeVisualProcess.killed) {
            console.log(`[ChatFlow] Force killing process (PID: ${this.activeVisualProcess.pid})`);
            this.activeVisualProcess.kill("SIGKILL");
          }
        }, 1000);
        
        this.activeVisualProcess = null;
      } catch (error) {
        console.error(`[ChatFlow] Error killing visual process:`, error);
        this.activeVisualProcess = null;
      }
    }
    
    // Clear state flags
    setLiveDetectionActive(false);
    setVideoRecordingActive(false);
    clearVideoPlayback();
    
    // Clean up temporary frame files
    const tempFiles = [
      "/tmp/whisplay_current_video_frame.jpg",
      "/tmp/whisplay_video_preview_latest.jpg",
      "/tmp/whisplay_detection_frame.jpg",
      "/tmp/whisplay_pose_frame.jpg",
      "/tmp/whisplay_observer_frame.jpg",
      "/tmp/whisplay_sentry_frame.jpg"
    ];
    
    tempFiles.forEach(file => {
      try {
        if (fs.existsSync(file)) {
          fs.unlinkSync(file);
        }
      } catch (error) {
        // Ignore cleanup errors
      }
    });
    
    // Clear display completely
    display({
      status: "idle",
      RGB: "#00c8a3",
      emoji: "✅",
      text: "Visual mode stopped",
      image: "",
    });
  };

  setCurrentFlow = (flowName: string): void => {
    console.log(`[${getCurrentTimeTag()}] switch to:`, flowName);
    switch (flowName) {
      case "sleep":
        this.currentFlowName = "sleep";
        onButtonPressed(() => {
          this.setCurrentFlow("listening");
        });
        onButtonReleased(noop);
        // Don't update display if any visual mode is active
        if (!isVisualModeActive()) {
          display({
            status: "idle",
            emoji: "😴",
            RGB: "#000055",
            ...(getCurrentStatus().text === "Listening..."
              ? {
                  text: "Press the button to start",
                }
              : {}),
          });
        }
        break;
        case "listening":
          this.currentFlowName = "listening";
        this.currentRecordFilePath = `${
          this.recordingsDir
        }/user-${Date.now()}.${recordFileFormat}`;
        onButtonPressed(noop);
        const { result, stop } = recordAudioManually(
          this.currentRecordFilePath
        );
        onButtonReleased(() => {
          stop();
          display({
            RGB: "#ff6800", // yellow
          });
        });
        result.then(() => {
          this.setCurrentFlow("asr");
        });
        display({
          status: "listening",
          emoji: "😐",
          RGB: "#00ff00",
          text: "Listening...",
        });
        break;
      case "asr":
        this.currentFlowName = "asr";
        display({
          status: "recognizing",
        });
        Promise.race([
          recognizeAudio(this.currentRecordFilePath),
          new Promise<string>((resolve) => {
            onButtonPressed(() => {
              resolve("[UserPress]");
            });
            onButtonReleased(noop);
          }),
        ]).then((result) => {
          if (this.currentFlowName !== "asr") return;
          if (result === "[UserPress]") {
            this.setCurrentFlow("listening");
          } else {
            if (result) {
              console.log("Audio recognized result:", result);
              this.asrText = result;
              // Don't update display if any visual mode is active
              if (!isVisualModeActive()) {
                display({ status: "recognizing", text: result });
              }
              this.setCurrentFlow("answer");
            } else {
              this.setCurrentFlow("sleep");
            }
          }
        });
        break;
      case "answer":
        display({
          RGB: "#00c8a3",
        });
        this.currentFlowName = "answer";
        this.answerId += 1;
        const currentAnswerId = this.answerId;
        onButtonPressed(() => {
          this.setCurrentFlow("listening");
        });
        onButtonReleased(noop);
        const {
          partial,
          endPartial,
          getPlayEndPromise,
          stop: stopPlaying,
        } = this.streamResponser;
        this.partialThinking = "";
        this.thinkingSentences = [];
        let fullAnswer = "";
        chatWithLLMStream(
          [
            {
              role: "user",
              content: this.asrText,
            },
          ],
          (text) => {
            partial(text, currentAnswerId);
            fullAnswer += text;
          },
          () => endPartial(currentAnswerId),
          (partialThinking) =>
            this.partialThinkingCallback(partialThinking, currentAnswerId)
        );
        getPlayEndPromise().then(() => {
          if (this.currentFlowName === "answer") {
            // Send conversation to Telegram
            if (this.asrText && fullAnswer) {
              telegramBot.sendMessage(`User: ${this.asrText}\n\nOptidex: ${fullAnswer}`);
            }

            // Check for pending visual mode first
            const visualMode = getPendingVisualMode();
            const img = getLatestGenImg();
            
            console.log(`[ChatFlow] After TTS - visualMode:`, visualMode ? `${visualMode.type} @ ${visualMode.framePath}` : 'null');
            console.log(`[ChatFlow] After TTS - latestImg:`, img || 'null');
            
            if (visualMode) {
              // Start visual mode - similar to how images are handled
              console.log(`[ChatFlow] Starting visual mode from getPlayEndPromise`);
              this.startVisualMode(visualMode);
            } else if (img) {
              // Show generated/captured image
              display({
                image: img,
              });
              this.setCurrentFlow("image");
            } else {
              this.setCurrentFlow("sleep");
            }
          }
        });
        onButtonPressed(() => {
          stopPlaying();
          this.setCurrentFlow("listening");
        });
        onButtonReleased(noop);
        break;
      case "image":
        onButtonPressed(() => {
          display({ image: "" });
          this.setCurrentFlow("listening");
        });
        onButtonReleased(noop);
        break;
      default:
        console.error("Unknown flow name:", flowName);
        break;
    }
  };
}

export default ChatFlow;
