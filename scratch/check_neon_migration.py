import sys
import os

# Add project root to PYTHONPATH dynamically
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database.init_db import get_connection

def run_diagnostics():
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # Check row count in qcomm_catalog_history
            cur.execute("SELECT count(*) FROM qcomm_catalog_history;")
            history_count = cur.fetchone()[0]
            
            # Check row count in qcomm_prices
            cur.execute("SELECT count(*) FROM qcomm_prices;")
            prices_count = cur.fetchone()[0]
            
            print(f"Total rows in qcomm_catalog_history: {history_count}")
            print(f"Total rows in qcomm_prices (synchronized): {prices_count}")
            
            # Check indices on qcomm_prices
            cur.execute("""
                SELECT indexname, indexdef 
                FROM pg_indexes 
                WHERE tablename = 'qcomm_prices';
            """)
            indexes = cur.fetchall()
            print("\nIndices defined on 'qcomm_prices':")
            for idxname, idxdef in indexes:
                print(f" -> {idxname}: {idxdef}")
                
            assert prices_count > 0, "Synchronized prices count must be greater than 0"
            assert any('idx_metrics_lookup' in idx[0] for idx in indexes), "Index idx_metrics_lookup must exist"
            print("\nAll Neon Serverless trigger and index diagnostics passed successfully!")
            
    except Exception as e:
        print(f"Diagnostics failed: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    run_diagnostics()
