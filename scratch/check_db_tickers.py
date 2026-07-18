import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database.init_db import get_connection

conn = get_connection()
try:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT platform_name, store_id, product_name, brand_name, parent_ticker
            FROM qcomm_catalog_history
            ORDER BY observed_at DESC
            LIMIT 20;
        """)
        rows = cur.fetchall()
        print("\n" + "="*80)
        print("              TIMESCALEDB RESOLVED CORPORATE TICKERS REPORT")
        print("="*80)
        print(f"{'PLATFORM':<15} | {'STORE ID':<20} | {'PRODUCT NAME':<25} | {'BRAND':<12} | {'TICKER'}")
        print("-"*80)
        for r in rows:
            print(f"{r[0]:<15} | {r[1][:20]:<20} | {r[2][:25]:<25} | {r[3]:<12} | {r[4]}")
        print("="*80 + "\n")
finally:
    conn.close()
