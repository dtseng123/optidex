#!/usr/bin/env python3
"""
Jarvis Memory System - Knowledge Graph based memory for AI assistant

This module implements a hybrid memory architecture combining:
- Episodic Memory: Specific events with timestamps, video/audio links
- Semantic Memory: Entities, concepts, and relationships
- Temporal Memory: Time-based patterns and context
- Mission System: Goal-focused behavior tracking

Storage: NetworkX graph with JSON persistence (fallback when PostgreSQL unavailable)
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
import networkx as nx

# Data directories
DATA_DIR = Path(os.path.expanduser("~/optidex/data/memory"))
GRAPH_FILE = DATA_DIR / "knowledge_graph.json"
EPISODES_DIR = DATA_DIR / "episodes"
MISSIONS_DIR = DATA_DIR / "missions"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
EPISODES_DIR.mkdir(parents=True, exist_ok=True)
MISSIONS_DIR.mkdir(parents=True, exist_ok=True)


class EdgeType(Enum):
    """Types of relationships in the knowledge graph"""
    IS_A = "is_a"              # Entity is a type of concept
    HAS = "has"                # Entity has property/attribute
    RELATES_TO = "relates_to"  # General relationship
    OBSERVED_IN = "observed_in"  # Object observed in episode
    OCCURRED_AT = "occurred_at"  # Episode occurred at time
    INVOLVES = "involves"      # Mission involves entity/concept
    TRIGGERED_BY = "triggered_by"  # Episode triggered by event
    MENTIONED = "mentioned"    # Entity mentioned in speech
    LOCATED_AT = "located_at"  # Entity located at place


@dataclass
class Episode:
    """Represents a memory episode (event)"""
    id: str
    timestamp: float
    episode_type: str  # observation, conversation, audio, mission_event
    summary: str
    importance: float = 0.5  # 0.0 to 1.0
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


@dataclass
class Mission:
    """Represents a Jarvis mission/objective"""
    id: str
    objective: str
    mission_type: str  # surveillance, reminder, search, monitor
    status: str = "active"  # active, completed, cancelled
    priority: str = "normal"  # low, normal, high, critical
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


class JarvisMemory:
    """
    Main memory system using NetworkX knowledge graph with JSON persistence.
    """
    
    def __init__(self, graph_file: Path = GRAPH_FILE):
        self.graph_file = graph_file
        self.graph = nx.MultiDiGraph()
        self._load_graph()
        self._initialize_core_nodes()
    
    def _load_graph(self):
        """Load graph from JSON file"""
        if self.graph_file.exists():
            try:
                with open(self.graph_file, 'r') as f:
                    data = json.load(f)
                
                # Add nodes
                for node in data.get('nodes', []):
                    node_id = node.pop('id')
                    self.graph.add_node(node_id, **node)
                
                # Add edges
                for edge in data.get('edges', []):
                    self.graph.add_edge(
                        edge['source'],
                        edge['target'],
                        key=edge.get('key', f"edge_{time.time()}"),
                        **{k: v for k, v in edge.items() if k not in ['source', 'target', 'key']}
                    )
                
                print(f"[Memory] Loaded graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges", file=sys.stderr)
            except Exception as e:
                print(f"[Memory] Error loading graph: {e}", file=sys.stderr)
                self.graph = nx.MultiDiGraph()
    
    def _save_graph(self):
        """Save graph to JSON file"""
        try:
            nodes = []
            for node_id, attrs in self.graph.nodes(data=True):
                node_data = {'id': node_id, **attrs}
                nodes.append(node_data)
            
            edges = []
            for u, v, key, attrs in self.graph.edges(keys=True, data=True):
                edge_data = {'source': u, 'target': v, 'key': key, **attrs}
                edges.append(edge_data)
            
            data = {'nodes': nodes, 'edges': edges}
            
            with open(self.graph_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"[Memory] Error saving graph: {e}", file=sys.stderr)
    
    def _initialize_core_nodes(self):
        """Ensure core nodes exist"""
        if not self.graph.has_node("entity:user"):
            self.add_entity("user", "person", role="owner")
        if not self.graph.has_node("entity:jarvis"):
            self.add_entity("jarvis", "ai_assistant", role="assistant")
    
    # === Entity Management ===
    
    def add_entity(self, name: str, category: str, **attributes) -> str:
        """Add or update an entity node"""
        node_id = f"entity:{name.lower().replace(' ', '_')}"
        
        if self.graph.has_node(node_id):
            # Update existing
            self.graph.nodes[node_id].update(attributes)
            self.graph.nodes[node_id]['updated_at'] = time.time()
        else:
            # Create new
            self.graph.add_node(node_id,
                name=name,
                type="entity",
                category=category,
                created_at=time.time(),
                updated_at=time.time(),
                **attributes
            )
            # Link to category concept
            self._ensure_concept(category)
            self._add_edge(node_id, f"concept:{category}", EdgeType.IS_A)
        
        self._save_graph()
        return node_id
    
    def add_concept(self, name: str, **attributes) -> str:
        """Add or update a concept node"""
        return self._ensure_concept(name, **attributes)
    
    def _ensure_concept(self, name: str, **attributes) -> str:
        """Ensure a concept exists"""
        node_id = f"concept:{name.lower().replace(' ', '_')}"
        
        if not self.graph.has_node(node_id):
            self.graph.add_node(node_id,
                name=name,
                type="concept",
                created_at=time.time(),
                **attributes
            )
        elif attributes:
            self.graph.nodes[node_id].update(attributes)
        
        return node_id
    
    def _add_edge(self, source: str, target: str, edge_type: EdgeType, **attributes):
        """Add an edge between nodes"""
        key = f"{edge_type.value}_{int(time.time() * 1000)}"
        self.graph.add_edge(source, target, key=key,
            type=edge_type.value,
            created_at=time.time(),
            **attributes
        )
    
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
        timestamp = time.time()
        
        episode = Episode(
            id=episode_id,
            timestamp=timestamp,
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
        
        # Save episode to file
        episode_file = EPISODES_DIR / f"{episode_id}.json"
        with open(episode_file, 'w') as f:
            json.dump(episode.to_dict(), f, indent=2)
        
        # Add episode node to graph
        self.graph.add_node(episode_id,
            type="episode",
            timestamp=timestamp,
            episode_type=episode_type,
            summary=summary,
            importance=importance
        )
        
        # Link to detected objects
        for obj in (detected_objects or []):
            entity_id = self.add_entity(episode_id, "episode_entity")
            concept_id = self._ensure_concept(obj, category="detected_object")
            self._add_edge(entity_id, concept_id, EdgeType.OBSERVED_IN)
        
        # Link to time node
        time_node = self._get_or_create_time_node(timestamp)
        self._add_edge(entity_id if detected_objects else episode_id, time_node, EdgeType.OCCURRED_AT)
        
        # Link to mission if applicable
        if mission_id and self.graph.has_node(mission_id):
            self._add_edge(episode_id, mission_id, EdgeType.TRIGGERED_BY)
        
        self._save_graph()
        
        print(f"[Memory] Created episode: {episode_id} - {summary[:50]}...", file=sys.stderr)
        return episode
    
    def get_episode(self, episode_id: str) -> Optional[Episode]:
        """Retrieve an episode by ID"""
        episode_file = EPISODES_DIR / f"{episode_id}.json"
        if episode_file.exists():
            with open(episode_file, 'r') as f:
                return Episode.from_dict(json.load(f))
        return None
    
    def get_recent_episodes(self, limit: int = 10, episode_type: str = None) -> List[Episode]:
        """Get most recent episodes"""
        episodes = []
        for episode_file in sorted(EPISODES_DIR.glob("ep_*.json"), reverse=True)[:limit * 2]:
            try:
                with open(episode_file, 'r') as f:
                    ep = Episode.from_dict(json.load(f))
                    if episode_type is None or ep.episode_type == episode_type:
                        episodes.append(ep)
                        if len(episodes) >= limit:
                            break
            except:
                continue
        return episodes
    
    # === Time Management ===
    
    def _get_or_create_time_node(self, timestamp: float) -> str:
        """Get or create a time node for the given timestamp"""
        dt = datetime.fromtimestamp(timestamp)
        time_id = f"time:{dt.strftime('%Y%m%d_%H%M')}"
        
        if not self.graph.has_node(time_id):
            self.graph.add_node(time_id,
                type="time",
                timestamp=timestamp,
                date=dt.strftime("%Y-%m-%d"),
                time=dt.strftime("%H:%M"),
                hour=dt.hour,
                day_of_week=dt.strftime("%A")
            )
        
        return time_id
    
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
        
        # Add mission node to graph
        self.graph.add_node(mission_id,
            type="mission",
            objective=objective,
            mission_type=mission_type,
            status="active",
            priority=priority,
            created_at=mission.created_at
        )
        
        # Link to target entities/concepts
        for target in (target_entities or []):
            concept_id = self._ensure_concept(target, category="target_object")
            self._add_edge(mission_id, concept_id, EdgeType.INVOLVES)
        
        self._save_missions()
        self._save_graph()
        
        print(f"[Memory] Created mission: {mission_id} - {objective}", file=sys.stderr)
        return mission
    
    def get_active_missions(self) -> List[Mission]:
        """Get all active missions"""
        missions = []
        missions_file = MISSIONS_DIR / "active_missions.json"
        
        if missions_file.exists():
            try:
                with open(missions_file, 'r') as f:
                    data = json.load(f)
                    for m in data:
                        missions.append(Mission.from_dict(m))
            except:
                pass
        
        # Also check graph for active missions
        for node_id, attrs in self.graph.nodes(data=True):
            if attrs.get('type') == 'mission' and attrs.get('status') == 'active':
                if not any(m.id == node_id for m in missions):
                    missions.append(Mission(
                        id=node_id,
                        objective=attrs.get('objective', ''),
                        mission_type=attrs.get('mission_type', 'general'),
                        status='active',
                        priority=attrs.get('priority', 'normal'),
                        created_at=attrs.get('created_at', time.time())
                    ))
        
        return missions
    
    def complete_mission(self, mission_id: str, results: Dict = None):
        """Mark a mission as completed"""
        if self.graph.has_node(mission_id):
            self.graph.nodes[mission_id]['status'] = 'completed'
            self.graph.nodes[mission_id]['completed_at'] = time.time()
            if results:
                self.graph.nodes[mission_id]['results'] = results
            self._save_graph()
            self._save_missions()
    
    def _save_missions(self):
        """Save active missions to file"""
        missions = self.get_active_missions()
        missions_file = MISSIONS_DIR / "active_missions.json"
        with open(missions_file, 'w') as f:
            json.dump([m.to_dict() for m in missions], f, indent=2)
    
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
            
            # Check detected objects against target entities
            if detected_objects and mission.target_entities:
                for obj in detected_objects:
                    if obj.lower() in [t.lower() for t in mission.target_entities]:
                        score += 0.5
            
            # Check transcription for keywords
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
        results = []
        query_lower = query.lower()
        
        for node_id, attrs in self.graph.nodes(data=True):
            if attrs.get('type') == 'entity':
                name = attrs.get('name', '').lower()
                if query_lower in name or query_lower in node_id.lower():
                    results.append({'id': node_id, **attrs})
        
        return results[:limit]
    
    def get_related_entities(self, entity_id: str, max_depth: int = 2) -> List[Dict]:
        """Get entities related to the given entity"""
        if not self.graph.has_node(entity_id):
            return []
        
        related = []
        visited = set()
        
        def traverse(node, depth):
            if depth > max_depth or node in visited:
                return
            visited.add(node)
            
            for neighbor in self.graph.neighbors(node):
                if neighbor not in visited:
                    attrs = self.graph.nodes.get(neighbor, {})
                    related.append({'id': neighbor, 'depth': depth, **attrs})
                    traverse(neighbor, depth + 1)
        
        traverse(entity_id, 1)
        return related
    
    def get_stats(self) -> Dict:
        """Get memory statistics"""
        node_types = {}
        for _, attrs in self.graph.nodes(data=True):
            t = attrs.get('type', 'unknown')
            node_types[t] = node_types.get(t, 0) + 1
        
        episodes_count = len(list(EPISODES_DIR.glob("ep_*.json")))
        
        return {
            'total_nodes': self.graph.number_of_nodes(),
            'total_edges': self.graph.number_of_edges(),
            'entities': node_types.get('entity', 0),
            'concepts': node_types.get('concept', 0),
            'episodes': episodes_count,
            'time_nodes': node_types.get('time', 0),
            'active_missions': len(self.get_active_missions()),
            'node_types': node_types
        }
    
    def get_context_for_llm(self, include_recent: bool = True, include_missions: bool = True) -> str:
        """Generate context string for LLM"""
        parts = []
        
        # Stats
        stats = self.get_stats()
        parts.append(f"Memory: {stats['entities']} entities, {stats['episodes']} episodes")
        
        # Active missions
        if include_missions:
            missions = self.get_active_missions()
            if missions:
                parts.append("Active missions:")
                for m in missions[:3]:
                    parts.append(f"  - {m.objective} ({m.priority})")
        
        # Recent episodes
        if include_recent:
            recent = self.get_recent_episodes(limit=3)
            if recent:
                parts.append("Recent observations:")
                for ep in recent:
                    dt = datetime.fromtimestamp(ep.timestamp)
                    parts.append(f"  - {dt.strftime('%H:%M')}: {ep.summary[:60]}")
        
        return "\n".join(parts)


# Singleton instance
_memory_instance: Optional[JarvisMemory] = None

def get_memory() -> JarvisMemory:
    """Get the singleton memory instance"""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = JarvisMemory()
    return _memory_instance


# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Jarvis Memory System")
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
            print(f"Nodes: {stats['total_nodes']}, Edges: {stats['total_edges']}")
            print(f"Entities: {stats['entities']}, Episodes: {stats['episodes']}")
            print(f"Active Missions: {stats['active_missions']}")
    
    elif args.command == "recent":
        episodes = memory.get_recent_episodes(limit=args.limit)
        if args.json:
            print(json.dumps([e.to_dict() for e in episodes], indent=2))
        else:
            for ep in episodes:
                dt = datetime.fromtimestamp(ep.timestamp)
                print(f"[{dt.strftime('%Y-%m-%d %H:%M')}] {ep.episode_type}: {ep.summary}")
    
    elif args.command == "missions":
        missions = memory.get_active_missions()
        if args.json:
            print(json.dumps([m.to_dict() for m in missions], indent=2))
        else:
            for m in missions:
                print(f"[{m.priority}] {m.objective} ({m.mission_type})")
    
    elif args.command == "search":
        if args.query:
            results = memory.search_entities(args.query, limit=args.limit)
            if args.json:
                print(json.dumps(results, indent=2))
            else:
                for r in results:
                    print(f"{r.get('id')}: {r.get('name')} ({r.get('category', 'unknown')})")
    
    elif args.command == "context":
        print(memory.get_context_for_llm())

