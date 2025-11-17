# Video Playback Fixes - Final Version

## Issues Fixed

### Issue 1: Auto-playback after recording shows blank screen
**Problem**: When user says "shoot a 5 sec video and play it back", the display stays blank during playback.

**Root Cause**: 
- The `recordVideoForDuration` tool was setting `pendingVisualMode` for 'recording' AFTER the recording completed
- This caused the recording preview to try to activate after the video was already recorded
- Created state conflicts when playback was immediately requested

**Fix**:
- Removed the `setPendingVisualMode` call from `recordVideoForDuration`
- Recording preview now happens during the actual recording process (handled by the Python script)
- This prevents state conflicts between recording and playback modes

### Issue 2: Manual playback shows only one frame for 5 seconds
**Problem**: When user explicitly asks to "play the last video", only one frame displays and doesn't update.

**Root Cause**: 
- Python display script (`chatbot-ui.py`) had conditional image cache clearing
- The condition `if image_path != current_image_path or current_image_path != ""` wasn't aggressive enough
- Video frames with the same path weren't being reloaded consistently

**Fix**:
- Changed image cache clearing to ALWAYS force reload when `image_path` is provided
- Now every frame update forces a fresh load from disk
- This ensures video frames are displayed as they're updated by the player

### Issue 3: Display not updating fast enough to show all frames
**Problem**: Video player was completing playback before display could show most frames.

**Fixes Applied**:
1. **Increased Python render FPS**: Changed from 30 FPS to 40 FPS (25ms per frame)
2. **Optimized frame checking**: ChatFlow checks for new frames every 30ms for playback
3. **Better frame detection**: Now tracks frame file size changes to detect updates
4. **Comprehensive logging**: Added detailed logs to track frame updates and playback progress

## Changes Made

### File: `python/chatbot-ui.py`
```python
# BEFORE:
if image_path is not None:
    if image_path != current_image_path or current_image_path != "":
        current_image = None  # Force reload on next render

# AFTER:
if image_path is not None:
    current_image = None  # Force reload on every frame update
```

```python
# BEFORE:
render_thread = RenderThread(whisplay, "NotoSansSC-Bold.ttf", fps=30)

# AFTER:
render_thread = RenderThread(whisplay, "NotoSansSC-Bold.ttf", fps=40)
```

### File: `src/config/custom-tools/video.ts`
```typescript
// REMOVED this line from recordVideoForDuration:
setPendingVisualMode({
  type: 'recording',
  framePath: RECORDING_PREVIEW_FRAME
});
```

### File: `src/core/ChatFlow.ts`

**Enhanced Logging**:
- Added comprehensive playback logs with timestamps
- Tracks frame updates by size changes
- Logs playback duration and frame count
- Clear visual separators in logs for easier debugging

**Improved Cleanup**:
- `stopVisualMode()` now deletes temporary frame files:
  - `/tmp/whisplay_current_video_frame.jpg`
  - `/tmp/whisplay_video_preview_latest.jpg`
  - `/tmp/whisplay_detection_frame.jpg`
- Prevents stale frames from previous operations

**Better Frame Detection**:
- Tracks frame file size to detect actual changes
- Logs every 10th frame update (or first 3 frames)
- Always calls `display()` even if frame hasn't changed (forces refresh)

## How It Works Now

### Recording Flow:
1. User: "Shoot a 5 second video"
2. Tool: `recordVideoForDuration(5)` executes
3. Python script records video and shows live preview during recording
4. Returns: "Video recorded for 5 seconds (2.7MB). Ready to play."
5. TTS speaks, then goes to sleep (no visual mode pending)

### Playback Flow:
1. User: "Play the video" or "Play it back"
2. Tool: `playVideo()` executes
3. Sets `setPendingVisualMode({ type: 'playback', framePath: videoPath })`
4. Returns: "Starting video playback"
5. TTS speaks
6. After TTS completes, `ChatFlow.startVisualMode()` is called:
   - Spawns `python/video_player_lcd.py` process
   - Player extracts frames to `/tmp/whisplay_current_video_frame.jpg`
   - ChatFlow updates display every 30ms with the current frame
   - Python render thread updates LCD every 25ms (40 FPS)
   - Video plays smoothly with frame-by-frame updates

### Combined Flow (shoot + play):
1. User: "Shoot a 5 sec video and play it back"
2. LLM calls both tools in sequence:
   - `recordVideoForDuration(5)` → "Video recorded..."
   - `playVideo()` → "Starting video playback"
3. After final TTS, playback visual mode activates
4. Video plays normally with all frames

## Testing

To test the fixes:

1. **Test recording preview**:
   ```
   "Shoot a 10 second video"
   ```
   Should show live camera preview during recording.

2. **Test playback**:
   ```
   "Play the last video"
   ```
   Should play all frames smoothly.

3. **Test combined**:
   ```
   "Shoot a 5 second video and play it back"
   ```
   Should record, then play back the video with all frames visible.

4. **View logs**:
   ```bash
   tail -f chatbot_output.log
   ```
   Look for:
   - `[ChatFlow] Starting visual mode: playback`
   - `[Video Player]: Extracted 138 frames`
   - `[ChatFlow] Frame #10 updated (size: XXXX bytes)`
   - `[ChatFlow] Video playback exited with code 0`

## Performance Improvements

- **Frame update rate**: 30ms (33 FPS) for playback mode
- **Display render rate**: 25ms (40 FPS) in Python
- **Cache behavior**: Always reload images to ensure fresh frames
- **Cleanup**: Automatic removal of temporary frame files

## Known Behavior

- After video playback completes, the last frame stays visible for 3 seconds
- Button press during playback stops the video immediately
- Blank screen between TTS completion and first frame is normal (<100ms)


