# Visual Mode Display Fix - Complete Solution

## Problem Summary
Video recording, live detection, and video playback were being blocked by TTS text responses. The image generation path works correctly, but video paths don't.

## Root Cause Analysis

### Why Image Generation Works
1. Tool generates image → `setLatestGenImg(path)` → Returns success
2. LLM generates TTS response
3. TTS plays (display shows text)
4. **AFTER TTS completes**, `ChatFlow.getPlayEndPromise()` triggers
5. Checks `getLatestGenImg()` → displays image → switches to "image" flow
6. Image stays on screen, no TTS can interrupt

### Why Video/Detection Was Broken
1. Tool starts process → Starts display interval immediately → Returns success
2. LLM generates TTS response  
3. **TTS display updates OVERRIDE video frames** ← CONFLICT!
4. Video frames keep trying to update but get blocked by TTS

## Solution Architecture

### New Pattern: Defer Display Until After TTS

**Video/detection tools should follow the same pattern as image generation:**

1. Tool prepares operation (starts process if needed)
2. Tool sets "pending" marker (like `setPendingDetection("marker")`)
3. Tool returns success WITHOUT starting display
4. LLM generates (brief!) TTS response
5. TTS plays
6. **AFTER TTS**, ChatFlow checks pending markers
7. ChatFlow switches to visual flow and starts display updates
8. Visual display runs uninterrupted until stopped

## Implementation

### New Files Created

#### 1. `src/utils/image.ts` (Updated)
Added pending marker functions:
- `setPendingDetection(marker)` / `getPendingDetection()`
- `setPendingRecording(marker)` / `getPendingRecording()`
- `getVideoPlaybackMarker()` (modified to be retrieval-only)
- `hasVisualPending()` - checks if any visual mode is pending

#### 2. `src/utils/visualCoordinator.ts` (NEW)
Central coordinator for all visual display intervals:
- `startDetectionDisplay()` - Starts detection frame updates
- `startRecordingDisplay()` - Starts recording preview updates
- `startPlaybackDisplay()` - Starts video playback updates
- `stopDetectionDisplay()` / `stopRecordingDisplay()` / `stopPlaybackDisplay()`
- `stopAllDisplays()` - Cleanup helper

#### 3. `src/core/ChatFlow.ts` (Updated)
- Checks `hasVisualPending()` in TTS callbacks to prevent text display
- After TTS completes, checks for pending visual markers
- New flows: "detection", "recording", "videoPlayback"
- Each flow calls coordinator to start display, sets up button handlers

### How to Update Visual Tools

Tools need to follow this pattern:

```typescript
// OLD PATTERN (DON'T DO THIS)
export const startDetectionTool = {
  func: async (params) => {
    startDetectionProcess();
    
    // ❌ DON'T start interval immediately
    detectionInterval = setInterval(() => {
      display({ image: FRAME_PATH });
    }, 100);
    
    return "[success]Detection started";
  }
};

// NEW PATTERN (DO THIS)
import { setPendingDetection } from "../../utils/image";

export const startDetectionTool = {
  func: async (params) => {
    // Start the process (it will write frames to temp files)
    startDetectionProcess();
    
    // ✅ Set pending marker - DON'T start display
    setPendingDetection("detection_active");
    
    // Return success - LLM will generate brief TTS
    // After TTS, ChatFlow will check marker and start display
    return "[success]Starting detection";
  }
};
```

### Required Changes Per Tool

#### Live Detection Tool (`src/config/custom-tools/live-detection.ts`)

**Changes needed:**
1. Import `setPendingDetection` from `../../utils/image`
2. In `startLiveDetection` function:
   - Keep process spawning logic
   - **REMOVE** the `detectionUpdateInterval = setInterval(...)` block
   - **REMOVE** the `setLiveDetectionActive(true)` call (coordinator handles this)
   - **ADD** `setPendingDetection("active")` before returning
3. In `stopLiveDetection` function:
   - Import and call `stopDetectionDisplay()` from visualCoordinator
   - Keep process cleanup logic

#### Video Recording Tool (`src/config/custom-tools/video.ts`)

**For `recordVideoForDuration`:**
1. Import `setPendingRecording` from `../../utils/image`
2. Keep recording process/command execution
3. **REMOVE** the `previewUpdateInterval = setInterval(...)` block
4. **REMOVE** the `setVideoRecordingActive(true)` call
5. **ADD** `setPendingRecording("recording")` before returning

**For `startVideoRecording`:**
- Same pattern as above

**For `stopVideoRecording`:**
- Import and call `stopRecordingDisplay()` from visualCoordinator

**For `playVideo`:**
1. Import `setVideoPlaybackMarker` (already exists)
2. Keep video player process spawn logic
3. **REMOVE** the `playbackUpdateInterval = setInterval(...)` block
4. Call `setVideoPlaybackMarker(VIDEO_FRAME_PATH)`
5. Return success

**For `stopVideo`:**
- Import and call `stopPlaybackDisplay()` from visualCoordinator

## How It Works (Flow Diagram)

```
User says: "Start detecting person"
    ↓
[startLiveDetection tool called]
    ↓
1. Spawn Python detection process (writes frames to /tmp/)
2. setPendingDetection("active")
3. Return "[success]Starting detection"
    ↓
[LLM receives success, generates response]
    ↓
4. LLM: "I'll start detecting people for you"
5. TTS plays (brief, text might show on display)
    ↓
[TTS completes, getPlayEndPromise() triggers]
    ↓
6. ChatFlow checks getPendingDetection() → "active"
7. ChatFlow.setCurrentFlow("detection")
    ↓
[Detection flow activated]
    ↓
8. startDetectionDisplay() called
9. setInterval starts updating display with frames
10. Frames display continuously, no TTS can interrupt!
    ↓
User presses button OR says "stop"
    ↓
11. stopDetectionDisplay() called
12. Clear interval, stop process
13. Return to listening mode
```

## Testing

### Test Cases

**1. Live Detection:**
```bash
# Say: "Start detecting person"
# Expected: Brief TTS, then detection frames display continuously
# Say anything else while detecting
# Expected: Detection continues, no text overlay
```

**2. Video Recording:**
```bash
# Say: "Record video for 10 seconds"
# Expected: Brief TTS, then preview frames display
# Expected: Recording completes, shows success message briefly
```

**3. Video Playback:**
```bash
# Say: "Play the video"
# Expected: Brief TTS, then video frames play
# Expected: Video plays smoothly without text overlay
```

**4. Image Generation (should still work):**
```bash
# Say: "Draw a cat"
# Expected: TTS plays, then image displays (same as before)
```

## Benefits of This Approach

1. **Consistent Pattern**: All visual modes follow the same architecture as image generation
2. **Clean Separation**: Tools handle process management, ChatFlow handles display flow
3. **No Race Conditions**: Display only starts after TTS completes
4. **Centralized Control**: visualCoordinator manages all display intervals in one place
5. **Easy to Debug**: Clear flow from tool → pending marker → ChatFlow → coordinator
6. **Button Handling**: Each visual flow properly handles button presses to exit

## Files Modified Summary

- ✅ `src/utils/image.ts` - Added pending marker functions
- ✅ `src/utils/visualCoordinator.ts` - NEW coordinator module  
- ✅ `src/core/ChatFlow.ts` - Integrated pending markers and visual flows
- ⚠️ `src/config/custom-tools/live-detection.ts` - **NEEDS UPDATE** (remove intervals, add markers)
- ⚠️ `src/config/custom-tools/video.ts` - **NEEDS UPDATE** (remove intervals, add markers)

## Next Steps

1. Update `live-detection.ts` following the pattern above
2. Update `video.ts` following the pattern above
3. Test each visual mode
4. Verify TTS doesn't block video display
5. Verify button press exits visual modes cleanly
