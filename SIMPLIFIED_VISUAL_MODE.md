# Simplified Visual Mode Architecture

## Problem Solved

Previously, visual modes (live detection, video recording preview, video playback) used a complex coordinator system with separate flows and manual interval management. This was overly complicated compared to how images are handled.

**User feedback:** "visualCoordinator by itself doesn't work. If you look at the getPlayEndPromise function, if its an img it just calls the display function and passes the img to it. Can we do something similar?"

## Solution: Treat Visual Modes Like Images

Visual modes now work **exactly like images** - simple, clean, and managed in one place (ChatFlow).

### Architecture Overview

```
Tool Call → Sets Pending Visual Mode → TTS Completes → ChatFlow Starts Visual Mode → Display Updates
```

### Key Changes

#### 1. Unified Visual Mode Type (`src/utils/image.ts`)

```typescript
export type VisualMode = {
  type: 'detection' | 'recording' | 'playback'
  framePath: string
}

let pendingVisualMode: VisualMode | null = null

export const setPendingVisualMode = (mode: VisualMode | null) => {
  pendingVisualMode = mode
}

export const getPendingVisualMode = (): VisualMode | null => {
  const mode = pendingVisualMode
  pendingVisualMode = null  // Consume on read
  return mode
}
```

#### 2. ChatFlow Handles Everything (`src/core/ChatFlow.ts`)

**After TTS completes:**
```typescript
getPlayEndPromise().then(() => {
  if (this.currentFlowName === "answer") {
    // Check for pending visual mode first
    const visualMode = getPendingVisualMode();
    const img = getLatestGenImg();
    
    if (visualMode) {
      // Start visual mode - similar to how images are handled
      this.startVisualMode(visualMode);
    } else if (img) {
      // Show generated/captured image
      display({ image: img });
      this.setCurrentFlow("image");
    } else {
      this.setCurrentFlow("sleep");
    }
  }
});
```

**Visual mode display (single method for all types):**
```typescript
startVisualMode = (visualMode: { type: string; framePath: string }): void => {
  console.log(`[ChatFlow] Starting visual mode: ${visualMode.type}`);
  
  // Stop any existing visual mode
  this.stopVisualMode();
  
  // Set appropriate state flags
  if (visualMode.type === 'detection') {
    setLiveDetectionActive(true);
    this.currentFlowName = "detection";
  } else if (visualMode.type === 'recording') {
    setVideoRecordingActive(true);
    this.currentFlowName = "recording";
  } else if (visualMode.type === 'playback') {
    this.currentFlowName = "videoPlayback";
  }
  
  // Get color based on mode
  const colorMap = {
    detection: "#00FFFF",  // Cyan
    recording: "#FF0000",  // Red
    playback: "#0000FF",   // Blue
  };
  const RGB = colorMap[visualMode.type];
  
  // Clear any text first
  display({ RGB, text: "", emoji: "", image: "" });
  
  // Start updating display with frames
  this.visualModeInterval = setInterval(() => {
    if (fs.existsSync(visualMode.framePath)) {
      display({ RGB, image: visualMode.framePath });
    }
  }, visualMode.type === 'playback' ? 50 : 100);
  
  // Set button handler to stop
  onButtonPressed(() => {
    this.stopVisualMode();
    this.setCurrentFlow("listening");
  });
};
```

#### 3. Tools Just Set Pending Mode

**Video Recording (`src/config/custom-tools/video.ts`):**
```typescript
// Before: Complex coordinator calls, manual intervals, state management
// After: Just set the pending mode!

setPendingVisualMode({
  type: 'recording',
  framePath: RECORDING_PREVIEW_FRAME
});
```

**Video Playback:**
```typescript
setPendingVisualMode({
  type: 'playback',
  framePath: VIDEO_FRAME_PATH
});
```

**Live Detection (`src/config/custom-tools/live-detection.ts`):**
```typescript
setPendingVisualMode({
  type: 'detection',
  framePath: DETECTION_FRAME
});
```

### What Was Removed

❌ **visualCoordinator.ts** - No longer needed!
- `startDetectionDisplay()`
- `stopDetectionDisplay()`
- `startRecordingDisplay()`
- `stopRecordingDisplay()`
- `startPlaybackDisplay()`
- `stopPlaybackDisplay()`
- `stopAllDisplays()`

❌ **Separate flow cases in ChatFlow:**
- `case "detection":` removed
- `case "recording":` removed
- `case "videoPlayback":` removed

❌ **Manual interval management in tools:**
- Tools no longer manage `setInterval`
- Tools no longer call `display()` directly
- Tools no longer track display state

### Benefits

✅ **Simpler** - One place manages all visual display logic (ChatFlow)
✅ **Consistent** - Visual modes work exactly like images
✅ **Less Code** - Removed entire coordinator layer
✅ **Easier to Maintain** - Clear flow: Tool → Pending → ChatFlow → Display
✅ **No Race Conditions** - ChatFlow waits for TTS naturally via `getPlayEndPromise()`

### How It Works

#### Example: Record a Video

1. **User:** "Record a video for 10 seconds"

2. **Tool executes:**
   ```typescript
   // Start Python recording process
   spawn("python3", [VIDEO_CAPTURE_SCRIPT, ...]);
   
   // Set pending mode
   setPendingVisualMode({
     type: 'recording',
     framePath: RECORDING_PREVIEW_FRAME
   });
   
   return "[success]Starting video recording";
   ```

3. **TTS speaks:** "Starting video recording"
   - During TTS: `isVisualModeActive()` returns `false` (not started yet)
   - `hasVisualPending()` returns `true` (blocks new TTS text)

4. **TTS completes:** `getPlayEndPromise().then()` runs
   ```typescript
   const visualMode = getPendingVisualMode();
   // Returns: { type: 'recording', framePath: '/tmp/whisplay_video_preview_latest.jpg' }
   
   this.startVisualMode(visualMode);
   ```

5. **ChatFlow starts visual mode:**
   - Sets `setVideoRecordingActive(true)`
   - Clears text from display
   - Starts interval to update display with frames
   - Sets button handler to stop on press

6. **Display updates:**
   - Every 100ms, checks if frame exists
   - If exists, sends to display with RED color
   - Live preview shows on LCD!

7. **User presses button:**
   - `stopVisualMode()` called
   - Clears interval
   - Clears state flags
   - Returns to listening mode

### Frame Paths

| Visual Mode | Frame Path | Update Rate |
|-------------|-----------|-------------|
| Detection | `/tmp/whisplay_detection_frame.jpg` | 100ms |
| Recording | `/tmp/whisplay_video_preview_latest.jpg` | 100ms |
| Playback | `/tmp/whisplay_current_video_frame.jpg` | 50ms |

### State Management

**State Flags** (for blocking TTS during visual modes):
- `isLiveDetectionActive` - Detection running
- `isRecordingActive` - Recording running
- `isVideoPlaying` - Playback running

**Pending State:**
- `pendingVisualMode` - Visual mode waiting to start after TTS

**Checks:**
```typescript
isVisualModeActive()  // Any visual mode currently displaying
hasVisualPending()    // Visual mode waiting to start
```

**TTS Gating:**
```typescript
// In StreamResponser callbacks
if (isVisualModeActive() || hasVisualPending()) return;  // Don't update display
```

### Comparison: Before vs After

#### Before (Complex):
```typescript
// Tool
startRecordingDisplay();  // Coordinator call
recordingInterval = setInterval(...);  // Manual interval
setVideoRecordingActive(true);  // State management

// ChatFlow
case "recording":
  this.currentFlowName = "recording";
  startRecordingDisplay();  // Redundant coordinator call
  onButtonPressed(() => {
    stopRecordingDisplay();
    this.setCurrentFlow("listening");
  });
  break;

// visualCoordinator
export const startRecordingDisplay = () => {
  setVideoRecordingActive(true);
  recordingInterval = setInterval(() => {
    if (fs.existsSync(RECORDING_PREVIEW_LATEST)) {
      display({ RGB: "#FF0000", image: RECORDING_PREVIEW_LATEST });
    }
  }, 150);
};
```

#### After (Simple):
```typescript
// Tool
setPendingVisualMode({
  type: 'recording',
  framePath: RECORDING_PREVIEW_FRAME
});

// ChatFlow (handles ALL visual modes)
if (visualMode) {
  this.startVisualMode(visualMode);  // One method for all types
}
```

### Testing

```bash
# Build
npm run build

# Restart
systemctl --user restart whisplay.service

# Test recording
"Record a video for 10 seconds"
→ TTS: "Starting video recording"
→ After TTS: Live preview shows (red border)
→ No text overlays during preview
→ Button stops recording

# Test playback
"Play the video"
→ TTS: "Starting video playback"
→ After TTS: Video plays (blue border)
→ No text overlays during playback
→ Button stops playback

# Test detection
"Start detecting person"
→ TTS: "Starting detection for person"
→ After TTS: Detection boxes show (cyan border)
→ No text overlays during detection
→ Button stops detection
```

### Summary

**The key insight:** Visual modes are just animated images. Treat them the same way - set a pending state, let ChatFlow handle display after TTS, use a simple interval to update frames.

**Result:** 
- ❌ Removed ~200 lines (visualCoordinator + separate flows)
- ✅ Added ~60 lines (unified startVisualMode)
- **Net: 140 lines removed, simpler architecture**

This matches how images work perfectly - clean, simple, maintainable. 🎉



