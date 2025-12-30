#!/usr/bin/env python3
"""
Jarvis Memory System - PostgreSQL + pgvector Backend

This module implements a hybrid memory architecture using PostgreSQL with pgvector
for semantic search capabilities. Provides the same interface as jarvis_memory.py
but with scalable, persistent storage.

Requirements:
- PostgreSQL 14+ with pgvector extension
- psycopg2-binary
- sentence-transformers (for embeddings)
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

import psycopg2
from psycopg2.extras import Json, RealDictCursor

# Try to import embedding model
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
    HAS_EMBEDDINGS = True
except ImportError:
    EMBEDDING_MODEL = None
    HAS_EMBEDDINGS = False
    print("[Memory-PG] sentence-transformers not available, semantic search disabled", file=sys.stderr)

# Database configuration
DB_CONFIG = {
    'host': os.environ.get('JARVIS_DB_HOST', 'localhost'),
    'port': os.environ.get('JARVIS_DB_PORT', '5432'),
    'database': os.environ.get('JARVIS_DB_NAME', 'jarvis_memory'),
    'user': os.environ.get('JARVIS_DB_USER', 'jarvis'),
    'password': os.environ.get('JARVIS_DB_PASSWORD', 'jarvis_memory_2024'),
}

# Embedding dimension
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2


class EdgeType(Enum):
    """Types of relationships in the knowledge graph"""
    IS_A = "is_a"
    HAS = "has"
    RELATES_TO = "relates_to"
    OBSERVED_IN = "observed_in"
    OCCURRED_AT = "occurred_at"
    INVOLVES = "involves"
    TRIGGERED_BY = "triggered_by"
    MENTIONED = "mentioned"
    LOCATED_AT = "located_at"


@dataclass
class Episode:
    """Represents a memory episode (event)"""
    id: str
    timestamp: float
    episode_type: str
    summary: str
    importance: float = 0.5
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    image_path: Optional[str] = None
    transcription: Optional[str] = None
    detected_objects: List[str] = field(default_factory=list)
    entities_mentioned: List[str] = field(default_factory=list)
    mission_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Episode':
        return cls(**data)
    
    @classmethod
    def from_row(cls, row: Dict) -> 'Episode':
        """Create Episode from database row"""
        return cls(
            id=row['id'],
            timestamp=row['timestamp'].timestamp() if hasattr(row['timestamp'], 'timestamp') else row['timestamp'],
            episode_type=row['episode_type'],
            summary=row['summary'],
            importance=row.get('importance', 0.5),
            video_path=row.get('video_path'),
            audio_path=row.get('audio_path'),
            image_path=row.get('image_path'),
            transcription=row.get('transcription'),
            detected_objects=row.get('detected_objects', []),
            entities_mentioned=row.get('entities_mentioned', []),
            mission_id=row.get('mission_id'),
            metadata=row.get('metadata', {})
        )


@dataclass
class Mission:
    """Represents a Jarvis mission/objective"""
    id: str
    objective: str
    mission_type: str
    status: str = "active"
    priority: str = "normal"
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    target_entities: List[str] = field(default_factory=list)
    trigger_conditions: Dict[str, Any] = field(default_factory=dict)
    results: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Mission':
        return cls(**data)
    
    @classmethod
    def from_row(cls, row: Dict) -> 'Mission':
        """Create Mission from database row"""
        created_at = row['created_at']
        if hasattr(created_at, 'timestamp'):
            created_at = created_at.timestamp()
        
        completed_at = row.get('completed_at')
        if completed_at and hasattr(completed_at, 'timestamp'):
            completed_at = completed_at.timestamp()
            
        return cls(
            id=row['id'],
            objective=row['objective'],
            mission_type=row['mission_type'],
            status=row.get('status', 'active'),
            priority=row.get('priority', 'normal'),
            created_at=created_at,
            completed_at=completed_at,
            target_entities=row.get('target_entities', []),
            trigger_conditions=row.get('trigger_conditions', {}),
            results=row.get('results', [])
        )


class JarvisMemoryPG:
    """
    PostgreSQL-backed memory system with pgvector for semantic search.
    """
    
    def __init__(self):
        self.conn = None
        self._connect()
        self._ensure_schema()
    
    def _connect(self):
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.conn.autocommit = False
            print(f"[Memory-PG] Connected to PostgreSQL", file=sys.stderr)
        except Exception as e:
            print(f"[Memory-PG] Connection failed: {e}", file=sys.stderr)
            raise
    
    def _ensure_schema(self):
        """Create tables if they don't exist"""
        with self.conn.cursor() as cur:
            # Enable pgvector extension
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            # Nodes table (entities, concepts, time nodes)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id VARCHAR(255) PRIMARY KEY,
                    node_type VARCHAR(50) NOT NULL,
                    name VARCHAR(255),
                    category VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    attributes JSONB DEFAULT '{}'::jsonb,
                    embedding vector(%s)
                );
                CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
                CREATE INDEX IF NOT EXISTS idx_nodes_category ON nodes(category);
            """ % EMBEDDING_DIM)
            
            # Edges table (relationships)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    id SERIAL PRIMARY KEY,
                    source_id VARCHAR(255) REFERENCES nodes(id) ON DELETE CASCADE,
                    target_id VARCHAR(255) REFERENCES nodes(id) ON DELETE CASCADE,
                    edge_type VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    attributes JSONB DEFAULT '{}'::jsonb
                );
                CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
                CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);
            """)
            
            # Episodes table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id VARCHAR(100) PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    episode_type VARCHAR(50) NOT NULL,
                    summary TEXT,
                    importance FLOAT DEFAULT 0.5,
                    video_path VARCHAR(500),
                    audio_path VARCHAR(500),
                    image_path VARCHAR(500),
                    transcription TEXT,
                    detected_objects TEXT[],
                    entities_mentioned TEXT[],
                    mission_id VARCHAR(100),
                    metadata JSONB DEFAULT '{}'::jsonb,
                    embedding vector(%s),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_episodes_type ON episodes(episode_type);
            """ % EMBEDDING_DIM)
            
            # Missions table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS missions (
                    id VARCHAR(100) PRIMARY KEY,
                    objective TEXT NOT NULL,
                    mission_type VARCHAR(50) NOT NULL,
                    status VARCHAR(20) DEFAULT 'active',
                    priority VARCHAR(20) DEFAULT 'normal',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    target_entities TEXT[],
                    trigger_conditions JSONB DEFAULT '{}'::jsonb,
                    results JSONB DEFAULT '[]'::jsonb
                );
                CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status);
            """)
            
            self.conn.commit()
            print("[Memory-PG] Schema initialized", file=sys.stderr)
    
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text"""
        if not HAS_EMBEDDINGS or not EMBEDDING_MODEL:
            return None
        try:
            embedding = EMBEDDING_MODEL.encode(text).tolist()
            return embedding
        except Exception as e:
            print(f"[Memory-PG] Embedding error: {e}", file=sys.stderr)
            return None
    
    # === Entity Management ===
    
    def add_entity(self, name: str, category: str, **attributes) -> str:
        """Add or update an entity node"""
        node_id = f"entity:{name.lower().replace(' ', '_')}"
        
        with self.conn.cursor() as cur:
            # Get embedding for entity
            embedding = self._get_embedding(f"{name} {category}")
            
            cur.execute("""
                INSERT INTO nodes (id, node_type, name, category, attributes, embedding)
                VALUES (%s, 'entity', %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    attributes = nodes.attributes || EXCLUDED.attributes,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (node_id, name, category, Json(attributes), embedding))
            
            # Ensure category concept exists
            self._ensure_concept(category)
            
            # Add IS_A relationship
            self._add_edge(node_id, f"concept:{category}", EdgeType.IS_A)
            
            self.conn.commit()
        
        return node_id
    
    def _ensure_concept(self, name: str, **attributes) -> str:
        """Ensure a concept exists"""
        node_id = f"concept:{name.lower().replace(' ', '_')}"
        
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO nodes (id, node_type, name, attributes)
                VALUES (%s, 'concept', %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (node_id, name, Json(attributes)))
        
        return node_id
    
    def _add_edge(self, source: str, target: str, edge_type: EdgeType, **attributes):
        """Add an edge between nodes"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO edges (source_id, target_id, edge_type, attributes)
                VALUES (%s, %s, %s, %s)
            """, (source, target, edge_type.value, Json(attributes)))
    
    # === Episode Management ===
    
    def create_episode(
        self,
        episode_type: str,
        summary: str,
        importance: float = 0.5,
        video_path: Optional[str] = None,
        audio_path: Optional[str] = None,
        image_path: Optional[str] = None,
        transcription: Optional[str] = None,
        detected_objects: List[str] = None,
        entities_mentioned: List[str] = None,
        mission_id: Optional[str] = None,
        **metadata
    ) -> Episode:
        """Create a new memory episode"""
        episode_id = f"ep_{int(time.time() * 1000)}"
        timestamp = datetime.now()
        
        # Generate embedding from summary and transcription
        embed_text = summary
        if transcription:
            embed_text += " " + transcription
        embedding = self._get_embedding(embed_text)
        
        episode = Episode(
            id=episode_id,
            timestamp=timestamp.timestamp(),
            episode_type=episode_type,
            summary=summary,
            importance=importance,
            video_path=video_path,
            audio_path=audio_path,
            image_path=image_path,
            transcription=transcription,
            detected_objects=detected_objects or [],
            entities_mentioned=entities_mentioned or [],
            mission_id=mission_id,
            metadata=metadata
        )
        
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO episodes (
                    id, timestamp, episode_type, summary, importance,
                    video_path, audio_path, image_path, transcription,
                    detected_objects, entities_mentioned, mission_id, metadata, embedding
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                episode_id, timestamp, episode_type, summary, importance,
                video_path, audio_path, image_path, transcription,
                detected_objects or [], entities_mentioned or [], mission_id,
                Json(metadata), embedding
            ))
            
            self.conn.commit()
        
        print(f"[Memory-PG] Created episode: {episode_id} - {summary[:50]}...", file=sys.stderr)
        return episode
    
    def get_episode(self, episode_id: str) -> Optional[Episode]:
        """Retrieve an episode by ID"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM episodes WHERE id = %s", (episode_id,))
            row = cur.fetchone()
            if row:
                return Episode.from_row(dict(row))
        return None
    
    def get_recent_episodes(self, limit: int = 10, episode_type: str = None) -> List[Episode]:
        """Get most recent episodes"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            if episode_type:
                cur.execute("""
                    SELECT * FROM episodes 
                    WHERE episode_type = %s
                    ORDER BY timestamp DESC LIMIT %s
                """, (episode_type, limit))
            else:
                cur.execute("""
                    SELECT * FROM episodes 
                    ORDER BY timestamp DESC LIMIT %s
                """, (limit,))
            
            return [Episode.from_row(dict(row)) for row in cur.fetchall()]
    
    def search_episodes_by_time(
        self,
        start_time: datetime = None,
        end_time: datetime = None,
        episode_type: str = None,
        limit: int = 50
    ) -> List[Episode]:
        """Search episodes by time range"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            conditions = []
            params = []
            
            if start_time:
                conditions.append("timestamp >= %s")
                params.append(start_time)
            if end_time:
                conditions.append("timestamp <= %s")
                params.append(end_time)
            if episode_type:
                conditions.append("episode_type = %s")
                params.append(episode_type)
            
            where = " AND ".join(conditions) if conditions else "TRUE"
            params.append(limit)
            
            cur.execute(f"""
                SELECT * FROM episodes 
                WHERE {where}
                ORDER BY timestamp DESC LIMIT %s
            """, params)
            
            return [Episode.from_row(dict(row)) for row in cur.fetchall()]
    
    def semantic_search_episodes(self, query: str, limit: int = 10) -> List[Episode]:
        """Search episodes by semantic similarity"""
        if not HAS_EMBEDDINGS:
            # Fallback to text search
            return self._text_search_episodes(query, limit)
        
        embedding = self._get_embedding(query)
        if not embedding:
            return self._text_search_episodes(query, limit)
        
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT *, embedding <=> %s::vector AS distance
                FROM episodes
                WHERE embedding IS NOT NULL
                ORDER BY distance ASC
                LIMIT %s
            """, (embedding, limit))
            
            return [Episode.from_row(dict(row)) for row in cur.fetchall()]
    
    def _text_search_episodes(self, query: str, limit: int) -> List[Episode]:
        """Fallback text search for episodes"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM episodes
                WHERE summary ILIKE %s OR transcription ILIKE %s
                ORDER BY timestamp DESC LIMIT %s
            """, (f'%{query}%', f'%{query}%', limit))
            
            return [Episode.from_row(dict(row)) for row in cur.fetchall()]
    
    # === Mission Management ===
    
    def create_mission(
        self,
        objective: str,
        mission_type: str,
        priority: str = "normal",
        target_entities: List[str] = None,
        trigger_conditions: Dict = None
    ) -> Mission:
        """Create a new mission"""
        mission_id = f"mission:m_{int(time.time() * 1000)}"
        
        mission = Mission(
            id=mission_id,
            objective=objective,
            mission_type=mission_type,
            priority=priority,
            target_entities=target_entities or [],
            trigger_conditions=trigger_conditions or {}
        )
        
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO missions (
                    id, objective, mission_type, priority,
                    target_entities, trigger_conditions
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                mission_id, objective, mission_type, priority,
                target_entities or [], Json(trigger_conditions or {})
            ))
            
            self.conn.commit()
        
        print(f"[Memory-PG] Created mission: {mission_id} - {objective}", file=sys.stderr)
        return mission
    
    def get_active_missions(self) -> List[Mission]:
        """Get all active missions"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM missions WHERE status = 'active'
                ORDER BY 
                    CASE priority 
                        WHEN 'critical' THEN 1 
                        WHEN 'high' THEN 2 
                        WHEN 'normal' THEN 3 
                        ELSE 4 
                    END
            """)
            
            return [Mission.from_row(dict(row)) for row in cur.fetchall()]
    
    def complete_mission(self, mission_id: str, results: Dict = None):
        """Mark a mission as completed"""
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE missions 
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP, results = %s
                WHERE id = %s
            """, (Json(results or {}), mission_id))
            self.conn.commit()
    
    def check_mission_match(
        self,
        detected_objects: List[str] = None,
        transcription: str = None,
        location: str = None
    ) -> List[Tuple[Mission, float]]:
        """Check if any missions match current observations"""
        matches = []
        
        for mission in self.get_active_missions():
            score = 0.0
            
            if detected_objects and mission.target_entities:
                for obj in detected_objects:
                    if obj.lower() in [t.lower() for t in mission.target_entities]:
                        score += 0.5
            
            if transcription and mission.target_entities:
                for target in mission.target_entities:
                    if target.lower() in transcription.lower():
                        score += 0.3
            
            if score > 0:
                matches.append((mission, min(score, 1.0)))
        
        return sorted(matches, key=lambda x: x[1], reverse=True)
    
    # === Query Methods ===
    
    def search_entities(self, query: str, limit: int = 10) -> List[Dict]:
        """Search for entities by name"""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM nodes
                WHERE node_type = 'entity' AND name ILIKE %s
                LIMIT %s
            """, (f'%{query}%', limit))
            
            return [dict(row) for row in cur.fetchall()]
    
    def get_stats(self) -> Dict:
        """Get memory statistics"""
        with self.conn.cursor() as cur:
            stats = {}
            
            cur.execute("SELECT COUNT(*) FROM nodes")
            stats['total_nodes'] = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM edges")
            stats['total_edges'] = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM nodes WHERE node_type = 'entity'")
            stats['entities'] = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM nodes WHERE node_type = 'concept'")
            stats['concepts'] = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM episodes")
            stats['episodes'] = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM missions WHERE status = 'active'")
            stats['active_missions'] = cur.fetchone()[0]
            
            return stats
    
    def get_context_for_llm(self, include_recent: bool = True, include_missions: bool = True) -> str:
        """Generate context string for LLM"""
        parts = []
        
        stats = self.get_stats()
        parts.append(f"Memory: {stats['entities']} entities, {stats['episodes']} episodes")
        
        if include_missions:
            missions = self.get_active_missions()
            if missions:
                parts.append("Active missions:")
                for m in missions[:3]:
                    parts.append(f"  - {m.objective} ({m.priority})")
        
        if include_recent:
            recent = self.get_recent_episodes(limit=3)
            if recent:
                parts.append("Recent observations:")
                for ep in recent:
                    dt = datetime.fromtimestamp(ep.timestamp)
                    parts.append(f"  - {dt.strftime('%H:%M')}: {ep.summary[:60]}")
        
        return "\n".join(parts)
    
    # Compatibility property for JSON backend
    @property
    def graph(self):
        """Return None - no NetworkX graph in PG backend"""
        return None


# Singleton instance
_memory_instance: Optional[JarvisMemoryPG] = None

def get_memory() -> JarvisMemoryPG:
    """Get the singleton memory instance"""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = JarvisMemoryPG()
    return _memory_instance


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Jarvis Memory System (PostgreSQL)")
    parser.add_argument("command", choices=["stats", "recent", "missions", "search", "context"])
    parser.add_argument("--query", "-q", help="Search query")
    parser.add_argument("--limit", "-l", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    memory = get_memory()
    
    if args.command == "stats":
        stats = memory.get_stats()
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            for k, v in stats.items():
                print(f"{k}: {v}")
    
    elif args.command == "recent":
        episodes = memory.get_recent_episodes(limit=args.limit)
        if args.json:
            print(json.dumps([e.to_dict() for e in episodes], indent=2, default=str))
        else:
            for ep in episodes:
                dt = datetime.fromtimestamp(ep.timestamp)
                print(f"[{dt.strftime('%Y-%m-%d %H:%M')}] {ep.episode_type}: {ep.summary}")
    
    elif args.command == "missions":
        missions = memory.get_active_missions()
        if args.json:
            print(json.dumps([m.to_dict() for m in missions], indent=2, default=str))
        else:
            for m in missions:
                print(f"[{m.priority}] {m.objective} ({m.mission_type})")
    
    elif args.command == "search":
        if args.query:
            episodes = memory.semantic_search_episodes(args.query, limit=args.limit)
            if args.json:
                print(json.dumps([e.to_dict() for e in episodes], indent=2, default=str))
            else:
                for ep in episodes:
                    dt = datetime.fromtimestamp(ep.timestamp)
                    print(f"[{dt.strftime('%Y-%m-%d %H:%M')}] {ep.summary[:80]}")
    
    elif args.command == "context":
        print(memory.get_context_for_llm())

