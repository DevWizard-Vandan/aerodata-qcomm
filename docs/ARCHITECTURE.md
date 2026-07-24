# Architecture Overview & Engineering Design

`aerodata-qcomm` is an institutional-grade quick-commerce alternative data platform designed to collect, validate, federate, and export high-frequency pricing, stockout, and catalog metrics across major Indian urban centers (e.g., Bengaluru, Mumbai, Delhi NCR).

---

## Technical Stack & Systems Layout

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

    subgraph Validation & Data Pipeline
        C & D & E --> I[DataGuardrail Engine]
        I -->|Z-Score Anomaly & Floor/Ceiling Checks| J[Entity & Ticker Resolver]
        I -->|Quarantined Records| K[quarantine.log]
    end

    subgraph Hybrid Storage Tiering
        J --> L[(Neon PostgreSQL / TimescaleDB Hot Tier)]
        L -->|qcomm_catalog_history| M[Database Triggers & Indexes]
        L -->|qcomm_prices| N[Fast Query Read View]
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

## Data Pipeline Components

### 1. Spatial Ingestion Engine (`scrapers/`)
- **Impersonation**: Employs `curl_cffi` to mimic Chrome 120 TLS fingerprints and bypass anti-bot challenges.
- **Resilient Networking**:
  - `NetworkManager`: Programmatic UDP/DNS fallback resolution.
  - `ProxyManager`: Sticky session proxy routing and mobile network IP rotation.
  - `SessionHarvester`: Dynamic cookie extraction for platform sessions.
- **Production Mode Toggle (`STRICT_PROD_MODE`)**:
  - `true` (Default): Disables mock generation. Raises explicit `ScraperHTTPError`, `RateLimitError` (429), or `ScraperParsingError` and emits structured JSON error telemetry.
  - `false`: Enables offline mock data generation for local developer testing.

### 2. Data Quality & Entity Resolution (`signals/`)
- **DataGuardrail**: Validates required fields, checks logical price boundaries (INR 1.00 to INR 50,000.00), and calculates rolling Z-scores against recent historical prices to filter out erroneous price anomalies into `logs/quarantine.log`.
- **EntityResolver**: Normalizes product names and brand strings to equity ticker symbols (`AMUL`, `PEPSI`, `TATACONSUM`, `ZEPTO`, `BLINKIT`, `SWIGGY`).

### 3. Federated Storage Model (`database/`)
- **Hot Tier**: Neon Serverless PostgreSQL / TimescaleDB hypertable storing point-in-time observations in `qcomm_catalog_history` and `qcomm_prices`. Auto-populates `timestamp` via PostgreSQL database triggers (`trg_populate_timestamp`).
- **Cold Storage Archival**: Automated script `database/offload_historical.py` queries records older than 30 days, serializes them into compressed Parquet datasets, uploads them to Hugging Face (`VaNam65/qcomm-cold-archive`), and purges cold rows from hot storage to fit within the 0.5 GiB free tier ceiling.

### 4. Quantitative Signal Engine (`signals/alpha_engine.py`)
- **Staples Inflation Index ($\Delta CPI$)**: Computes day-over-day price drift using Volume-Weighted Average Price (VWAP) across baseline essential categories (Dairy, Produce, Groceries).
- **Stockout Velocity Vector ($SVV$)**: Tracks daily stockout rates ($SR_t$) and first-derivative rate of change ($SVV_t = SR_t - SR_{t-1}$) smoothed with a 3-day exponential moving average (EMA).

---

## Telemetry & Failover Architecture

```mermaid
sequenceDiagram
    autonumber
    participant GHA as GitHub Actions Runner
    participant Orch as main.py Orchestrator
    participant Scraper as Scraper Modules
    participant DB as Neon Postgres
    participant Alert as Notifier (Telegram/Discord)

    GHA->>Orch: Execute python main.py
    Orch->>Scraper: fetch_page(lat, lng)
    alt HTTP 200 & Valid Payload
        Scraper-->>Orch: Return catalog JSON
        Orch->>DB: Bulk Upsert qcomm_catalog_history
    else HTTP 403 / 429 / Parsing Error (STRICT_PROD_MODE=true)
        Scraper-->>Scraper: Emit Structured JSON Error Log
        Scraper-->>Orch: Raise ScraperHTTPError / RateLimitError
        Orch->>Alert: Send alert telegram/discord payload (if in scheduler backoff)
    end
```

---

## Production Security & Password Gate

The Streamlit dashboard (`dashboard/app.py`) is protected by an entrypoint authentication gate. It checks session credentials against `st.secrets["DASHBOARD_PASSWORD"]` or environmental fallback `DASHBOARD_PASSWORD` (`admin123` by default) before rendering analytical views or running database queries.
