-- Jarvis Memory Database Initialization
-- This script runs automatically when the PostgreSQL container is first created

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- For fuzzy text search

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE jarvis_memory TO jarvis;

-- Create nodes table for knowledge graph
CREATE TABLE IF NOT EXISTS nodes (
    id VARCHAR(255) PRIMARY KEY,
    node_type VARCHAR(50) NOT NULL,
    name VARCHAR(255),
    category VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    attributes JSONB DEFAULT '{}'::jsonb,
    embedding vector(384)  -- all-MiniLM-L6-v2 dimension
);

CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_category ON nodes(category);
CREATE INDEX IF NOT EXISTS idx_nodes_name_trgm ON nodes USING gin(name gin_trgm_ops);

-- Create edges table for relationships
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

-- Create episodes table for memory episodes
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
    embedding vector(384),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_type ON episodes(episode_type);
CREATE INDEX IF NOT EXISTS idx_episodes_objects ON episodes USING gin(detected_objects);

-- Create missions table
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
CREATE INDEX IF NOT EXISTS idx_missions_type ON missions(mission_type);

-- Create vector similarity search indexes (using ivfflat for performance)
-- Note: These indexes are created after some data exists for better performance
-- Run these manually after initial data import:
-- CREATE INDEX IF NOT EXISTS idx_nodes_embedding ON nodes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
-- CREATE INDEX IF NOT EXISTS idx_episodes_embedding ON episodes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Insert core nodes
INSERT INTO nodes (id, node_type, name, category, attributes) VALUES
    ('entity:user', 'entity', 'User', 'person', '{"role": "owner"}'::jsonb),
    ('entity:jarvis', 'entity', 'Jarvis', 'ai_assistant', '{"role": "assistant"}'::jsonb)
ON CONFLICT (id) DO NOTHING;

-- Helpful views
CREATE OR REPLACE VIEW recent_episodes AS
SELECT id, timestamp, episode_type, summary, detected_objects
FROM episodes
ORDER BY timestamp DESC
LIMIT 100;

CREATE OR REPLACE VIEW active_missions AS
SELECT id, objective, mission_type, priority, created_at, target_entities
FROM missions
WHERE status = 'active'
ORDER BY 
    CASE priority 
        WHEN 'critical' THEN 1 
        WHEN 'high' THEN 2 
        WHEN 'normal' THEN 3 
        ELSE 4 
    END;

-- Function to search episodes by semantic similarity
CREATE OR REPLACE FUNCTION search_episodes_semantic(
    query_embedding vector(384),
    max_results INT DEFAULT 10
)
RETURNS TABLE (
    id VARCHAR(100),
    timestamp TIMESTAMP,
    episode_type VARCHAR(50),
    summary TEXT,
    distance FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        e.id,
        e.timestamp,
        e.episode_type,
        e.summary,
        (e.embedding <=> query_embedding)::FLOAT AS distance
    FROM episodes e
    WHERE e.embedding IS NOT NULL
    ORDER BY e.embedding <=> query_embedding
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;

-- Log initialization
DO $$
BEGIN
    RAISE NOTICE 'Jarvis Memory Database initialized successfully';
END $$;

