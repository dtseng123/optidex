# Tool Updates - Complete

## Changes Applied

Successfully updated both visual mode tool files to follow the **defer-display-until-after-TTS** pattern.

## Files Updated

### 1. `src/config/custom-tools/live-detection.ts`

**Key Changes:**
- ✅ Removed `setLiveDetectionActive(true)` call (coordinator handles this)
- ✅ Removed `detectionUpdateInterval = setInterval(...)` block
- ✅ Removed manual display updates and interval management
- ✅ Added `setPendingDetection("active")` before returning
- ✅ Imported and used `stopDetectionDisplay()` in stop function
- ✅ Simplified exit handler to only manage process cleanup

**What happens now:**
1. Tool starts detection process → Sets pending marker → Returns
2. LLM generates brief TTS response
3. TTS completes → ChatFlow checks marker → Switches to "detection" flow
4. ChatFlow calls `startDetectionDisplay()` → Frame updates begin
5. Detection runs uninterrupted until stopped

### 2. `src/config/custom-tools/video.ts`

**Key Changes:**

**For `recordVideoForDuration`:**
- ✅ Removed `setVideoRecordingActive(true)` call
- ✅ Removed preview interval setup block
- ✅ Added `setPendingRecording("recording")` before command
- ✅ Uses `stopRecordingDisplay()` after completion

**For `startVideoRecording`:**
- ✅ Removed `setVideoRecordingActive(true)` call
- ✅ Removed preview interval setup block
- ✅ Added `setPendingRecording("recording")` before returning

**For `stopVideoRecording`:**
- ✅ Uses `stopRecordingDisplay()` from coordinator
- ✅ Removed manual interval cleanup

**For `playVideo`:**
- ✅ Removed `setTimeout` wrapper and interval setup
- ✅ Process spawns immediately but display handled separately
- ✅ Simply calls `setVideoPlaybackMarker(VIDEO_FRAME_PATH)`
- ✅ Process exit handler calls `stopPlaybackDisplay()`

**For `stopVideo`:**
- ✅ Uses `stopPlaybackDisplay()` from coordinator
- ✅ Removed manual interval cleanup

## Before vs After Flow

### BEFORE (Broken):
```
User: "Start detecting person"
  ↓
Tool: Start process + setInterval (display frames immediately)
  ↓
LLM: Generate TTS "I'll start detecting people"
  ↓
TTS: Display text updates OVERRIDE video frames ❌
  ↓
Result: Text blocks video
```

### AFTER (Fixed):
```
User: "Start detecting person"
  ↓
Tool: Start process + setPendingDetection("active")
  ↓
LLM: Generate TTS "Starting detection"
  ↓
TTS: Plays (hasVisualPending()=true, so no text display)
  ↓
TTS completes → ChatFlow checks getPendingDetection()
  ↓
ChatFlow: setCurrentFlow("detection")
  ↓
startDetectionDisplay() → setInterval starts
  ↓
Result: Video frames display continuously ✅
```

## Testing Checklist

Run through these test scenarios:

### ✅ Live Detection
```bash
# Test 1: Start detection
Say: "Start detecting person"
Expected: Brief/no TTS display → Detection frames appear immediately after
Expected: Frames update smoothly, no text overlay

# Test 2: Talk during detection
Say: "What time is it?" (while detection running)
Expected: Detection continues, no TTS text blocks video

# Test 3: Stop detection
Say: "Stop detection"
Expected: Frames stop, brief success message, return to idle
```

### ✅ Video Recording
```bash
# Test 1: Record for duration
Say: "Record video for 10 seconds"
Expected: Brief/no TTS display → Preview frames appear
Expected: Recording completes after 10 seconds

# Test 2: Continuous recording
Say: "Start recording video"
Expected: Preview frames appear immediately after TTS
Say: "Stop recording"
Expected: Recording stops, success message
```

### ✅ Video Playback
```bash
# Test 1: Play video
Say: "Play the video"
Expected: Brief/no TTS display → Video frames play
Expected: Smooth playback, no text overlay

# Test 2: Stop video
Say: "Stop video"
Expected: Playback stops, success message
```

### ✅ Image Generation (Should Still Work)
```bash
Say: "Draw a cat"
Expected: TTS plays, then image displays (same as before)
```

## Architecture Summary

**Now all visual modes follow the same pattern:**

| Mode | Tool Action | After TTS | Display Manager |
|------|-------------|-----------|-----------------|
| **Image** | `setLatestGenImg()` | `display({ image })` | One-time display |
| **Detection** | `setPendingDetection()` | `startDetectionDisplay()` | Interval (100ms) |
| **Recording** | `setPendingRecording()` | `startRecordingDisplay()` | Interval (150ms) |
| **Playback** | `setVideoPlaybackMarker()` | `startPlaybackDisplay()` | Interval (50ms) |

**All intervals managed centrally by `visualCoordinator.ts`**

## Rollback Instructions

If you need to rollback:

```bash
# Restore from backups
cp src/config/custom-tools/live-detection.ts.backup src/config/custom-tools/live-detection.ts
cp src/config/custom-tools/video.ts.backup src/config/custom-tools/video.ts

# Rebuild
npm run build
```

## Build Status

✅ **Build successful** - All TypeScript compiles without errors

## Next Steps

1. **Test each mode** using the checklist above
2. **Verify** TTS doesn't block video display
3. **Check** button press interrupts work correctly
4. If issues arise, check logs for flow transitions and marker setting

---

**The fix is complete!** Video display should now work exactly like image generation - TTS plays, then visual content displays without interruption.
