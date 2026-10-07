#!/bin/bash

# SHIRO Docker Runner Script
# For Linux & macOS
# Usage: ./run-docker.sh [command]

COMMAND=${1:-start}

print_header() {
    echo "╔═══════════════════════════════════════╗"
    echo "║      SHIRO v5 LLMA Docker Runner      ║"
    echo "╚═══════════════════════════════════════╝"
    echo ""
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        echo "❌ Error: Docker is not installed"
        echo "📥 Download: https://www.docker.com/products/docker-desktop"
        exit 1
    fi
    
    DOCKER_VERSION=$(docker --version)
    echo "✅ Docker found: $DOCKER_VERSION"
    echo ""
}

print_header
check_docker

case "$COMMAND" in
    start)
        echo "🚀 Starting SHIRO Docker container..."
        docker-compose up -d
        
        if [ $? -eq 0 ]; then
            sleep 3
            echo ""
            echo "✅ Container started successfully!"
            echo "📍 Access at: http://localhost:7474"
            echo "📋 View logs: docker-compose logs -f"
            echo ""
        else
            echo "❌ Failed to start container"
            exit 1
        fi
        ;;
    
    stop)
        echo "🛑 Stopping SHIRO Docker container..."
        docker-compose down
        
        if [ $? -eq 0 ]; then
            echo "✅ Container stopped"
        else
            echo "❌ Failed to stop container"
            exit 1
        fi
        ;;
    
    restart)
        echo "🔄 Restarting SHIRO Docker container..."
        docker-compose restart
        
        if [ $? -eq 0 ]; then
            sleep 2
            echo "✅ Container restarted"
            echo "📍 Access at: http://localhost:7474"
        else
            echo "❌ Failed to restart container"
            exit 1
        fi
        ;;
    
    logs)
        echo "📋 Showing live logs (Ctrl+C to stop)..."
        docker-compose logs -f
        ;;
    
    build)
        echo "🔨 Rebuilding Docker image..."
        docker-compose up --build -d
        
        if [ $? -eq 0 ]; then
            sleep 3
            echo ""
            echo "✅ Image rebuilt and container started!"
            echo "📍 Access at: http://localhost:7474"
        else
            echo "❌ Failed to rebuild image"
            exit 1
        fi
        ;;
    
    status)
        echo "📊 Container Status:"
        echo ""
        docker-compose ps
        echo ""
        echo "📊 Resource Usage:"
        docker stats shiro-llma --no-stream
        ;;
    
    *)
        echo "Usage: $0 [command]"
        echo ""
        echo "Available commands:"
        echo "  start      - Start container (default)"
        echo "  stop       - Stop container"
        echo "  restart    - Restart container"
        echo "  logs       - View live logs"
        echo "  build      - Rebuild and start"
        echo "  status     - Show container status"
        echo ""
        echo "Examples:"
        echo "  $0"
        echo "  $0 logs"
        echo "  $0 stop"
        ;;
esac
