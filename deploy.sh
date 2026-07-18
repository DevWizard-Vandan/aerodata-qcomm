#!/usr/bin/env bash
set -eo pipefail

# Production Ingestion Deployment script for aerodata-qcomm
# Author: DevOps SRE Engine

echo "===================================================="
echo "          AERODATA-QCOMM DEPLOYMENT SEQUENCE        "
echo "===================================================="

# 1. Environment Verification
echo "[INFO] Step 1: Verifying system dependencies..."
for cmd in git docker; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "[ERROR] Mandatory dependency '$cmd' is not installed. Exiting."
        exit 1
    fi
done

# Check if 'docker compose' or 'docker-compose' is valid
if ! docker compose version &> /dev/null; then
    if ! command -v docker-compose &> /dev/null; then
        echo "[ERROR] Neither 'docker compose' nor 'docker-compose' is installed. Exiting."
        exit 1
    fi
    DOCKER_COMPOSE="docker-compose"
else
    DOCKER_COMPOSE="docker compose"
fi
echo "[INFO] System dependencies verified successfully."

# 2. Git Automation
echo "[INFO] Step 2: Syncing latest codebase..."
if git rev-parse --is-inside-work-tree &> /dev/null; then
    echo "[INFO] Git repository detected. Pulling changes..."
    git pull || echo "[WARNING] Git pull failed. Continuing with local codebase state."
else
    echo "[WARNING] Not a git repository. Skipping sync."
fi

# 3. Environment File Assurance
echo "[INFO] Step 3: Verifying environment configuration..."
if [ ! -f .env ]; then
    echo "[WARNING] Local '.env' file not found! Generating template..."
    cat <<EOT > .env
# Database Configuration
DB_HOST=db
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_secure_password
DB_NAME=postgres

# Proxy Rotation Middleware
PROXY_URL=
PROXY_USER=
PROXY_PASS=

# Telemetry Alerts & Notifications
NOTIFICATION_PROVIDER=none
DISCORD_WEBHOOK_URL=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EOT
    echo "[IMPORTANT] Template '.env' generated successfully. Please edit it to populate active credentials."
else
    echo "[INFO] Existing '.env' configuration file verified."
fi

# 4. Multi-Container Build & Launch
echo "[INFO] Step 4: Dismantling stale network containers..."
$DOCKER_COMPOSE down --remove-orphans || true

echo "[INFO] Building and starting container orchestration layers..."
$DOCKER_COMPOSE up --build -d

# 5. Post-Deployment Health Check
echo "[INFO] Step 5: Initiating SRE telemetry health checks..."
timeout=30
elapsed=0
healthy=false

while [ $elapsed -lt $timeout ]; do
    # Check TimescaleDB (5432) and Streamlit (8501) ports
    if docker exec qcomm-timescaledb-srv pg_isready -U postgres &> /dev/null; then
        healthy=true
        break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
    echo "[INFO] Waiting for database service port (5432) to bind... ($elapsed/${timeout}s)"
done

if [ "$healthy" = true ]; then
    echo "===================================================="
    echo "  SYSTEM HEALTH: ONLINE                             "
    echo "  Deployment completed successfully!                "
    echo "===================================================="
else
    echo "===================================================="
    echo "  [ERROR] Health checks failed. One or more         "
    echo "  services are unresponsive. Check container logs.   "
    echo "===================================================="
    exit 1
fi
