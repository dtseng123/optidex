# Jarvis Memory Architecture

A hybrid memory system for the Jarvis AI assistant, combining episodic memory, semantic memory, temporal patterns, and a mission system.

## Overview

The Jarvis memory system provides:
- **Episodic Memory**: Specific events with timestamps, video/audio links
- **Semantic Memory**: Entities, concepts, and relationships (knowledge graph)
- **Temporal Memory**: Time-based patterns and context
- **Mission System**: Goal-focused behavior tracking
- **Recall**: Query memories by date, time, or content

## Storage Backends

### Primary: PostgreSQL + pgvector
- Scalable, persistent storage
- Vector embeddings for semantic search
- Full-text search with trigram indexing
- Docker-based deployment

### Fallback: NetworkX + JSON
- Zero-dependency local storage
- Automatic fallback when PostgreSQL unavailable
- Full API compatibility

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Jarvis Assistant                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Mission   │  │   Memory    │  │   Knowledge Base    │ │
│  │    Tools    │  │   Recall    │  │      (Wikipedia)    │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
│         │                │                     │            │
│         └────────────────┼─────────────────────┘            │
│                          │                                  │
│                   ┌──────▼──────┐                          │
│                   │  memory.py  │  (Unified Interface)     │
│                   └──────┬──────┘                          │
│                          │                                  │
│         ┌────────────────┼────────────────┐                │
│         │                │                │                │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐       │
│  │  PostgreSQL │  │   NetworkX  │  │   SQLite    │       │
│  │  + pgvector │  │   + JSON    │  │  (Knowledge)│       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Data Models

### Episode
```python
@dataclass
class Episode:
    id: str                          # ep_1234567890123
    timestamp: float                 # Unix timestamp
    episode_type: str                # observation, conversation, audio
    summary: str                     # Brief description
    importance: float                # 0.0 to 1.0
    video_path: Optional[str]        # Path to video file
    audio_path: Optional[str]        # Path to audio file
    image_path: Optional[str]        # Path to image file
    transcription: Optional[str]     # Speech transcription
    detected_objects: List[str]      # Objects seen
    entities_mentioned: List[str]    # People/things mentioned
    mission_id: Optional[str]        # Related mission
    metadata: Dict[str, Any]         # Additional data
```

### Mission
```python
@dataclass
class Mission:
    id: str                          # mission:m_1234567890123
    objective: str                   # What to accomplish
    mission_type: str                # surveillance, reminder, search, monitor
    status: str                      # active, completed, cancelled
    priority: str                    # low, normal, high, critical
    target_entities: List[str]       # Objects/people to watch for
    trigger_conditions: Dict         # When to trigger
    results: List[Dict]              # Mission outcomes
```

### Knowledge Graph Nodes
- **entity**: People, objects, places
- **concept**: Abstract categories
- **time**: Temporal markers (hour, day)
- **episode**: Links to episode records
- **mission**: Links to mission records

### Edge Types
- `is_a`: Entity belongs to category
- `has`: Entity has property
- `relates_to`: General relationship
- `observed_in`: Object seen in episode
- `occurred_at`: Episode at time
- `involves`: Mission involves entity
- `triggered_by`: Episode triggered by event
- `mentioned`: Entity mentioned in speech
- `located_at`: Entity at location

## Perception Pipelines

### Periodic Observer
- Captures video + audio every 10 minutes
- Runs object detection (YOLO/EdgeTPU)
- Gets scene description from Gemini Vision
- Transcribes audio with Whisper
- Creates episodes with detected content

### Timing Configuration
| System | Interval | Video Duration | Audio |
|--------|----------|----------------|-------|
| Periodic Observer | 10 minutes | 4 seconds | Concurrent |

## LLM Tools

### Memory Tools
- `displayMemory`: Show memory visualization on screen
- `getMemoryStats`: Get memory statistics

### Recall Tools
- `recallMemory`: Query by date/time/content
- `findObject`: Search for when object was last seen
- `getRecentActivity`: Get recent observations

### Mission Tools
- `createMission`: Create surveillance/reminder task
- `listMissions`: List active missions
- `completeMission`: Mark mission done
- `cancelMission`: Cancel a mission

### Knowledge Tools
- `searchKnowledge`: Search Wikipedia knowledge base
- `getArticle`: Get specific article
- `knowledgeStats`: Get knowledge base stats

## File Structure

```
optidex/
├── python/
│   ├── memory.py              # Unified interface
│   ├── jarvis_memory.py       # JSON/NetworkX backend
│   ├── jarvis_memory_pg.py    # PostgreSQL backend
│   ├── memory_display.py      # Visualization generator
│   ├── knowledge_base.py      # Wikipedia/Wikidata
│   ├── periodic_observer.py   # Video/audio capture
│   └── migrate_to_postgres.py # Migration tool
├── src/config/custom-tools/
│   ├── memory-display.ts      # Display tool
│   ├── memory-recall.ts       # Recall tool
│   ├── mission.ts             # Mission management
│   └── knowledge.ts           # Knowledge base queries
├── docker/
│   ├── docker-compose.yml     # PostgreSQL setup
│   ├── init.sql               # Database schema
│   └── start-db.sh            # DB management script
├── data/memory/
│   ├── knowledge_graph.json   # Graph data (JSON backend)
│   ├── episodes/              # Episode files
│   ├── missions/              # Mission files
│   └── visualizations/        # Generated images
└── docs/
    └── JARVIS_MEMORY_ARCHITECTURE.md
```

## Setup

### Option 1: JSON Backend (Default)
No setup required. Works automatically.

### Option 2: PostgreSQL Backend
```bash
# Start the database
cd optidex/docker
./start-db.sh start

# Migrate existing data (optional)
python3 python/migrate_to_postgres.py

# The system auto-detects PostgreSQL
```

### Environment Variables (PostgreSQL)
```bash
export JARVIS_DB_HOST=localhost
export JARVIS_DB_PORT=5432
export JARVIS_DB_NAME=jarvis_memory
export JARVIS_DB_USER=jarvis
export JARVIS_DB_PASSWORD=jarvis_memory_2024
```

## Usage Examples

### Create a Surveillance Mission
"Jarvis, watch for when a package arrives at the door"

### Recall Memories
- "What happened yesterday at 3pm?"
- "When did you last see the dog?"
- "What have you been observing today?"

### Display Memory
"Show me your memory graph"

### Query Knowledge
"What do you know about photosynthesis?"

## API Reference

### Python
```python
from memory import get_memory, Episode, Mission

memory = get_memory()

# Create episode
episode = memory.create_episode(
    episode_type="observation",
    summary="Saw a cat in the garden",
    detected_objects=["cat", "garden"],
    importance=0.7
)

# Create mission
mission = memory.create_mission(
    objective="Alert when package arrives",
    mission_type="surveillance",
    target_entities=["package", "box"],
    priority="high"
)

# Query
recent = memory.get_recent_episodes(limit=10)
missions = memory.get_active_missions()
stats = memory.get_stats()
```

### CLI
```bash
# Memory info
python3 python/memory.py info
python3 python/memory.py recent --limit 5
python3 python/memory.py missions

# Knowledge base
python3 python/knowledge_base.py search "Albert Einstein"
python3 python/knowledge_base.py stats
```

## Performance Notes

### Raspberry Pi Optimization
- JSON backend for low-memory systems
- PostgreSQL with 512MB memory limit
- Whisper "tiny" model for transcription
- 10-minute observation intervals to reduce CPU load

### Scaling
- PostgreSQL backend for larger deployments
- Vector indexes for semantic search at scale
- Partitioning for time-series episode data

