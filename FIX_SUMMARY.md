# Video Display Issue Fix

## Problem
When video recording, live detection, or video playback was active, the TTS response text from the LLM would appear on the display and block the actual video content.

## Root Cause
The `ChatFlow.ts` file had `isVisualModeActive()` guards on the TTS response display callbacks, but NOT on all state transition display updates:

1. **ASR Result Display** (line 151): After speech recognition completed, the recognized text was displayed without checking if visual modes were active
2. **Sleep Mode Display** (line 94): When transitioning to sleep/idle mode, the display update didn't check for active visual modes

These unguarded display updates would override the video frames being shown during detection/recording/playback.

## Solution
Added `isVisualModeActive()` guards to the two missing locations:

### 1. Sleep Mode Display (line 94-107)
```typescript
// Don't update display if any visual mode is active (detection/recording/playback)
if (!isVisualModeActive()) {
  display({
    status: "idle",
    emoji: "😴",
    RGB: "#000055",
    // ...
  });
}
```

### 2. ASR Result Display (line 154-157)
```typescript
// Don't update display if any visual mode is active (detection/recording/playback)
if (!isVisualModeActive()) {
  display({ status: "recognizing", text: result });
}
```

## How It Works
- Video tools (`video.ts`, `live-detection.ts`) set visual mode flags when starting:
  - `setLiveDetectionActive(true)`
  - `setVideoRecordingActive(true)`
  - `setVideoPlaybackMarker(path)`
  
- `isVisualModeActive()` checks if any of these flags are set

- ChatFlow now checks this flag before ALL text/status display updates

- Video frame update intervals continue to run uninterrupted, updating the display at 50-150ms intervals

## Testing
To test the fix:

1. **Live Detection**: 
   ```
   Say: "Start detecting person"
   [Video frames should display continuously]
   Say: "Hello" or any other command
   [Video should remain visible, not be replaced with text]
   ```

2. **Video Recording**:
   ```
   Say: "Record video for 10 seconds"
   [Preview frames should display throughout recording]
   [LLM response should not appear on screen]
   ```

3. **Video Playback**:
   ```
   Say: "Play the video"
   [Video frames should display continuously]
   [Text should not overlay the video]
   ```

## Files Modified
- `src/core/ChatFlow.ts` - Added visual mode guards to prevent text display during video operations
- Backup created: `src/core/ChatFlow.ts.backup`

## Build
Project rebuilt successfully with `npm run build`
