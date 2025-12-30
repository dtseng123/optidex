# Optidex

An AI-powered personal assistant device built on Raspberry Pi 5, featuring voice interaction, computer vision, memory systems, and a knowledge graph. Think of it as Jarvis in a pocket-sized form factor.

## Origins

This project is built upon and extends the excellent [Whisplay AI Chatbot](https://github.com/PiSugar/whisplay-ai-chatbot) by PiSugar. The original project provides the foundation for the display, audio, and basic chatbot functionality.

**Original Whisplay Resources:**
- [Whisplay HAT Repository](https://github.com/PiSugar/whisplay) - Audio/display drivers
- [Original Tutorial Video](https://www.youtube.com/watch?v=Nwu2DruSuyI)
- [Offline RPi 5 Build Tutorial](https://www.youtube.com/watch?v=kFmhSTh167U)

## Hardware

- **Raspberry Pi 5** (16GB RAM recommended for full features)
- **PiSugar Whisplay HAT** - LCD screen (240x280), speaker, microphone
- **PiSugar 3 Battery** - 1200mAh portable power
- **Coral USB Accelerator** (optional) - EdgeTPU for fast ML inference
- **Pi Camera Module** (optional) - For vision capabilities
- **Meshtastic Radio** (optional) - For mesh network communication

---

## Capabilities Overview

### Self-Contained (No External APIs Required)

These features work entirely offline using local models and processing:

| Feature | Description | Technology |
|---------|-------------|------------|
| **Local LLM** | Conversational AI without internet | Ollama (Llama, Mistral, etc.) |
| **Local ASR** | Speech-to-text transcription | Whisper (tiny/base/small) |
| **Local TTS** | Text-to-speech synthesis | Piper TTS |
| **Object Detection** | Real-time object detection with bounding boxes | YOLO + EdgeTPU |
| **Person Segmentation** | Semantic segmentation masks | EdgeTPU DeepLab |
| **Pose Estimation** | Human pose detection and tracking | MoveNet + EdgeTPU |
| **Exercise Counting** | Count push-ups, squats, pull-ups, crunches | Pose analysis |
| **Species Classification** | Identify birds, insects, plants | EdgeTPU iNaturalist models |
| **Product Classification** | Identify retail products | EdgeTPU product model |
| **Knowledge Base** | 6.9M Wikipedia articles searchable offline | SQLite + FTS5 |
| **Memory System** | Episodic memory with knowledge graph | NetworkX + JSON |
| **Video Recording** | Record and playback video clips | Picamera2 + FFmpeg |
| **Camera Capture** | Take photos and display on screen | Picamera2 |

### External Services (Require API Keys/Internet)

These features require external services or API keys:

| Feature | Description | Service Required |
|---------|-------------|------------------|
| **Cloud LLM** | Advanced conversational AI | OpenAI GPT-4, Google Gemini, Grok |
| **Cloud ASR** | High-quality speech recognition | Google, OpenAI Whisper API |
| **Cloud TTS** | Natural voice synthesis | OpenAI, Google, Volcengine |
| **Vision Analysis** | Describe images, answer questions | GPT-4o, Gemini Vision |
| **Image Generation** | Generate images from text | DALL-E, Gemini Imagen |
| **Web Search** | Real-time web information | Serper API |
| **Telegram Notifications** | Send alerts and photos | Telegram Bot API |

### Hardware-Dependent Features

These require specific additional hardware:

| Feature | Description | Hardware Required |
|---------|-------------|-------------------|
| **TPU Acceleration** | Fast ML inference | Coral USB Accelerator |
| **Camera Vision** | All camera-based features | Pi Camera Module |
| **Mesh Network** | Off-grid communication | Meshtastic radio device |
| **VR Passthrough** | Object detection in VR | VR headset with passthrough |

---

## Feature Details

### Voice Interaction
- Press button to speak, get spoken response
- Adjustable volume via voice command
- Conversation history with auto-reset after inactivity

### Computer Vision
- **Live Detection**: Real-time object detection with bounding boxes on display
- **Smart Observer**: Monitor for specific objects, alert when found
- **Semantic Sentry**: Detect interactions between objects (e.g., "dog on couch")
- **Object Search**: Find specific items by scanning with camera
- **Pose Detection**: Track human poses, detect actions (waving, hands up, sitting)
- **Exercise Counter**: Count reps for workouts with live feedback

### Memory & Intelligence
- **Episodic Memory**: Records observations with timestamps, objects detected, transcriptions
- **Knowledge Graph**: Entities, concepts, and relationships stored in graph structure
- **Mission System**: Create surveillance tasks, reminders, monitoring objectives
- **Memory Recall**: Query past events by date, time, or content
- **Local Knowledge Base**: 6.9M Wikipedia articles for offline factual queries

### Classification (TPU-Accelerated)
- **ImageNet**: 1,000 general object classes
- **Products**: 100,000 US retail products
- **Birds**: 965 species (iNaturalist)
- **Insects**: 1,022 species (iNaturalist)
- **Plants**: 2,102 species (iNaturalist)

### Mesh Networking (Meshtastic)
- List nodes on the mesh network
- Send/receive text messages
- View battery and signal strength

---

## Installation

### Prerequisites

1. Install Whisplay HAT audio drivers:
   ```bash
   # Follow instructions at https://github.com/PiSugar/whisplay
   ```

2. Install PiSugar Power Manager (for battery display):
   ```bash
   wget https://cdn.pisugar.com/release/pisugar-power-manager.sh
   bash pisugar-power-manager.sh -c release
   ```

### Setup

1. Clone and enter the repository:
   ```bash
   git clone <repository-url> optidex
   cd optidex
   ```

2. Install dependencies:
   ```bash
   bash install_dependencies.sh
   source ~/.bashrc
   ```

3. Create environment configuration:
   ```bash
   cp .env.template .env
   # Edit .env with your API keys and preferences
   ```

4. Build the project:
   ```bash
   bash build.sh
   ```

5. Start the chatbot:
   ```bash
   bash run_chatbot.sh
   ```

6. (Optional) Enable auto-start on boot:
   ```bash
   sudo bash startup.sh
   ```

### Optional: PostgreSQL Memory Backend

For larger-scale memory storage with semantic search:

```bash
cd docker
./start-db.sh start
python3 ../python/migrate_to_postgres.py
```

### Optional: Download Wikipedia Knowledge Base

```bash
python3 python/knowledge_base.py download
```

---

## Environment Variables

Key configuration options in `.env`:

| Variable | Description | Options |
|----------|-------------|---------|
| `LLM_SERVER` | Language model provider | `OLLAMA`, `OPENAI`, `GEMINI`, `GROK` |
| `ASR_SERVER` | Speech recognition | `WHISPER_LOCAL`, `GOOGLE`, `OPENAI` |
| `TTS_SERVER` | Text-to-speech | `PIPER`, `OPENAI`, `GEMINI`, `VOLCENGINE` |
| `IMAGE_GENERATION_SERVER` | Image generation | `OPENAI`, `GEMINI`, `VOLCENGINE` |
| `SERVE_OLLAMA` | Auto-start Ollama server | `true`, `false` |

---

## Project Structure

```
optidex/
├── src/                    # TypeScript source (Node.js backend)
│   ├── core/               # ChatFlow, StreamResponsor
│   ├── cloud-api/          # LLM, TTS, ASR integrations
│   ├── config/
│   │   └── custom-tools/   # LLM tool definitions
│   ├── device/             # Audio, display, ESP32 voice
│   └── utils/              # Helpers, image utils
├── python/                 # Python components
│   ├── chatbot-ui.py       # LCD display UI
│   ├── periodic_observer.py # Autonomous observation
│   ├── live_detection.py   # Real-time object detection
│   ├── pose_estimation.py  # Pose tracking and exercise counting
│   ├── memory.py           # Unified memory interface
│   ├── knowledge_base.py   # Wikipedia search
│   └── ...
├── docker/                 # PostgreSQL + pgvector setup
├── data/                   # Runtime data (videos, images, memory)
└── docs/                   # Documentation
```

---

## Usage Examples

**Voice Commands:**
- "Take a picture"
- "What do you see?"
- "Start detecting people"
- "Count my push-ups"
- "What happened yesterday at 3pm?"
- "Watch for when a package arrives"
- "What do you know about photosynthesis?"
- "Search the web for today's weather"
- "Show me your memory"
- "List my missions"

---

## Building After Changes

After modifying TypeScript code:
```bash
bash build.sh
```

After adding Python dependencies:
```bash
cd python
pip install -r requirements.txt --break-system-packages
```

Restart the service:
```bash
# If running via systemd
systemctl restart whisplay-ai-chatbot.service

# If running manually
pkill -f run_chatbot.sh
bash run_chatbot.sh
```

---

## License

[GPL-3.0](LICENSE)

## Acknowledgments

- [PiSugar](https://github.com/PiSugar) - Whisplay HAT and original chatbot project
- [Coral](https://coral.ai/) - EdgeTPU acceleration
- [Ultralytics](https://ultralytics.com/) - YOLO models
- [OpenAI](https://openai.com/) - GPT and Whisper
- [Google](https://ai.google.dev/) - Gemini API
