# Optidex/Jarvis Capabilities

## Camera & Photography
- Take pictures with the onboard camera and display them on screen
- Photos are automatically saved and can be sent to Telegram

## Vision & Image Analysis
- Analyze images to describe what's in them, recognize objects, people, or text
- Answer questions about image content
- Uses GPT-4o when online or local Moondream model when offline
- Extract and analyze frames from recorded videos

## Live Object Detection
- Start live detection showing real-time camera feed with bounding boxes
- Detect thousands of objects: person, hand, face, cup, bottle, phone, laptop, keyboard, mouse, book, pen, plant, chair, table, door, window, car, dog, cat, bird, etc.
- Person segmentation with semantic mask overlay using EdgeTPU DeepLab or YOLO
- Run continuously or for a set duration
- Record detection sessions to video

## Object Search
- Find specific objects by searching with the camera
- Uses broad YOLO class detection first, then AI verification to match specific descriptions
- Example: find "my blue wallet" by scanning for "handbag" candidates
- Announces when target is found and sends photo to Telegram

## Pose Estimation & Exercise Tracking
- Detect human poses and actions like waving, hands up, sitting, or standing
- Display skeleton overlay on screen
- Count exercise reps in real-time for push-ups, squats, pull-ups, and crunches
- Set rep goals and optionally record workout videos
- Play back recorded exercise videos

## Smart Observer (Surveillance Mode)
- Monitor for specific objects with live video display
- When target is found, capture photo, analyze with AI, and send notification to Telegram
- Record the monitoring session
- Continue watching after detections

## Semantic Sentry (Interaction Detection)
- Detect interactions between objects (e.g., "dog on couch", "person near door")
- Show live camera feed with detection boxes
- Alert when objects interact
- Record sessions and check all combinations of specified objects

## Video Recording & Playback
- Record videos for a specific duration (up to 5 minutes)
- Record continuously until stopped
- Show live preview while recording
- Play back recorded videos on the display

## Species & Object Classification (TPU-Accelerated)
- Classify images using specialized models:
  - ImageNet: 1,000 general objects
  - Products: 100,000 US retail products
  - Birds: 965 bird species
  - Insects: 1,022 insect species
  - Plants: 2,102 plant species
- Identify what's in a photo
- Identify items by category
- List all available classification models

## VR Passthrough Detection
- Object detection through VR headset cameras using YOLO-World
- Open-vocabulary detection (detect any object by name)
- Segmentation overlay support
- Adjustable confidence and detection smoothing
- Capture stereo frames from VR cameras for analysis

## Web Search
- Search the web for current information, news, weather, or facts
- Get direct answers, knowledge graph summaries, and organic search results

## Meshtastic Mesh Network
- List all visible devices on the Meshtastic network
- View battery levels and signal strength for each node
- Broadcast messages to all nodes
- Send messages to specific devices
- Listen for incoming messages

## Memory & Knowledge Graph
- Display a visualization of Jarvis's memory on the screen
- Shows stats: nodes, edges, episodes, and active missions
- Shows recent episodes/activity
- Optionally displays a mini knowledge graph with node connections
- Get memory statistics without visualization

## Memory Recall
- Recall memories by specific date, time, or time range
- Search memories for specific content or keywords
- Find when an object was last seen ("when did you last see my keys?")
- Get recent activity summary ("what have you been doing?")
- Filter by episode type (observations, conversations, audio)

## Mission Management
- Create surveillance missions (watch for specific objects/events)
- Create reminder missions (time-based alerts)
- Create search missions (find specific items)
- Create monitoring missions (ongoing observation tasks)
- List all active missions with priority levels
- Complete or cancel missions

## Local Knowledge Base (Wikipedia)
- Search the local Wikipedia knowledge base offline
- Get specific articles by title
- View knowledge base statistics
- Works without internet connection
- 6,912,573 articles
- 56,716 entities
  - people (20,000)
  - companies (5,000)
  -  books (10,000)
  -  species (10,000)
  -  mountains (2,000)
  -  schools (5,000)
## System Power
- Shutdown the Raspberry Pi safely with optional delay
- Reboot the system
