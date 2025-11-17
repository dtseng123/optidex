

# Live Object Detection with YOLOE

## Overview

Your whisplay chatbot now has **live object detection** using [YOLOE (YOLO Everything)](https://core-electronics.com.au/guides/raspberry-pi/custom-object-detection-models-without-training-yoloe-and-raspberry-pi/) from Ultralytics! 

**What makes YOLOE amazing:**
- ✅ **No training required** - just describe what you want to detect
- ✅ **Text prompts** - detect "person", "cup", "phone" etc instantly
- ✅ **Real-time** - 10-15 FPS on Pi5 8GB RAM
- ✅ **Bounding boxes** - visual overlays on live camera feed
- ✅ **Thousands of objects** - can detect almost anything you describe

**Based on:** [Core Electronics YOLOE Guide](https://core-electronics.com.au/guides/raspberry-pi/custom-object-detection-models-without-training-yoloe-and-raspberry-pi/)

## Quick Start

### 1. Install YOLOE

```bash
cd /home/dash/whisplay-ai-chatbot
./setup-yoloe.sh
```

This installs:
- ultralytics Python package
- Auto-downloads yoloe-s.pt model (~22MB) on first use

### 2. Restart Chatbot

```bash
systemctl --user restart whisplay.service
```

### 3. Try It!

```
You: "Start live detection for person"
Bot: "Live detection started! Looking for: person"
     [LCD shows camera feed with GREEN boxes around detected people]

You: "Stop detection"
Bot: "Live detection stopped."
```

## Voice Commands

### Start Detection

**Single object:**
- "Start live detection for person"
- "Detect hands"
- "Look for cups"

**Multiple objects:**
- "Start detecting person, cup, and phone"
- "Look for hands and faces"
- "Detect laptop, keyboard, and mouse"

**Timed detection:**
- "Start detection for person for 30 seconds"
- "Detect cups for 1 minute"

### Stop Detection

- "Stop detection"
- "Stop live detection"
- "End detection"

## What Can YOLOE Detect?

According to the guide, YOLOE can detect **tens of thousands** of objects using text prompts. Here are common examples:

### People & Body Parts
- person, people, human
- hand, hands, fingers
- face, head
- arm, leg, foot

### Common Objects
- cup, mug, bottle, glass
- phone, smartphone, cellphone
- laptop, computer, keyboard, mouse
- book, notebook, pen, pencil
- bag, backpack, purse

### Furniture & Home
- chair, couch, sofa
- table, desk
- bed, pillow
- door, window
- lamp, light
- plant, flower

### Electronics
- monitor, screen, display
- remote, controller
- charger, cable
- headphones, earbuds
- camera

### Kitchen
- plate, bowl, spoon, fork, knife
- food, apple, banana, sandwich
- microwave, oven, refrigerator
- coffee maker

### Outdoor
- car, vehicle, truck
- bicycle, bike
- tree, grass
- dog, cat, bird
- ball, frisbee

### And Much More!
- Try describing anything - YOLOE breaks it down into visual concepts

## Technical Details

### Models for Pi5 8GB RAM

| Model | Size | Speed | Accuracy | Recommended |
|-------|------|-------|----------|-------------|
| yoloe-n.pt | ~5MB | ⭐⭐⭐⭐⭐ 20+ FPS | ⭐⭐ | Fast, lower quality |
| yoloe-s.pt | ~22MB | ⭐⭐⭐⭐ 10-15 FPS | ⭐⭐⭐⭐ | ✅ BEST BALANCE |
| yoloe-m.pt | ~50MB | ⭐⭐⭐ 5-8 FPS | ⭐⭐⭐⭐⭐ | Higher quality, slower |

**Default:** yoloe-s.pt (good balance for Pi5)

### How It Works

1. **Camera Stream** → Captures 640x480 frames at 15 FPS
2. **YOLOE Model** → Analyzes each frame for target objects
3. **Text Prompts** → You specify what to detect (e.g., "person", "cup")
4. **Visual Concepts** → Model breaks prompts into concepts (4 legs, furry, brown...)
5. **Detection** → Finds objects matching those concepts
6. **Bounding Boxes** → Draws green boxes around target objects
7. **LCD Display** → Shows annotated frame at 240x240 on screen
8. **Real-time** → Updates 10 times per second

### Performance

**On Pi5 8GB RAM with yoloe-s.pt:**
- Processing: 10-15 FPS
- Display: 10 FPS (100ms intervals)
- Camera: 640x480 @ 15 FPS
- Confidence threshold: 0.3 (adjustable)

**RAM Usage:**
- Model loaded: ~500MB
- Camera + processing: ~300MB
- Total: ~800MB additional RAM

## Usage Examples

### Example 1: Find Your Coffee Cup

```
You: "Start detecting cup"
Bot: "Live detection started! Looking for: cup"
     [Screen shows camera feed with green box around your coffee cup]
     [Box labeled: "cup 0.87" (87% confidence)]

You: "Stop detection"
Bot: "Live detection stopped."
```

### Example 2: Hand Gesture Detection

```
You: "Start live detection for hand"
Bot: "Live detection started! Looking for: hand"
     [Wave your hand - green box appears and follows it]
     [Perfect for gesture-based controls!]

You: "Stop detection"
```

### Example 3: Security Monitor

```
You: "Start detecting person for 60 seconds"
Bot: "Live detection started for 60 seconds! Looking for: person"
     [Monitors for people for 1 minute]
     [Automatically stops after 60 seconds]

Bot: "Detection stopped."
```

### Example 4: Object Counter

```
You: "Start detecting bottle and cup"
Bot: "Live detection started! Looking for: bottle, cup"
     [All bottles get green boxes]
     [All cups get green boxes]
     [Each labeled with confidence score]

You: "Stop detection"
```

### Example 5: Pet Detector

```
You: "Start live detection for dog and cat"
Bot: "Live detection started! Looking for: dog, cat"
     [Detects your pets in real-time]
     
You: "Stop detection"
```

## Visual Display

**On LCD Screen:**
- **Green boxes** → Your target objects (what you asked for)
- **Yellow boxes** → Other detected objects (if any)
- **Labels** → Object name + confidence score
- **Real-time** → Updates 10 times per second

**Example display:**
```
┌────────────────────────────┐
│                            │
│   ┏━━━━━━━━━┓              │
│   ┃ person  ┃              │
│   ┃  0.94   ┃              │
│   ┗━━━━━━━━━┛              │
│                            │
│        ┏━━━━━━━┓           │
│        ┃  cup  ┃           │
│        ┃ 0.82  ┃           │
│        ┗━━━━━━━┛           │
└────────────────────────────┘
```

## Advanced Usage

### Custom Confidence Threshold

Edit `python/live_detection.py`:

```python
# Line ~250 (in run_live_detection function)
confidence_threshold=0.3  # Change to 0.5 for higher confidence
```

Or pass as parameter in tool (requires code modification).

### Different Model Size

Edit `python/live_detection.py`:

```python
# Line ~120
model = YOLO('yoloe-s.pt')  # Change to 'yoloe-n.pt' or 'yoloe-m.pt'
```

### Custom Resolution

Edit `python/live_detection.py`:

```python
# Line ~135
main={"size": (640, 480)},  # Try (320, 240) for faster, (1280, 720) for better
```

## Integration with Other Tools

### Combine with Photos

```
You: "Take a picture"
Bot: [Takes photo]

You: "What do you see in the picture?"
Bot: [Uses vision model to analyze]

You: "Now start detecting person"
Bot: [Switches to live detection]
```

### Combine with Video

```
You: "Start detecting hand"
Bot: [Live detection running]

You: "Record a video for 10 seconds"
Bot: [Stops detection, records video]

You: "What's in the video?"
Bot: [Analyzes video frame]
```

## Troubleshooting

### Model Too Slow

**Problem:** Detection is laggy or slow

**Solutions:**
1. Use yoloe-n.pt (faster nano model)
2. Reduce resolution to 320x240
3. Close other applications
4. Lower confidence threshold
5. Reduce frame rate in camera config

### Model Not Found

**Problem:** `Error: Model file not found`

**Solution:**
```bash
# Models auto-download, but if issues:
pip3 install --upgrade ultralytics
# Then try detection again - it will download the model
```

### Out of Memory

**Problem:** Detection crashes or system freezes

**Solutions:**
1. Close other heavy apps
2. Use yoloe-n.pt (smallest model)
3. Add swap space (see VISION_MODELS_FOR_PI5.md)
4. Restart system: `sudo reboot`

### Poor Detection Quality

**Problem:** Missing objects or false detections

**Solutions:**
1. Improve lighting
2. Use more specific prompts ("red cup" vs "cup")
3. Try yoloe-m.pt for better accuracy
4. Lower confidence threshold
5. Get closer to objects

### Can't Detect Custom Object

**Problem:** YOLOE doesn't recognize specific object

**Try:**
1. Describe it differently ("smartphone" vs "phone")
2. Break it down ("black rectangle device" for phone)
3. Use image prompting (see guide - future feature)
4. Try common object names from COCO dataset

## Limitations

Based on the Core Electronics guide:

1. **Obscure Objects:** Can't reliably detect very unique/unusual objects
2. **Text Prompting:** Works best with common, well-defined visual concepts
3. **Speed vs Quality:** Trade-off between FPS and accuracy
4. **RAM Constraints:** Limited to smaller models on 8GB Pi5
5. **No Audio:** Detection is visual only (no sound alerts yet)

## Performance Optimization

### For Maximum Speed

```python
# Use nano model
model = YOLO('yoloe-n.pt')

# Lower resolution
main={"size": (320, 240)}

# Higher confidence threshold (fewer detections)
confidence_threshold=0.5
```

### For Maximum Accuracy

```python
# Use medium model (if you have RAM headroom)
model = YOLO('yoloe-m.pt')

# Higher resolution
main={"size": (1280, 720)}

# Lower confidence threshold
confidence_threshold=0.2
```

### Balanced (Default)

```python
model = YOLO('yoloe-s.pt')
main={"size": (640, 480)}
confidence_threshold=0.3
```

## Future Enhancements

Potential additions:

1. **Adjustable confidence** via voice command
2. **Object counting** - "How many cups do you see?"
3. **Alert on detection** - "Tell me when you see a person"
4. **Zone detection** - "Detect when hand enters left side"
5. **Image prompting** - Show YOLOE a custom object photo
6. **Detection logging** - Save detection events to file
7. **Multi-camera** - Detect on multiple camera feeds
8. **ONNX export** - Faster inference with optimized model

## Resources

- **YOLOE Guide:** [Core Electronics YOLOE Tutorial](https://core-electronics.com.au/guides/raspberry-pi/custom-object-detection-models-without-training-yoloe-and-raspberry-pi/)
- **Ultralytics Docs:** https://docs.ultralytics.com/
- **YOLO Models:** https://github.com/ultralytics/ultralytics
- **COCO Dataset:** Common objects YOLO is trained on

## Summary

**What's Added:**
- ✅ 2 new tools (`startLiveDetection`, `stopLiveDetection`)
- ✅ Real-time object detection with YOLOE
- ✅ Text-prompted detection (no training!)
- ✅ Visual bounding boxes on LCD
- ✅ 10-15 FPS on Pi5 8GB RAM
- ✅ Detect thousands of objects

**Setup:**
```bash
./setup-yoloe.sh
systemctl --user restart whisplay.service
```

**Try It:**
```
"Start detecting person"
"Stop detection"
```

**Detect Almost Anything:**
person, hand, face, cup, phone, laptop, dog, cat, chair, car, and thousands more!

Enjoy real-time object detection! 👁️📹🎯




