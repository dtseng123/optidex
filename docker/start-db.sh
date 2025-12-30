#!/bin/bash
# Start Jarvis Memory Database (PostgreSQL + pgvector)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Jarvis Memory Database ==="

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed"
    echo "Install with: curl -fsSL https://get.docker.com | sh"
    exit 1
fi

# Check if docker-compose or docker compose is available
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
else
    echo "Error: docker-compose is not installed"
    echo "Install with: sudo apt install docker-compose-plugin"
    exit 1
fi

case "${1:-start}" in
    start)
        echo "Starting PostgreSQL + pgvector..."
        $COMPOSE_CMD up -d
        
        echo "Waiting for database to be ready..."
        sleep 5
        
        # Check if database is ready
        for i in {1..30}; do
            if docker exec jarvis-memory-db pg_isready -U jarvis -d jarvis_memory > /dev/null 2>&1; then
                echo "Database is ready!"
                break
            fi
            echo "Waiting... ($i/30)"
            sleep 2
        done
        
        # Show connection info
        echo ""
        echo "Connection details:"
        echo "  Host: localhost"
        echo "  Port: 5432"
        echo "  Database: jarvis_memory"
        echo "  User: jarvis"
        echo "  Password: jarvis_memory_2024"
        echo ""
        echo "Test connection:"
        echo "  docker exec -it jarvis-memory-db psql -U jarvis -d jarvis_memory"
        ;;
    
    stop)
        echo "Stopping database..."
        $COMPOSE_CMD down
        ;;
    
    restart)
        echo "Restarting database..."
        $COMPOSE_CMD restart
        ;;
    
    logs)
        $COMPOSE_CMD logs -f
        ;;
    
    status)
        $COMPOSE_CMD ps
        echo ""
        if docker exec jarvis-memory-db pg_isready -U jarvis -d jarvis_memory > /dev/null 2>&1; then
            echo "Status: HEALTHY"
            
            # Show some stats
            echo ""
            docker exec jarvis-memory-db psql -U jarvis -d jarvis_memory -c "
                SELECT 
                    (SELECT COUNT(*) FROM nodes) as nodes,
                    (SELECT COUNT(*) FROM edges) as edges,
                    (SELECT COUNT(*) FROM episodes) as episodes,
                    (SELECT COUNT(*) FROM missions WHERE status = 'active') as active_missions;
            " 2>/dev/null || true
        else
            echo "Status: NOT READY"
        fi
        ;;
    
    reset)
        echo "WARNING: This will delete all data!"
        read -p "Are you sure? (y/N) " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            $COMPOSE_CMD down -v
            echo "Database reset. Run '$0 start' to recreate."
        fi
        ;;
    
    shell)
        docker exec -it jarvis-memory-db psql -U jarvis -d jarvis_memory
        ;;
    
    *)
        echo "Usage: $0 {start|stop|restart|logs|status|reset|shell}"
        exit 1
        ;;
esac

