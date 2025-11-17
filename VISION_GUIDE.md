# Vision Capabilities - Complete Guide

## Overview

Your whisplay chatbot now has **computer vision** capabilities! It can analyze photos and videos using:
- **Online**: GPT-4o (OpenAI Vision API)
- **Offline**: llama3.2-vision (Ollama local model)

## Quick Start

### 1. Setup (One-Time)

```bash
./setup-vision.sh
```

This will:
- Check if Ollama is installed
- Offer to install llama3.2-vision:11b (~7GB)
- Configure vision tools

### 2. Use It!

**Take and analyze a photo:**
```
You: "Take a picture"
Bot: "I've taken a picture!"

You: "What do you see in the picture?"
Bot: [Analyzes with GPT-4o or llama3.2-vision]
     "I see a person sitting at a desk with a laptop..."
```

**Record and analyze video:**
```
You: "Record a video for 5 seconds"
Bot: [Records video with live preview]

You: "What's in the video?"
Bot: [Extracts frame and analyzes]
     "I can see..."
```

## Available Tools

### 1. `analyzeImage`

Analyzes the most recent photo (camera or AI-generated).

**Voice Commands:**
- "What do you see in the picture?"
- "Describe the image"
- "What objects are in the photo?"
- "Is there any text in the image?"
- "What colors are in the picture?"

**Parameters:**
- `question` (string): What to analyze about the image

**Example Questions:**
- "What do you see?"
- "Count how many people are in the image"
- "Is there a cat or dog in the picture?"
- "What is the person doing?"
- "Read any text visible in the image"
- "What's the main color scheme?"

### 2. `analyzeVideoFrame`

Extracts a frame from the most recent video and analyzes it.

**Voice Commands:**
- "What's in the video?"
- "Describe what happened in the video"
- "What did you see in the recording?"

**Parameters:**
- `question` (string): What to analyze about the video

**Note:** Currently analyzes frame 15 (about 0.5 seconds into the video). Future: analyze multiple frames.

## Technical Details

### Online Mode (GPT-4o)

**When:** WiFi connected
**Model:** `gpt-4o`
**Features:**
- Excellent object recognition
- Text reading (OCR)
- Scene understanding
- People/face detection
- Color analysis
- Spatial relationships

**How it works:**
1. Image converted to base64
2. Sent to OpenAI API with prompt
3. GPT-4o vision model analyzes
4. Response returned

### Offline Mode (llama3.2-vision)

**When:** No WiFi
**Model:** `llama3.2-vision:11b` (default)
**Size:** ~7GB
**Features:**
- Good object recognition
- Scene description
- Basic OCR
- Color detection

**Alternative models:**
- `llama3.2-vision:90b` - Better quality, needs GPU, ~55GB

**How it works:**
1. Image converted to base64
2. Sent to local Ollama API
3. Local vision model analyzes
4. Response returned

## Installation

### Install Ollama Vision Model

```bash
# Recommended: 11B model (7GB, CPU-friendly)
ollama pull llama3.2-vision:11b

# Or larger: 90B model (55GB, needs GPU)
ollama pull llama3.2-vision:90b
```

### Set Custom Model

Edit `.env`:
```bash
OLLAMA_VISION_MODEL=llama3.2-vision:11b
# or
OLLAMA_VISION_MODEL=llama3.2-vision:90b
```

## Usage Examples

### Example 1: Simple Analysis

```
You: "Take a picture"
Bot: "I've taken a picture!"

You: "What do you see?"
Bot: "I can see a workspace with a computer monitor displaying code,
     a keyboard, a mouse, and a coffee mug on a wooden desk."
```

### Example 2: Specific Questions

```
You: "Take a picture of my hand"
Bot: "I've taken a picture!"

You: "How many fingers am I holding up?"
Bot: "You're holding up three fingers."
```

### Example 3: Text Reading

```
You: "Take a picture of that sign"
Bot: "I've taken a picture!"

You: "Read the text in the image"
Bot: "The sign says 'Welcome to our store - Open 9am to 5pm'"
```

### Example 4: Video Analysis

```
You: "Record a 5 second video of me waving"
Bot: [Records video]

You: "What am I doing in the video?"
Bot: "In the video frame, you appear to be waving your hand
     in a friendly greeting gesture."
```

### Example 5: Object Detection

```
You: "Take a picture"
Bot: "I've taken a picture!"

You: "Are there any animals in the picture?"
Bot: "Yes, I can see a cat sitting on the couch."
```

## File Structure

**Vision Tool:**
- `src/config/custom-tools/vision.ts` - Vision tools implementation

**Dependencies:**
- GPT-4o: Already included in OpenAI API
- Ollama: Install vision model separately

**Image Sources:**
- Camera photos: `data/images/camera-*.jpg`
- AI generated: `data/images/*-image-*.jpg`
- Video frames: Extracted temporarily to `/tmp/`

## Conversation Flow

```
1. User takes photo/video
   ↓
2. User asks about it
   ↓
3. LLM detects vision tool needed
   ↓
4. Tool finds latest image/video
   ↓
5. Image sent to vision model
   (GPT-4o online or Ollama offline)
   ↓
6. Analysis result returned
   ↓
7. LLM incorporates in response
   ↓
8. TTS speaks answer
```

## Performance

### GPT-4o (Online)
- **Speed:** ~2-3 seconds
- **Quality:** Excellent
- **Cost:** ~$0.01 per image
- **Limits:** API rate limits apply

### llama3.2-vision:11b (Offline)
- **Speed:** ~10-15 seconds (CPU)
- **Speed:** ~3-5 seconds (GPU)
- **Quality:** Good
- **Cost:** Free (local)
- **Limits:** RAM/CPU dependent

## Advanced Usage

### Analyze Specific Image

By default, tools analyze the most recent image. To analyze a specific image, modify the tool to accept an image path parameter.

### Analyze Multiple Video Frames

Currently analyzes frame 15. To analyze multiple frames:

```typescript
// Extract frames at different timestamps
for (let frameNum of [15, 45, 75, 105]) {
  const extractCmd = `ffmpeg -i ${video} -vf "select=eq(n\\,${frameNum})" -vframes 1 frame_${frameNum}.jpg`;
  // Analyze each frame
}
```

### Batch Analysis

Analyze multiple images in sequence:

```typescript
const allImages = getRecentImages(5); // Last 5 images
for (const img of allImages) {
  const result = await analyzeImage(img, question);
  // Process results
}
```

## Troubleshooting

### Vision Model Not Found

**Problem:** `Ollama vision model not available`

**Solution:**
```bash
ollama pull llama3.2-vision:11b
```

### Slow Analysis (Offline)

**Problem:** Takes 15+ seconds to analyze

**Solutions:**
1. Use smaller model: `llama3.2-vision:11b` instead of `:90b`
2. Use GPU if available
3. Close other applications
4. Ensure sufficient RAM (8GB+ recommended)

### OpenAI Rate Limit

**Problem:** `Rate limit exceeded`

**Solution:**
- Wait a moment and try again
- Use offline mode (disconnect WiFi temporarily)

### No Images Found

**Problem:** `No images found. Take a photo first.`

**Solution:**
- Take a photo: "Take a picture"
- Or generate one: "Draw me a sunset"
- Check `data/images/` directory has files

## Environment Variables

```bash
# .env file

# Vision model for offline mode
OLLAMA_VISION_MODEL=llama3.2-vision:11b

# Ollama endpoint (default: localhost)
OLLAMA_ENDPOINT=http://localhost:11434

# OpenAI model (GPT-4o has vision)
OPENAI_LLM_MODEL=gpt-4o
```

## Future Enhancements

Planned improvements:

1. **Multi-frame video analysis** - Analyze entire video timeline
2. **Real-time analysis** - Analyze preview frames during recording
3. **Object tracking** - Track objects across video frames
4. **Face recognition** - Identify specific people
5. **Scene change detection** - Detect cuts/transitions in video
6. **Text extraction** - Full OCR with position data
7. **Image comparison** - Compare before/after photos
8. **Batch processing** - Analyze all photos in directory

## Model Comparison

| Feature | GPT-4o | llama3.2-vision:11b | llama3.2-vision:90b |
|---------|--------|---------------------|---------------------|
| Speed | ⭐⭐⭐ | ⭐⭐ | ⭐ |
| Quality | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| OCR | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| Objects | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Scenes | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Size | API | 7GB | 55GB |
| Cost | Paid | Free | Free |
| Internet | Required | No | No |

## Summary

**What's Added:**
- ✅ 2 vision tools (`analyzeImage`, `analyzeVideoFrame`)
- ✅ GPT-4o vision support (online)
- ✅ Ollama vision support (offline)
- ✅ Automatic model selection based on WiFi
- ✅ Photo and video analysis
- ✅ Setup script for easy installation

**Usage:**
```bash
# Setup
./setup-vision.sh

# Restart
systemctl --user restart whisplay.service

# Try it!
"Take a picture"
"What do you see?"
```

**Commands:**
- Take photo → Analyze
- Record video → Analyze frame
- Ask specific questions about visual content

Enjoy your new vision capabilities! 👁️📸🎥




