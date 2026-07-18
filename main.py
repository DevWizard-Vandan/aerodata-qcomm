import sys
import os
import logging
from datetime import datetime, timezone
import pandas as pd
import numpy as np

from database.init_db import initialize_database, get_connection
from scrapers.zepto import ZeptoScraper
from scrapers.blinkit import BlinkitScraper
from scrapers.swiggy import SwiggyScraper
from scrapers.spatial_filter import SpatialFilterEngine
from scrapers.network_manager import NetworkManager
from signals.exporter import export_signals
from signals.entity_resolver import EntityResolver
from scrapers.session_harvester import SessionHarvester
from spatial_config.geospatial_matrix import GEOSPATIAL_CLUSTERS
from signals.data_guardrails import DataGuardrail

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def run_pipeline():
    logger.info("Initializing aerodata-qcomm alternative data engine...")
    
    total_rows = 0
    breakdown = []
    
    resolver = EntityResolver()
    harvester = SessionHarvester()
    guardrail = DataGuardrail()
    
    quarantine_log_path = os.path.join("logs", "quarantine.log")
    os.makedirs("logs", exist_ok=True)
    
    # 1. Initialize database schema & policies
    logger.info("Step 1: Initializing Database Infrastructure...")
    initialize_database()

    # 2. Initialize spatial filter engine mapping
    logger.info("Step 2: Loading spatial matrix clusters...")
    scan_points = GEOSPATIAL_CLUSTERS

    # 3. Initialize Network Manager
    logger.info("Step 3: Initializing Network Resiliency Manager...")
    network_manager = NetworkManager()

    # 4. Instantiate scrapers
    scrapers = {
        "Zepto": ZeptoScraper(),
        "Blinkit": BlinkitScraper(),
        "Swiggy Instamart": SwiggyScraper()
    }

    all_records = []
    now = datetime.now(timezone.utc)

    # Open a single shared validation connection for high-performance running Z-score checks
    validation_conn = None
    try:
        validation_conn = get_connection()
    except Exception as e:
        logger.warning(f"Could not open database connection for Z-score checks: {e}")

    # 5. Execute crawls across spatial coordinates and platforms
    logger.info(f"Step 5: Executing spatial catalog scan across {len(scan_points)} coordinates for 3 platforms...")
    
    # Scan all mapped urban consumption grids sequentially
    for idx, point in enumerate(scan_points):
        lat = point["latitude"]
        lng = point["longitude"]
        city = point.get("city", "Unknown")
        cluster_name = point.get("name", "Unknown")
        zone = point.get("zone", "Unknown")
        
        logger.info(f"Scanning cluster #{idx+1}: {cluster_name}, {city} (lat={lat}, lng={lng}, zone={zone})")
        
        for name, scraper in scrapers.items():
            logger.info(f"Harvesting from platform '{name}' at ({lat}, {lng})...")
            try:
                # Fetch raw data applying DNS fallback and proxies
                raw_response = scraper.fetch_page(lat, lng, network_manager, session_harvester=harvester, session_key=zone)
                
                # Parse layout recursively
                parsed_items = scraper.parse_layout(raw_response)
                
                # Transform to DB insertion format with dynamic entity resolution mapping & data guardrails
                for item in parsed_items:
                    resolved_store_id = f"{item['platform_name'].lower().replace(' ', '_')}_{zone}"
                    resolved_ticker = resolver.resolve(
                        brand_name=item.get("brand_name"),
                        product_name=item.get("product_name"),
                        store_id=resolved_store_id,
                        platform_name=item.get("platform_name")
                    )
                    
                    record_dict = {
                        "platform_name": item["platform_name"],
                        "store_id": resolved_store_id,
                        "product_id": item["product_id"],
                        "product_name": item["product_name"],
                        "category": item["category"],
                        "brand_name": item["brand_name"],
                        "listed_price": item["listed_price"],
                        "discount_price": item["discount_price"],
                        "stock_status": item["stock_status"],
                        "parent_ticker": resolved_ticker
                    }
                    
                    is_valid, reason = guardrail.validate(record_dict, conn=validation_conn)
                    if is_valid:
                        all_records.append((
                            now,
                            now,
                            item["platform_name"],
                            resolved_store_id,
                            item["product_id"],
                            item["product_name"],
                            item["category"],
                            item["brand_name"],
                            item["listed_price"],
                            item["discount_price"],
                            item["stock_status"],
                            resolved_ticker
                        ))
                    else:
                        logger.warning(f"Quarantining corrupt or anomaly record {item['product_id']}: {reason}")
                        try:
                            with open(quarantine_log_path, "a") as qf:
                                timestamp = datetime.now(timezone.utc).isoformat()
                                qf.write(f"{timestamp} | {item['product_id']} | {item['product_name']} | {reason}\n")
                        except Exception as log_err:
                            logger.error(f"Failed writing to quarantine.log: {log_err}")
            except Exception as e:
                logger.error(f"Failed harvesting platform '{name}' at ({lat}, {lng}): {e}")

    # Close database check mapping if active
    if validation_conn:
        try:
            validation_conn.close()
        except Exception:
            pass

    if 'spatial_engine' in locals():
        spatial_engine.close()

    if not all_records:
        raise RuntimeError("No product records were parsed. Exiting pipeline.")

    # 6. Bulk upsert to TimescaleDB
    logger.info(f"Step 6: Executing bulk upsert of {len(all_records)} records into TimescaleDB...")
    conn = None
    try:
        conn = get_connection()
        conn.autocommit = True
        with conn.cursor() as cur:
            from psycopg2.extras import execute_values
            
            upsert_query = """
            INSERT INTO qcomm_catalog_history (
                observed_at, effective_at, platform_name, store_id, product_id,
                product_name, category, brand_name, listed_price, discount_price,
                stock_status, parent_ticker
            ) VALUES %s
            ON CONFLICT (observed_at, platform_name, store_id, product_id)
            DO UPDATE SET
                effective_at = EXCLUDED.effective_at,
                product_name = EXCLUDED.product_name,
                category = EXCLUDED.category,
                brand_name = EXCLUDED.brand_name,
                listed_price = EXCLUDED.listed_price,
                discount_price = EXCLUDED.discount_price,
                stock_status = EXCLUDED.stock_status,
                parent_ticker = EXCLUDED.parent_ticker;
            """
            
            execute_values(cur, upsert_query, all_records)
            logger.info("Bulk upsert successfully completed.")

            # 7. E2E Multi-Platform Verification
            logger.info("Step 7: Executing E2E multi-platform verification summary...")
            
            # Fetch platform breakdown counts
            cur.execute("""
                SELECT platform_name, COUNT(*), COUNT(CASE WHEN stock_status = TRUE THEN 1 END), AVG(discount_price)
                FROM qcomm_catalog_history
                GROUP BY platform_name;
            """)
            breakdown = cur.fetchall()
            
            # Fetch total count
            cur.execute("SELECT COUNT(*) FROM qcomm_catalog_history;")
            total_rows = cur.fetchone()[0]
            
            # Print DB verification report
            print("\n" + "="*95)
            print("                 E2E EXPANDED PIPELINE INGESTION REPORT")
            print("="*95)
            print(f"Total Rows Committed to Hypertable: {total_rows}")
            print("-"*95)
            print("PLATFORM SUMMARY STATISTICS:")
            
            stats_df = pd.DataFrame(breakdown, columns=["Platform", "Total Records", "In-Stock Count", "Avg Discount Price (INR)"])
            print(stats_df.to_string(index=False))
            print("="*95 + "\n")

    except Exception as e:
        logger.error(f"Pipeline database loading or verification failed: {e}")
        raise e
    finally:
        if conn:
            conn.close()

    # 8. Trigger Signal Production and Exporter
    logger.info("Step 8: Triggering Signal Generation and Parquet Exporter...")
    export_success = export_signals()
    if not export_success:
        raise RuntimeError("Failed to generate and export alternative data signals.")
        
    # 9. Verify and Print Parquet Export Reports
    logger.info("Step 9: Verifying local simulated S3 Parquet delivery...")
    s3_dir = BASE_S3_DIR = "s3_delivery_simulation"
    if os.path.exists(s3_dir):
        parquet_files = []
        for root, dirs, files in os.walk(s3_dir):
            for file in files:
                if file.endswith(".parquet"):
                    parquet_files.append(os.path.join(root, file))
                    
        print("\n" + "="*95)
        print("                 E2E PRODUCTIZATION LAYER EXPORT SUMMARY")
        print("="*95)
        print("GENERATED PARQUET FILES:")
        for pf in parquet_files:
            size_kb = os.path.getsize(pf) / 1024.0
            print(f" -> {pf} ({size_kb:.2f} KB)")
        print("-"*95)
        
        # Display sample from brand stockouts
        stockout_files = [f for f in parquet_files if "brand_stockouts" in f]
        if stockout_files:
            print("SAMPLE FROM EXPORTED BRAND STOCKOUT RATES:")
            try:
                sdf = pd.read_parquet(stockout_files[0])
                print(sdf.head(5).to_string(index=False))
            except Exception as e:
                logger.error(f"Failed to read exported stockout parquet: {e}")
                
        # Display sample from inflation index
        inflation_files = [f for f in parquet_files if "food_inflation" in f]
        if inflation_files:
            print("-"*95)
            print("SAMPLE FROM EXPORTED STAPLES INFLATION INDEX (CPI PROXY):")
            try:
                idf = pd.read_parquet(inflation_files[0])
                print(idf.head(5).to_string(index=False))
            except Exception as e:
                logger.error(f"Failed to read exported inflation parquet: {e}")
        print("="*95 + "\n")
    else:
        raise RuntimeError("Simulated S3 delivery directory does not exist.")

    # Return metrics for scheduler heartbeat
    return {
        "total_rows_committed": total_rows,
        "platform_breakdown": {row[0]: int(row[1]) for row in breakdown}
    }

if __name__ == "__main__":
    run_pipeline()
