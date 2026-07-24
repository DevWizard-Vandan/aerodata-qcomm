# API Reference & Quantitative Signal Specifications

This document details the edge API gateway endpoints, database schemas, and mathematical formulations powering the alternative data signals in `aerodata-qcomm`.

---

## 1. Cloudflare Worker Edge API

Located in `cloudflare-worker/` and deployed via Cloudflare Workers runtime.

### Endpoint: `GET /api/v1/alpha`

Queries the latest 100 pricing and stockout records directly from Neon PostgreSQL via WebSockets.

#### Request Headers
| Header | Type | Required | Description |
|---|---|---|---|
| `X-Alpha-Token` | String | **Yes** | Authentication token matching `ALPHA_API_KEY` |
| `Content-Type` | String | Optional | `application/json` |

#### Example Curl Request
```bash
curl -X GET "https://quantforge-keepalive.vandan-sharma06.workers.dev/api/v1/alpha" \
  -H "X-Alpha-Token: YOUR_SECURE_ALPHA_TOKEN"
```

#### Example Response Payload (`200 OK`)
```json
{
  "status": "success",
  "count": 2,
  "data": [
    {
      "observed_at": "2026-07-24T18:00:00Z",
      "platform_name": "Zepto",
      "store_id": "zepto_indiranagar",
      "product_id": "z-milk-901",
      "product_name": "Amul Taaza Toned Fresh Milk 1L",
      "category": "Dairy, Bread & Eggs",
      "brand_name": "Amul",
      "listed_price": 56.0,
      "discount_price": 54.0,
      "stock_status": true,
      "parent_ticker": "AMUL"
    },
    {
      "observed_at": "2026-07-24T18:00:00Z",
      "platform_name": "Blinkit",
      "store_id": "blinkit_hsr",
      "product_id": "b-bread-304",
      "product_name": "Harvest Gold Brown Bread 400g",
      "category": "Dairy, Bread & Eggs",
      "brand_name": "Harvest Gold",
      "listed_price": 50.0,
      "discount_price": 48.0,
      "stock_status": false,
      "parent_ticker": "BLINKIT"
    }
  ]
}
```

#### Error Responses
- `401 Unauthorized`: Missing or invalid `X-Alpha-Token` header.
- `500 Internal Server Error`: Database query or connectivity failure.

---

## 2. Quantitative Signal Formulations

### A. Staples Basket Inflation Index ($\Delta CPI$)

Computes daily annualized price index momentum from normalized high-volume essentials (Dairy, Produce, Groceries).

1. **Volume-Weighted Average Price (VWAP)**:
   $$\text{VWAP}_t = \frac{\sum_{i=1}^{N} P_{i,t} \cdot V_i}{\sum_{i=1}^{N} V_i}$$
   where $P_{i,t}$ is the discount price of item $i$ on day $t$, and $V_i$ is the assigned basket weighting.

2. **Day-over-Day (DoD) Pricing Drift ($\Delta CPI$)**:
   $$\Delta CPI_t = \frac{\text{Index}_t - \text{Index}_{t-1}}{\text{Index}_{t-1}}$$

3. **Volatility Bounds**:
   Evaluates a 7-day rolling standard deviation ($\sigma_{7d}$) around $\Delta CPI$ to flag hyper-inflationary spikes.

---

### B. Stockout Velocity Vector ($SVV$)

Quantifies inventory depletion momentum across spatial cluster zones ("Indiranagar", "HSR Layout", "Lower Parel").

1. **Daily Stockout Rate ($SR_t$)**:
   $$SR_t = \frac{\text{Count of Out-of-Stock Products}_t}{\text{Total Catalog Entries}_t}$$

2. **First-Derivative Velocity ($SVV_t$)**:
   $$SVV_t = SR_t - SR_{t-1}$$

3. **Smoothed Velocity Indicator ($SVV_{\text{EMA}}$)**:
   A 3-day Exponential Moving Average (EMA) to filter single-day noise:
   $$SVV_{\text{EMA}, t} = \alpha \cdot SVV_t + (1 - \alpha) \cdot SVV_{\text{EMA}, t-1}$$
   where $\alpha = \frac{2}{N+1} = 0.5$ for $N=3$.

---

## 3. Database Schema

### Table: `qcomm_catalog_history`

| Column Name | Type | Constraints | Description |
|---|---|---|---|
| `id` | BIGINT | PRIMARY KEY AUTO-INCREMENT | Surrogate key |
| `observed_at` | TIMESTAMPTZ | NOT NULL | Observation timestamp |
| `effective_at` | TIMESTAMPTZ | NOT NULL | Record effective timestamp |
| `platform_name` | VARCHAR(50) | NOT NULL | Platform (`Zepto`, `Blinkit`, `Swiggy Instamart`) |
| `store_id` | VARCHAR(100) | NOT NULL | Resolved store/cluster identifier |
| `product_id` | VARCHAR(100) | NOT NULL | Platform product ID |
| `product_name` | TEXT | NOT NULL | Cleaned product title |
| `category` | VARCHAR(100) | NOT NULL | Taxonomy category |
| `brand_name` | VARCHAR(100) | NOT NULL | Brand string |
| `listed_price` | NUMERIC(10,2) | NOT NULL | MRP / original listed price (INR) |
| `discount_price` | NUMERIC(10,2) | NOT NULL | Effective selling price (INR) |
| `stock_status` | BOOLEAN | NOT NULL | `true` if in stock, `false` if out of stock |
| `parent_ticker` | VARCHAR(20) | NOT NULL | Resolved equity ticker (`AMUL`, `PEPSI`, etc.) |
| `timestamp` | TIMESTAMPTZ | DEFAULT NOW() | Trigger-populated insertion timestamp |
