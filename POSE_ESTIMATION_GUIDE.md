# Pose Estimation Guide 🏃‍♂️

## Overview

Optidex now has **human pose estimation** capabilities using YOLOv8-Pose! It can detect body keypoints and recognize actions/gestures in real-time.

## Features

- ✅ **17 body keypoints detection** (nose, eyes, shoulders, elbows, wrists, hips, knees, ankles)
- ✅ **Gesture recognition** (waving, hands up)
- ✅ **Pose detection** (sitting, standing)
- ✅ **Real-time monitoring** with camera
- ✅ **Telegram alerts** with skeleton visualization
- ✅ **TTS announcements** when action detected

## Installation

The YOLOv8-Pose model will **auto-download** on first use (~6MB).

Or manually:
```bash
cd /home/dash/optidex
# Model downloads automatically, no action needed!
```

## Supported Actions

### 1. **Waving** 🤚
Detects when someone raises their hand (left or right)

**Use cases:**
- "Alert me when someone waves at the camera"
- "Let me know if someone is trying to get attention"

### 2. **Hands Up** 🙌
Detects when both hands are raised above shoulders

**Use cases:**
- "Tell me if someone raises both hands"
- "Detect surrender gesture"

### 3. **Sitting** 🪑
Detects when someone is in a seated position

**Use cases:**
- "Let me know when someone sits down"
- "Monitor if people are sitting at their desks"

### 4. **Standing** 🧍
Detects when someone is standing upright

**Use cases:**
- "Alert me when someone stands up"
- "Detect if someone is standing in the room"

### 5. **Detect (Any Action)** 👁️
Monitors for any of the above actions

**Use cases:**
- "Watch for any movement or gesture"
- "Let me know if someone does something"

## Voice Commands

### Start Detection

```
You: "Start pose detection for waving"
Bot: "Pose detection started. I am watching for: waving."

You: "Detect when someone raises both hands"
Bot: "Pose detection started. I am watching for: hands_up."

You: "Let me know if anyone sits down"
Bot: "Pose detection started. I am watching for: sitting."

You: "Watch for any pose or gesture"
Bot: "Pose detection started. I am watching for: any pose or action."
```

### Stop Detection

```
You: "Stop pose detection"
Bot: "Pose detection stopped."
```

## Technical Details

### Body Keypoints (COCO Format)

The model detects 17 keypoints:
```
0: nose
1: left_eye      2: right_eye
3: left_ear      4: right_ear
5: left_shoulder 6: right_shoulder
7: left_elbow    8: right_elbow
9: left_wrist    10: right_wrist
11: left_hip     12: right_hip
13: left_knee    14: right_knee
15: left_ankle   16: right_ankle
```

### How Actions Are Detected

**Waving:**
- Hand (wrist) is raised above shoulder by 30+ pixels
- Can detect left or right hand independently

**Hands Up:**
- Both wrists are above their respective shoulders
- At least 30 pixels separation

**Sitting:**
- Hips and knees detected
- Hip-to-knee vertical distance < 100 pixels (bent legs)

**Standing:**
- Hips positioned above knees
- At least 50 pixels vertical separation

### Performance

**On Raspberry Pi 5 (8GB):**
- Model: yolov8n-pose (~6MB)
- Speed: ~15-20 FPS
- Accuracy: Good for common poses
- RAM usage: ~500MB additional

**Detection Parameters:**
- Confidence threshold: 0.5 (50%)
- Consecutive detections required: 3
- Check interval: 0.5 seconds
- Cooldown after trigger: 3 seconds

## Usage Examples

### Example 1: Gesture Control

```
You: "Start detecting waving"
Bot: "Pose detection started. I am watching for: waving."
     [Wave at camera]
Bot: "👋 Alert: I detected someone waving! (left hand)"
     [Sends photo with skeleton to Telegram]
```

### Example 2: Activity Monitoring

```
You: "Let me know if someone sits down"
Bot: "Pose detection started. I am watching for: sitting."
     [Person sits in chair]
Bot: "👋 Alert: I detected someone sitting!"
     [Sends photo to Telegram]
```

### Example 3: Security/Presence Detection

```
You: "Watch for any movement"
Bot: "Pose detection started. I am watching for: any pose or action."
     [Someone enters and raises hand]
Bot: "👋 Alert: I detected someone waving!"
```

### Example 4: Fitness Tracking (Future)

*Coming soon: Count push-ups, squats, jumping jacks*

## File Structure

```
optidex/
├── python/
│   └── pose_estimation.py       # Main pose detection script
├── src/config/custom-tools/
│   └── pose-estimation.ts       # Tool integration
└── ~/ai-pi/captures/pose/       # Saved pose images
```

## Output

When an action is detected:

1. **TTS Announcement**: "Alert: I detected someone waving!"
2. **Telegram Message**: Text alert with details
3. **Telegram Photo**: Image with skeleton overlay
4. **Saved Image**: Stored in `~/ai-pi/captures/pose/`

### Example Image Names:
```
pose-waving-20241202-143022.jpg
pose-hands_up-20241202-143155.jpg
pose-sitting-20241202-143301.jpg
```

## Advanced Customization

### Adjust Detection Sensitivity

Edit `/home/dash/optidex/python/pose_estimation.py`:

```python
# Line ~30-60: Modify thresholds
if left_wrist[1] < left_shoulder[1] - 30:  # Change 30 to adjust sensitivity
```

### Change Consecutive Detections

```python
# In TypeScript tool, add parameter:
"--duration", "5"  # Require 5 consecutive detections instead of 3
```

### Disable Skeleton Visualization

```typescript
// In pose-estimation.ts, remove:
"--visualize"
```

## Troubleshooting

### Model Not Found

**Problem:** Model fails to load

**Solution:**
```bash
# Model auto-downloads, but if issues:
pip3 install --upgrade ultralytics
# Then try detection again
```

### Poor Detection Accuracy

**Problem:** Actions not recognized reliably

**Solutions:**
1. Improve lighting
2. Get closer to camera
3. Ensure full body is visible
4. Reduce background clutter
5. Wear contrasting clothing

### Slow Performance

**Problem:** Low FPS, laggy detection

**Solutions:**
1. Reduce camera resolution in script
2. Increase check interval (--interval 1.0)
3. Close other applications
4. Ensure good lighting (less processing needed)

## Future Enhancements

Planned features:

1. **Action counting** - Count push-ups, squats, etc.
2. **Pose sequences** - Detect multi-step actions
3. **Multiple people** - Track multiple persons simultaneously
4. **Custom poses** - Define your own pose patterns
5. **Fall detection** - Alert when someone falls
6. **Pose comparison** - Compare to reference poses
7. **Fitness coach** - Real-time form feedback

## Integration with Other Tools

### Combine with Semantic Sentry

```
You: "Tell me if a person waves while standing near the couch"
Bot: [Uses pose detection + object detection together]
```

### Combine with Smart Observer

```
You: "When someone waves, take a photo and describe them"
Bot: [Triggers camera + vision analysis on gesture]
```

## Use Cases

### Home Automation
- Wave to turn on lights
- Hands up to activate security mode
- Sitting detected → pause music

### Fitness Tracking
- Count exercises automatically
- Monitor form and posture
- Track workout sessions

### Security & Monitoring
- Detect unusual poses (falling)
- Alert when someone enters and waves
- Monitor activity patterns

### Accessibility
- Gesture-based commands for disabled users
- Non-verbal communication detection
- Activity assistance alerts

## Summary

**What's Added:**
- ✅ 2 new tools (`startPoseDetection`, `stopPoseDetection`)
- ✅ Real-time human pose estimation
- ✅ 5 action types (waving, hands_up, sitting, standing, detect)
- ✅ Skeleton visualization
- ✅ Telegram alerts with images
- ✅ ~15 FPS on Pi5

**Setup:**
```bash
cd /home/dash/optidex
npm run build
bash run_chatbot.sh

# Try it:
"Start detecting waving"
```

**Detect Actions:**
- Waving, hands up, sitting, standing, or any action
- Real-time camera monitoring
- Automatic alerts and notifications

Enjoy your new pose estimation capabilities! 🏃‍♂️🙌👋


