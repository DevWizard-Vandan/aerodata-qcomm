# Deployment & Operations Guide

This guide details deployment options for running `aerodata-qcomm` in local, containerized, serverless, and cloud environments.

---

## 1. Docker Compose (Full Stack)

Deploys PostgreSQL/TimescaleDB, the background scheduler daemon, and the Streamlit dashboard using container orchestration.

### Prerequisites
- Docker Engine 24.0+
- Docker Compose v2+

### Step-by-Step Execution

1. **Configure Environment Variables**:
   Create a `.env` file in the project root:
   ```bash
   DB_HOST=timescaledb
   DB_PORT=5432
   DB_USER=postgres
   DB_PASSWORD=your_secure_password
   DB_NAME=postgres
   DATABASE_URL=postgresql://postgres:your_secure_password@timescaledb:5432/postgres
   
   STRICT_PROD_MODE=true
   NOTIFICATION_PROVIDER=telegram
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_CHAT_ID=your_chat_id
   TELEGRAM_CUSTOM_GATEWAY=https://quantforge-keepalive.vandan-sharma06.workers.dev
   DASHBOARD_PASSWORD=admin123
   ```

2. **Launch Container Services**:
   ```bash
   docker compose up -d --build
   ```

3. **Verify Active Services**:
   ```bash
   docker compose ps
   ```
   - Streamlit Dashboard: `http://localhost:8501`
   - Database Host: `localhost:5432`

---

## 2. GitHub Actions Scheduled Automation

The repository contains an automated workflow configured in `.github/workflows/scheduled_crawlers.yml`.

### Triggers
- **Nightly Ingestion**: Executes at `23:30 IST` (`30 18 * * *` UTC) to harvest spatial catalogs across urban clusters.
- **Hibernation Keep-Alive**: Executes every 10 hours (`0 */10 * * *` UTC) pushing an empty keep-alive commit to prevent Streamlit Cloud free-tier inactivity sleep.
- **Manual Trigger**: Can be dispatched manually via GitHub CLI or UI (`workflow_dispatch`).

### Required GitHub Repository Secrets
Map the following environment secrets in your GitHub repository (`Settings -> Secrets and variables -> Actions`):
- `DATABASE_URL`: Connection string for Neon Serverless Postgres.
- `TELEGRAM_BOT_TOKEN`: Telegram bot token string.
- `TELEGRAM_CHAT_ID`: Recipient Telegram chat ID.
- `TELEGRAM_CUSTOM_GATEWAY`: Custom Cloudflare Worker gateway URL.
- `HF_TOKEN`: Hugging Face API access token (Write permission).
- `HF_REPO_ID`: Target dataset repository (e.g. `VaNam65/qcomm-cold-archive`).
- `DASHBOARD_PASSWORD`: Password for dashboard access gate.

### Dispatching via GitHub CLI (`gh`)
```bash
gh workflow run scheduled_crawlers.yml --ref main
gh run watch
```

---

## 3. Cloudflare Worker Edge Gateway

Located in `cloudflare-worker/`. Exposes `/api/v1/alpha` on Cloudflare's serverless edge.

### Prerequisites
- Node.js 18+
- Wrangler CLI (`npm install -g wrangler`)

### Deployment Steps
```bash
cd cloudflare-worker
npm install
npx wrangler secret put ALPHA_API_KEY
# Enter your secure token when prompted

npx wrangler deploy
```

---

## 4. Streamlit Cloud Deployment

1. Connect your GitHub repository (`DevWizard-Vandan/aerodata-qcomm`) to Streamlit Community Cloud.
2. Set Main File Path: `dashboard/app.py`.
3. Add Advanced Settings / Secrets:
   ```toml
   DASHBOARD_PASSWORD = "admin123"
   DATABASE_URL = "postgresql://user:pass@ep-xxxx.neon.tech/neondb?sslmode=require"
   HF_TOKEN = "hf_xxxx"
   HF_REPO_ID = "VaNam65/qcomm-cold-archive"
   ```
