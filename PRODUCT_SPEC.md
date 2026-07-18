# Institutional Alternative Data Specification: aerodata-qcomm

This document establishes the product metadata profile, data dictionaries, and compliance guidelines for the `aerodata-qcomm` alternative data engine, designed to deliver Point-in-Time (PIT) quick-commerce pricing, out-of-stock (OOS), and catalog signals to institutional quantitative funds.

---

## 1. Product Overview & Delivery SLAs

The `aerodata-qcomm` engine harvests real-time catalog feeds from Tier 1 Indian digital storefronts (Zepto, Blinkit, and Swiggy Instamart) across high-density urban locations. 

* **Daily Delivery SLA Bounds**: 
  * Files are finalized and delivered to S3-compatible endpoints daily at **01:30 UTC (07:00 IST)**.
  * This guarantees that data is fully partitioned, verified, and available prior to the NSE market open (09:15 IST).
* **Coverage Scope**:
  * Geography: Tier 1 dark store hotspot grids across Tier 1 Indian cities (Bengaluru, Mumbai, Delhi-NCR, Pune, Hyderabad, and Chennai).
  * Segment Tracking: Tracks core consumer goods (FMCG), dairy, staples, and fresh produce segments to act as high-frequency localized inflation and inventory proxies.

---

## 2. Core Schema Specifications

Data is delivered in optimized Apache Parquet format structured under Hive partitioning directories:
`s3://qcomm-delivery-bucket/year=YYYY/month=MM/day=DD/`

### Feed A: Brand Stockout Index (`brand_stockouts.parquet`)
This dataset tracks inventory availability levels for institutional FMCG brands.

| Column Name | Data Type | Description |
| :--- | :--- | :--- |
| `observed_date` | `VARCHAR` (Date) | The date when the storefront layouts were crawled (YYYY-MM-DD format). |
| `platform_name` | `VARCHAR` | The storefront origin (e.g. `Zepto`, `Blinkit`, `Swiggy Instamart`). |
| `brand_name` | `VARCHAR` | The parsed consumer brand name (e.g. `Amul`, `Surf Excel`, `Dove`, `Pepsi`). |
| `total_products`| `INT64` | Total number of unique product items monitored for this brand/platform day. |
| `oos_products`  | `INT64` | Total number of out-of-stock items for this brand/platform day. |
| `oos_rate`      | `DOUBLE` | Out-of-Stock (OOS) percentage rate: `(oos_products / total_products) * 100.0`. |

---

### Feed B: Staples Inflation Index (`food_inflation_index.parquet`)
This dataset measures day-over-day localized consumer price adjustments, acting as a high-frequency CPI proxy.

| Column Name | Data Type | Description |
| :--- | :--- | :--- |
| `observed_date` | `VARCHAR` (Date) | The observation date of the price index (YYYY-MM-DD format). |
| `dairy_avg_price`| `DOUBLE` | Average daily discount price in INR for the 'Dairy & Bread' category basket. |
| `produce_avg_price`| `DOUBLE` | Average daily discount price in INR for the 'Fruits & Vegetables' category basket. |
| `staples_avg_price`| `DOUBLE` | Average daily discount price in INR for the 'Groceries' (grains, flour, oils) basket. |
| `index_value`   | `DOUBLE` | Weighted Consumer Price Index value. Weights: Dairy=40%, Produce=30%, Staples=30%. |
| `inflation_dod` | `DOUBLE` | Day-over-Day price index percentage change: `(index_value_t / index_value_t-1) - 1.0`. |

---

## 3. Point-in-Time (PIT) Compliance Guarantee

To assure buy-side compliance officers and risk teams against look-ahead backtest contamination, the core database hypertable maintains a strict dual-timestamp schema:

1. **`observed_at` (TIMESTAMPTZ)**: The exact UTC timestamp when the storefront crawler snapshot was fetched from the target storefront API. This indicates *what* was happening on the digital shelf at that physical instant.
2. **`effective_at` (TIMESTAMPTZ)**: The exact UTC timestamp when the ingestion service completed processing and committed the record to the database hypertable, making it legally queryable for delivery.

### Backtest Purity Guideline
By querying historical data strictly where `effective_at <= [Backtest Simulation Time]`, quantitative backtesting engines can replicate the exact state of knowledge available at any historical execution point. This eliminates the risk of look-ahead bias caused by late-arriving records, retroactive pipeline updates, or timezone translation mismatches.
