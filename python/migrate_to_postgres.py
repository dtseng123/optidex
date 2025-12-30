#!/usr/bin/env python3
"""
Migrate Jarvis Memory from JSON/NetworkX to PostgreSQL + pgvector

This script migrates existing memory data from the JSON-based storage
to the PostgreSQL database with vector embeddings.

Usage:
    python3 migrate_to_postgres.py [--dry-run] [--embeddings]
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

# Paths
DATA_DIR = Path(os.path.expanduser("~/optidex/data/memory"))
GRAPH_FILE = DATA_DIR / "knowledge_graph.json"
EPISODES_DIR = DATA_DIR / "episodes"
MISSIONS_DIR = DATA_DIR / "missions"

def migrate_to_postgres(dry_run: bool = False, generate_embeddings: bool = True):
    """Migrate all data from JSON to PostgreSQL"""
    
    # Import PostgreSQL backend
    sys.path.insert(0, str(Path(__file__).parent))
    
    try:
        from jarvis_memory_pg import JarvisMemoryPG, Episode, Mission
    except ImportError as e:
        print(f"Error importing PostgreSQL backend: {e}")
        print("Make sure psycopg2 is installed: pip install psycopg2-binary")
        sys.exit(1)
    
    print("=== Jarvis Memory Migration ===")
    print(f"Source: {DATA_DIR}")
    print(f"Dry run: {dry_run}")
    print(f"Generate embeddings: {generate_embeddings}")
    print()
    
    if dry_run:
        print("[DRY RUN] No changes will be made to the database")
        print()
    
    # Initialize PostgreSQL connection
    if not dry_run:
        try:
            pg_memory = JarvisMemoryPG()
            print("Connected to PostgreSQL")
        except Exception as e:
            print(f"Error connecting to PostgreSQL: {e}")
            print("Make sure the database is running: ./docker/start-db.sh start")
            sys.exit(1)
    
    # Migrate knowledge graph (nodes and edges)
    print("\n--- Migrating Knowledge Graph ---")
    nodes_migrated = 0
    edges_migrated = 0
    
    if GRAPH_FILE.exists():
        with open(GRAPH_FILE, 'r') as f:
            graph_data = json.load(f)
        
        nodes = graph_data.get('nodes', [])
        edges = graph_data.get('edges', [])
        
        print(f"Found {len(nodes)} nodes and {len(edges)} edges")
        
        if not dry_run:
            with pg_memory.conn.cursor() as cur:
                # Migrate nodes
                for node in nodes:
                    node_id = node.get('id')
                    node_type = node.get('type', 'unknown')
                    name = node.get('name', node_id.split(':')[-1] if ':' in node_id else node_id)
                    category = node.get('category')
                    
                    # Extract attributes (everything except core fields)
                    core_fields = {'id', 'type', 'name', 'category', 'created_at', 'updated_at'}
                    attributes = {k: v for k, v in node.items() if k not in core_fields}
                    
                    try:
                        cur.execute("""
                            INSERT INTO nodes (id, node_type, name, category, attributes)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET
                                name = EXCLUDED.name,
                                category = EXCLUDED.category,
                                attributes = nodes.attributes || EXCLUDED.attributes
                        """, (node_id, node_type, name, category, json.dumps(attributes)))
                        nodes_migrated += 1
                    except Exception as e:
                        print(f"  Error migrating node {node_id}: {e}")
                
                # Migrate edges
                for edge in edges:
                    source = edge.get('source')
                    target = edge.get('target')
                    edge_type = edge.get('type', 'relates_to')
                    
                    attributes = {k: v for k, v in edge.items() 
                                  if k not in {'source', 'target', 'key', 'type', 'created_at'}}
                    
                    try:
                        cur.execute("""
                            INSERT INTO edges (source_id, target_id, edge_type, attributes)
                            VALUES (%s, %s, %s, %s)
                        """, (source, target, edge_type, json.dumps(attributes)))
                        edges_migrated += 1
                    except Exception as e:
                        print(f"  Error migrating edge {source}->{target}: {e}")
                
                pg_memory.conn.commit()
        
        print(f"Migrated {nodes_migrated} nodes, {edges_migrated} edges")
    else:
        print("No knowledge graph file found")
    
    # Migrate episodes
    print("\n--- Migrating Episodes ---")
    episodes_migrated = 0
    
    if EPISODES_DIR.exists():
        episode_files = list(EPISODES_DIR.glob("ep_*.json"))
        print(f"Found {len(episode_files)} episode files")
        
        for ep_file in episode_files:
            try:
                with open(ep_file, 'r') as f:
                    ep_data = json.load(f)
                
                if not dry_run:
                    # Create episode in PostgreSQL
                    timestamp = datetime.fromtimestamp(ep_data.get('timestamp', 0))
                    
                    # Generate embedding if requested
                    embedding = None
                    if generate_embeddings and hasattr(pg_memory, '_get_embedding'):
                        embed_text = ep_data.get('summary', '')
                        if ep_data.get('transcription'):
                            embed_text += ' ' + ep_data['transcription']
                        embedding = pg_memory._get_embedding(embed_text)
                    
                    with pg_memory.conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO episodes (
                                id, timestamp, episode_type, summary, importance,
                                video_path, audio_path, image_path, transcription,
                                detected_objects, entities_mentioned, mission_id, 
                                metadata, embedding
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET
                                summary = EXCLUDED.summary,
                                metadata = episodes.metadata || EXCLUDED.metadata
                        """, (
                            ep_data.get('id'),
                            timestamp,
                            ep_data.get('episode_type', 'observation'),
                            ep_data.get('summary', ''),
                            ep_data.get('importance', 0.5),
                            ep_data.get('video_path'),
                            ep_data.get('audio_path'),
                            ep_data.get('image_path'),
                            ep_data.get('transcription'),
                            ep_data.get('detected_objects', []),
                            ep_data.get('entities_mentioned', []),
                            ep_data.get('mission_id'),
                            json.dumps(ep_data.get('metadata', {})),
                            embedding
                        ))
                    
                episodes_migrated += 1
                
                if episodes_migrated % 100 == 0:
                    print(f"  Migrated {episodes_migrated} episodes...")
                    if not dry_run:
                        pg_memory.conn.commit()
                        
            except Exception as e:
                print(f"  Error migrating {ep_file.name}: {e}")
        
        if not dry_run:
            pg_memory.conn.commit()
        
        print(f"Migrated {episodes_migrated} episodes")
    else:
        print("No episodes directory found")
    
    # Migrate missions
    print("\n--- Migrating Missions ---")
    missions_migrated = 0
    
    missions_file = MISSIONS_DIR / "active_missions.json"
    if missions_file.exists():
        try:
            with open(missions_file, 'r') as f:
                missions_data = json.load(f)
            
            print(f"Found {len(missions_data)} missions")
            
            if not dry_run:
                for m_data in missions_data:
                    try:
                        created_at = m_data.get('created_at')
                        if isinstance(created_at, (int, float)):
                            created_at = datetime.fromtimestamp(created_at)
                        
                        completed_at = m_data.get('completed_at')
                        if completed_at and isinstance(completed_at, (int, float)):
                            completed_at = datetime.fromtimestamp(completed_at)
                        
                        with pg_memory.conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO missions (
                                    id, objective, mission_type, status, priority,
                                    created_at, completed_at, target_entities,
                                    trigger_conditions, results
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (id) DO UPDATE SET
                                    status = EXCLUDED.status,
                                    results = EXCLUDED.results
                            """, (
                                m_data.get('id'),
                                m_data.get('objective', ''),
                                m_data.get('mission_type', 'general'),
                                m_data.get('status', 'active'),
                                m_data.get('priority', 'normal'),
                                created_at,
                                completed_at,
                                m_data.get('target_entities', []),
                                json.dumps(m_data.get('trigger_conditions', {})),
                                json.dumps(m_data.get('results', []))
                            ))
                        missions_migrated += 1
                    except Exception as e:
                        print(f"  Error migrating mission {m_data.get('id')}: {e}")
                
                pg_memory.conn.commit()
            
            print(f"Migrated {missions_migrated} missions")
            
        except Exception as e:
            print(f"Error loading missions file: {e}")
    else:
        print("No missions file found")
    
    # Summary
    print("\n=== Migration Summary ===")
    print(f"Nodes: {nodes_migrated}")
    print(f"Edges: {edges_migrated}")
    print(f"Episodes: {episodes_migrated}")
    print(f"Missions: {missions_migrated}")
    
    if not dry_run:
        # Show database stats
        print("\n--- Database Stats ---")
        stats = pg_memory.get_stats()
        for k, v in stats.items():
            print(f"  {k}: {v}")
    
    print("\nMigration complete!")
    
    if not dry_run:
        print("\nNext steps:")
        print("1. Verify the data in PostgreSQL")
        print("2. Set environment variables to use PostgreSQL:")
        print("   export JARVIS_DB_HOST=localhost")
        print("   export JARVIS_DB_PORT=5432")
        print("   export JARVIS_DB_NAME=jarvis_memory")
        print("   export JARVIS_DB_USER=jarvis")
        print("   export JARVIS_DB_PASSWORD=jarvis_memory_2024")
        print("3. The memory system will auto-detect PostgreSQL on next start")


def main():
    parser = argparse.ArgumentParser(description="Migrate Jarvis Memory to PostgreSQL")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be migrated without making changes")
    parser.add_argument("--no-embeddings", action="store_true",
                       help="Skip generating vector embeddings (faster, but no semantic search)")
    
    args = parser.parse_args()
    
    migrate_to_postgres(
        dry_run=args.dry_run,
        generate_embeddings=not args.no_embeddings
    )


if __name__ == "__main__":
    main()

