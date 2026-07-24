# aerodata-qcomm

[![Python 3.10](https://img.shields.io/badge/Python-3.10+-blue.svg?logo=python&logoColor=white)](https://www.python.org/downloads/release/python-3100/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![GitHub Actions](https://img.shields.io/badge/Automation-GitHub%20Actions-2088FF?logo=github-actions&logoColor=white)](https://github.com/features/actions)
[![Cloudflare Workers](https://img.shields.io/badge/Edge%20API-Cloudflare%20Workers-F38020?logo=cloudflare&logoColor=white)](https://workers.cloudflare.com/)

**Institutional-grade quick-commerce alternative data engine** for harvesting, validating, federating, and analyzing high-frequency pricing, stockout velocity, and catalog metrics across **Zepto**, **Blinkit**, and **Swiggy Instamart** in major Indian urban consumption clusters (Bengaluru, Mumbai, Delhi NCR).

---

## 📋 Table of Contents

- [Project Overview](#-project-overview)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [Project Directory Layout](#-project-directory-layout)
- [Quick Start & Installation](#-quick-start--installation)
- [Configuration (.env)](#-configuration-env)
- [Pipeline & System Operations](#-pipeline--system-operations)
- [Quantitative Signals](#-quantitative-signals)
- [Edge API & Visualizations](#-edge-api--visualizations)
- [Documentation Hub](#-documentation-hub)
- [License & Maintainer](#-license--maintainer)

---

## ⚡ Project Overview

`aerodata-qcomm` solves the technical and analytical challenges of harvesting high-frequency quick-commerce alternative data at scale:

1. **Resilient Ingestion**: Bypasses anti-bot controls using `curl_cffi` TLS Chrome 120 fingerprint impersonation, sticky proxy pools, dynamic session cookie harvesting, and UDP/DNS fallbacks.
2. **Production Mode Toggle (`STRICT_PROD_MODE`)**: Enforces strict raw exception propagation (`ScraperHTTPError`, `RateLimitError`, `ScraperParsingError`) and outputs structured JSON telemetry logs during production burn-in.
3. **Data Quality & Resolution**: Filters anomaly prices using rolling historical Z-score checks and maps unstructured product strings to ticker symbols (`AMUL`, `PEPSI`, `TATACONSUM`, etc.).
4. **Hybrid Storage Federation**: Pairs Neon Serverless PostgreSQL / TimescaleDB (Hot Tier) with compressed Parquet archives stored on Hugging Face (`VaNam65/qcomm-cold-archive`) to stay within serverless tier ceilings.
5. **Alpha Signal Derivation**: Calculates the **Staples Inflation Index ($\Delta CPI$)** and the **Stockout Velocity Vector ($SVV$)** to track daily price momentum and supply depletion rates.

---

## ✨ Key Features

- **Multi-Platform Coverage**: Native scrapers for **Zepto**, **Blinkit**, and **Swiggy Instamart**.
- **Geospatial Scanning**: Pre-configured coordinate matrix spanning key darkstore zones (Indiranagar, HSR Layout, Lower Parel).
- **Network Management**:
  - `NetworkManager`: Programmatic UDP DNS resolver.
  - `ProxyManager`: Sticky session proxy rotation & mobile IP refresh.
  - `SessionHarvester`: Dynamic headless session cookie extraction.
- **Data Quality Guardrails**: Price bounds (INR 1.00 - 50,000.00), required field checks, and Z-score anomaly logging to `logs/quarantine.log`.
- **Hybrid Data Federation**: Seamless query layer combining active hot PostgreSQL rows with historical Hugging Face cold storage Parquet files.
- **Institutional Signals**:
  - **$\Delta CPI$**: Volume-Weighted Average Price (VWAP) daily inflation drift across essential food categories.
  - **$SVV$**: 3-day Exponential Moving Average (EMA) of day-over-day stockout rate changes.
- **Operations & Telemetry**:
  - `utils/notifier.py`: Automated Telegram and Discord alert integration.
  - SRE System Health panel & password-protected Streamlit dashboard interface.

---

## 🏗️ Architecture

```mermaid
flowchart TB
    subgraph Ingestion Layer
        A[GitHub Actions / Scheduler Daemon] -->|Cron 23:30 IST| B[main.py Orchestrator]
        B --> C[Zepto Scraper]
        B --> D[Blinkit Scraper]
        B --> E[Swiggy Instamart Scraper]
        
        C & D & E --> F[curl_cffi + TLS Chrome 120 Impersonation]
        F --> G[NetworkManager + ProxyManager]
        G --> H[SessionHarvester Cookies]
    end

    subgraph Validation & Guardrails
        C & D & E --> I[DataGuardrail Engine]
        I -->|Z-Score Anomaly & Price Bounds| J[Entity & Ticker Resolver]
        I -->|Corrupt Records| K[quarantine.log]
    end

    subgraph Hybrid Storage Tiering
        J --> L[(Neon PostgreSQL / TimescaleDB Hot Tier)]
        L -->|qcomm_catalog_history| M[Database Triggers & Indexes]
        L -->|qcomm_prices| N[Sync Query Table]
        L -->|Records > 30 Days| O[offload_historical.py]
        O --> P[Hugging Face Cold Parquet Vault<br/>VaNam65/qcomm-cold-archive]
    end

    subgraph Signal Processing & Export
        L --> Q[Signal Engine / alpha_engine.py]
        Q --> R[Staples Inflation Index Δ CPI]
        Q --> S[Stockout Velocity Vector SVV]
        Q --> T[Parquet Exporter<br/>s3_delivery_simulation/]
    end

    subgraph Access & Visualization Layer
        L & P --> U[Streamlit Federated Dashboard]
        L --> V[Cloudflare Worker Edge API<br/>GET /api/v1/alpha]
        A -->|Pipeline Failure| W[utils/notifier.py<br/>Telegram / Discord Alerts]
```

---

## 📁 Project Directory Layout

```text
aerodata-qcomm/
├── main.py                       # Ingestion pipeline entry point
├── scheduler.py                  # Daemon process with retry & backoff logic
├── config.py                     # Global configuration & database settings
├── requirements.txt              # Python dependencies
├── Dockerfile                    # Container definition
├── docker-compose.yml            # Multi-service stack (DB + Scheduler + Dashboard)
├── deploy.sh                     # Automated container deployment script
├── LICENSE                       # MIT License
├── .github/workflows/            # GitHub Actions CI/CD & scheduled workflows
│   └── scheduled_crawlers.yml    # Nightly 23:30 IST crawler & keep-alive workflow
├── scrapers/                     # Scraper connectors & network infrastructure
│   ├── exceptions.py             # STRICT_PROD_MODE, exceptions, & JSON logging
│   ├── zepto.py                  # Zepto PWA scraper
│   ├── blinkit.py                # Blinkit layout scraper
│   ├── swiggy.py                 # Swiggy Instamart scraper
│   ├── network_manager.py        # UDP/DNS fallback resolution
│   ├── proxy_manager.py          # Proxy pool & sticky session management
│   ├── session_harvester.py      # Cookie harvester
│   ├── spatial_filter.py         # Geospatial coordinate filter
│   ├── web_targets.py            # Platform target URLs
│   └── test_connection.py        # Diagnostic connector script
├── signals/                      # Data quality & quantitative signal engine
│   ├── alpha_engine.py           # Staples Index (Δ CPI) & Stockout Velocity (SVV)
│   ├── data_guardrails.py        # Z-score anomaly checks & validation rules
│   ├── entity_resolver.py        # Brand/product string to equity ticker mapping
│   └── exporter.py               # Simulated S3 Parquet export manager
├── database/                     # Database schemas & serverless tiering
│   ├── init_db.py                # Table schemas & PostgreSQL triggers
│   └── offload_historical.py     # Hot-to-Cold Hugging Face Parquet offloader
├── dashboard/                    # Streamlit analytical dashboard
│   ├── app.py                    # Multi-tab dashboard & password lock screen
│   └── .streamlit/               # Streamlit styling configuration
├── spatial_config/               # Target geospatial coordinate matrices
│   └── geospatial_matrix.py      # Urban cluster definitions (BLR, BOM, DEL)
├── cloudflare-worker/            # Edge API Gateway runtime
│   ├── src/index.js              # Edge worker API routing logic
│   └── wrangler.toml             # Cloudflare Worker configuration
└── docs/                         # Repository documentation suite
    ├── ARCHITECTURE.md           # Deep-dive architecture & data pipeline guide
    ├── API_AND_SIGNALS.md        # Edge API docs & signal math formulations
    ├── DEPLOYMENT.md             # Docker, GHA, Streamlit & Worker deployment guide
    └── CONTRIBUTING.md           # Engineering guidelines & workflow rules
```

---

## 🚀 Quick Start & Installation

### Prerequisites
- **Python 3.10+**
- **PostgreSQL 14+ / TimescaleDB** (or Neon Serverless Postgres)
- **Git**

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/DevWizard-Vandan/aerodata-qcomm.git
   cd aerodata-qcomm
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate        # Linux / macOS
   # .\venv\Scripts\activate       # Windows PowerShell
   ```

3. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

## ⚙️ Configuration (.env)

Create a `.env` file in the project root:

```env
# Production Mode Toggle (default: true)
STRICT_PROD_MODE=true

# Database Credentials
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_secure_password
DB_NAME=postgres
DATABASE_URL=postgresql://postgres:your_secure_password@localhost:5432/postgres

# Telemetry Alerts (Telegram / Discord)
NOTIFICATION_PROVIDER=telegram
TELEGRAM_BOT_TOKEN=8743897444:AAHGfE7jqM2nsC5SckI_N6yJkR0sPAfS4Y4
TELEGRAM_CHAT_ID=5751968943
TELEGRAM_CUSTOM_GATEWAY=https://quantforge-keepalive.vandan-sharma06.workers.dev
DISCORD_WEBHOOK_URL=

# Proxy Configuration (Optional)
PROXY_URL=
PROXY_USER=
PROXY_PASS=

# Hugging Face Cold Storage Vault
HF_TOKEN=hf_your_token_here
HF_REPO_ID=VaNam65/qcomm-cold-archive

# Dashboard Security Access Gate
DASHBOARD_PASSWORD=admin123
```

---

## 💻 Pipeline & System Operations

### 1. Execute Ingestion Pipeline Once
```bash
python main.py
```

### 2. Launch Daily Scheduler Daemon
Runs continuous background monitoring with automated retries and exponential backoff:
```bash
python scheduler.py
```
*To execute a quick 10-second test run*:
```bash
python scheduler.py --test
```

### 3. Run Hot-to-Cold Data Archival
Offloads records older than 30 days to Hugging Face Parquet storage:
```bash
python database/offload_historical.py
```

### 4. Launch Analytics Dashboard
```bash
streamlit run dashboard/app.py
```
*Access the dashboard at `http://localhost:8501` (Password: `admin123`).*

### 5. Run via Docker Compose
```bash
docker compose up -d --build
```

---

## 📈 Quantitative Signals

### Staples Basket Inflation Index ($\Delta CPI$)
Tracks volume-weighted pricing momentum across essential food staples:
$$\Delta CPI_t = \frac{\text{Index}_t - \text{Index}_{t-1}}{\text{Index}_{t-1}}$$

### Stockout Velocity Vector ($SVV$)
Measures the first-derivative rate of change of inventory depletion across darkstores, smoothed via a 3-day Exponential Moving Average (EMA):
$$SVV_t = SR_t - SR_{t-1}$$
$$SVV_{\text{EMA}, t} = 0.5 \cdot SVV_t + 0.5 \cdot SVV_{\text{EMA}, t-1}$$

*See [docs/API_AND_SIGNALS.md](docs/API_AND_SIGNALS.md) for full mathematical formulations.*

---

## 🌐 Edge API & Visualizations

### Cloudflare Worker Edge Route
- **Route**: `GET /api/v1/alpha`
- **Header**: `X-Alpha-Token: <token>`
- **Response**: Real-time JSON array of latest pricing and stockout data.

### Streamlit Dashboard Features
- 🔒 **Security Gate**: Password lock screen protecting alternative data signals.
- 📊 **Cross-Regional Arbitrage**: Multi-city spatial pricing comparisons.
- 📈 **Alpha Signals**: Dual-axis Plotly charts for $\Delta CPI$ and $SVV$.
- 🛠️ **SRE Health Monitoring**: Real-time database telemetry, system status, and Hugging Face archive sync state.

---

## 📚 Documentation Hub

Explore the full documentation suite in the [`docs/`](docs/) directory:

- 📐 [**Architecture Guide** (`docs/ARCHITECTURE.md`)](docs/ARCHITECTURE.md) - Pipeline design, network management, & hot/cold tiering.
- 🔢 [**API & Signal Specs** (`docs/API_AND_SIGNALS.md`)](docs/API_AND_SIGNALS.md) - Cloudflare Worker API specifications & signal formulas.
- 🚀 [**Deployment Guide** (`docs/DEPLOYMENT.md`)](docs/DEPLOYMENT.md) - Docker, GitHub Actions, Streamlit Cloud, & Worker setup.
- 🤝 [**Contributing Guide** (`docs/CONTRIBUTING.md`)](docs/CONTRIBUTING.md) - Engineering practices, code style, & PR workflow.

---

## 📄 License & Maintainer

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.

**Project Lead & Maintainer**:
- **Author**: Vandan Sharma ([@DevWizard-Vandan](https://github.com/DevWizard-Vandan))
- **Email**: `vandan.sharma06@gmail.com`
- **Repository**: [github.com/DevWizard-Vandan/aerodata-qcomm](https://github.com/DevWizard-Vandan/aerodata-qcomm)
