#!/usr/bin/env bash
# ==============================================================================
# AttendSync - Automated Docker Deployment & Setup Script (POSIX / Linux / macOS)
# ==============================================================================

set -euo pipefail

echo "=================================================="
echo " AttendSync: Phase 5 Docker Deployment Pipeline"
echo "=================================================="

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker is not installed or not in PATH. Please install Docker." >&2
    exit 1
fi

# Detect docker compose plugin vs docker-compose legacy
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    echo "[ERROR] Neither 'docker compose' nor 'docker-compose' was found." >&2
    exit 1
fi

echo "[1/4] Building Docker image..."
$COMPOSE_CMD build --no-cache

echo "[2/4] Starting AttendSync container in detached mode..."
$COMPOSE_CMD up -d

echo "[3/4] Initializing and seeding database..."
sleep 3
$COMPOSE_CMD exec -T web flask init-db
$COMPOSE_CMD exec -T web flask seed-db

echo "[4/4] Verifying container status..."
$COMPOSE_CMD ps

echo "=================================================="
echo " AttendSync is running!"
echo " URL: http://localhost:5000"
echo " Health: http://localhost:5000/health"
echo " To view logs: $COMPOSE_CMD logs -f web"
echo " To stop: $COMPOSE_CMD down"
echo "=================================================="
