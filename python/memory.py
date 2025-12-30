#!/usr/bin/env python3
"""
Unified Memory Interface for Jarvis

Provides a consistent interface that automatically selects between:
- PostgreSQL + pgvector (primary, if available)
- NetworkX + JSON (fallback)

Usage:
    from memory import get_memory, Episode, Mission
    
    memory = get_memory()
    episode = memory.create_episode(...)
"""

import os
import sys

# Try PostgreSQL backend first
_USE_POSTGRES = False
_backend = None

try:
    # Check if PostgreSQL is available
    import psycopg2
    
    # Try to connect
    conn = psycopg2.connect(
        host=os.environ.get("JARVIS_DB_HOST", "localhost"),
        port=os.environ.get("JARVIS_DB_PORT", "5432"),
        database=os.environ.get("JARVIS_DB_NAME", "jarvis_memory"),
        user=os.environ.get("JARVIS_DB_USER", "jarvis"),
        password=os.environ.get("JARVIS_DB_PASSWORD", "jarvis_memory_2024"),
        connect_timeout=2
    )
    conn.close()
    
    # PostgreSQL available, use it
    from jarvis_memory_pg import JarvisMemoryPG as JarvisMemory, Episode, EdgeType, Mission
    _USE_POSTGRES = True
    _backend = "postgresql"
    print("[Memory] Using PostgreSQL + pgvector backend", file=sys.stderr)
    
except Exception as e:
    # Fall back to JSON/NetworkX
    from jarvis_memory import JarvisMemory, Episode, EdgeType, Mission
    _backend = "json"
    print(f"[Memory] Using JSON/NetworkX backend (PostgreSQL unavailable: {e})", file=sys.stderr)


# Singleton instance
_memory_instance = None


def get_memory() -> JarvisMemory:
    """Get the singleton memory instance"""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = JarvisMemory()
    return _memory_instance


def get_backend() -> str:
    """Get the current backend type"""
    return _backend


def is_postgres() -> bool:
    """Check if using PostgreSQL backend"""
    return _USE_POSTGRES


# Re-export common classes
__all__ = ['get_memory', 'get_backend', 'is_postgres', 'Episode', 'EdgeType', 'Mission', 'JarvisMemory']


if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Jarvis Unified Memory Interface")
    parser.add_argument("command", nargs="?", default="info", 
                        choices=["info", "stats", "recent", "missions", "context"])
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--limit", "-l", type=int, default=5)
    
    args = parser.parse_args()
    memory = get_memory()
    
    if args.command == "info":
        print(f"Backend: {get_backend()}")
        print(f"PostgreSQL: {is_postgres()}")
        stats = memory.get_stats()
        print(f"Nodes: {stats.get('total_nodes', 0)}")
        print(f"Episodes: {stats.get('episodes', 0)}")
        print(f"Missions: {stats.get('active_missions', 0)}")
    
    elif args.command == "stats":
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
            from datetime import datetime
            for ep in episodes:
                dt = datetime.fromtimestamp(ep.timestamp)
                print(f"[{dt.strftime('%H:%M')}] {ep.summary[:60]}")
    
    elif args.command == "missions":
        missions = memory.get_active_missions()
        if args.json:
            print(json.dumps([m.to_dict() for m in missions], indent=2, default=str))
        else:
            for m in missions:
                print(f"[{m.priority}] {m.objective}")
    
    elif args.command == "context":
        print(memory.get_context_for_llm())

