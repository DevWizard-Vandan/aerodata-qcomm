import psycopg2
import sys
import os
import logging

# Add project root to PYTHONPATH dynamically
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def get_connection():
    """
    Establishes connection to the target PostgreSQL database.
    Supports serverless environments via DATABASE_URL or defaults to config parameters.
    """
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        return psycopg2.connect(db_url)
    
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME
    )

def initialize_database():
    conn = None
    try:
        db_url = os.environ.get("DATABASE_URL")
        if db_url:
            logger.info("Connecting to database using DATABASE_URL link...")
        else:
            logger.info(f"Connecting to database {DB_NAME} at {DB_HOST}:{DB_PORT}...")
            
        conn = get_connection()
        conn.autocommit = True
        with conn.cursor() as cur:
            # 1. Create main qcomm_catalog_history table
            logger.info("Creating table qcomm_catalog_history...")
            create_history_query = """
            CREATE TABLE IF NOT EXISTS qcomm_catalog_history (
                observed_at TIMESTAMPTZ NOT NULL,
                effective_at TIMESTAMPTZ NOT NULL,
                platform_name VARCHAR(100) NOT NULL,
                store_id VARCHAR(100) NOT NULL,
                product_id VARCHAR(100) NOT NULL,
                product_name TEXT NOT NULL,
                category TEXT,
                brand_name TEXT,
                listed_price NUMERIC(10, 2),
                discount_price NUMERIC(10, 2),
                stock_status BOOLEAN NOT NULL,
                parent_ticker VARCHAR(50),
                timestamp TIMESTAMPTZ,
                price_index_value NUMERIC(10, 2),
                daily_drift_velocity NUMERIC(10, 4),
                PRIMARY KEY (observed_at, platform_name, store_id, product_id)
            );
            """
            cur.execute(create_history_query)

            # Ensure columns exist in case table is already created
            cur.execute("ALTER TABLE qcomm_catalog_history ADD COLUMN IF NOT EXISTS timestamp TIMESTAMPTZ;")
            cur.execute("ALTER TABLE qcomm_catalog_history ADD COLUMN IF NOT EXISTS price_index_value NUMERIC(10, 2);")
            cur.execute("ALTER TABLE qcomm_catalog_history ADD COLUMN IF NOT EXISTS daily_drift_velocity NUMERIC(10, 4);")

            # Create a trigger to automatically populate timestamp from observed_at if null
            create_ts_trigger_function = """
            CREATE OR REPLACE FUNCTION populate_timestamp()
            RETURNS TRIGGER AS $$
            BEGIN
                IF NEW.timestamp IS NULL THEN
                    NEW.timestamp := NEW.observed_at;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
            cur.execute(create_ts_trigger_function)
            
            cur.execute("DROP TRIGGER IF EXISTS trg_populate_timestamp ON qcomm_catalog_history;")
            cur.execute("""
                CREATE TRIGGER trg_populate_timestamp
                BEFORE INSERT OR UPDATE ON qcomm_catalog_history
                FOR EACH ROW
                EXECUTE FUNCTION populate_timestamp();
            """)

            # Update existing records
            cur.execute("UPDATE qcomm_catalog_history SET timestamp = observed_at WHERE timestamp IS NULL;")

            # 2. Create qcomm_prices table for Neon high-speed indexed lookups
            logger.info("Creating table qcomm_prices...")
            create_prices_query = """
            CREATE TABLE IF NOT EXISTS qcomm_prices (
                timestamp TIMESTAMPTZ NOT NULL,
                store_id VARCHAR(100) NOT NULL,
                parent_ticker VARCHAR(50),
                platform_name VARCHAR(100) NOT NULL,
                product_id VARCHAR(100) NOT NULL,
                product_name TEXT NOT NULL,
                listed_price NUMERIC(10, 2),
                discount_price NUMERIC(10, 2),
                category TEXT,
                brand_name TEXT,
                stock_status BOOLEAN NOT NULL DEFAULT TRUE,
                PRIMARY KEY (timestamp, platform_name, store_id, product_id)
            );
            """
            cur.execute(create_prices_query)

            # 3. Create the compound lookup index on qcomm_prices
            logger.info("Creating index idx_metrics_lookup...")
            create_index_query = """
            CREATE INDEX IF NOT EXISTS idx_metrics_lookup 
            ON qcomm_prices (timestamp DESC, store_id, parent_ticker);
            """
            cur.execute(create_index_query)

            # 4. Build database synchronization trigger functions
            logger.info("Creating synchronization trigger function and trigger...")
            create_function_query = """
            CREATE OR REPLACE FUNCTION sync_to_qcomm_prices()
            RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO qcomm_prices (
                    timestamp, store_id, parent_ticker, platform_name, 
                    product_id, product_name, listed_price, discount_price,
                    category, brand_name, stock_status
                )
                VALUES (
                    NEW.observed_at, NEW.store_id, NEW.parent_ticker, NEW.platform_name, 
                    NEW.product_id, NEW.product_name, NEW.listed_price, NEW.discount_price,
                    NEW.category, NEW.brand_name, NEW.stock_status
                )
                ON CONFLICT (timestamp, platform_name, store_id, product_id)
                DO UPDATE SET
                    parent_ticker = EXCLUDED.parent_ticker,
                    product_name = EXCLUDED.product_name,
                    listed_price = EXCLUDED.listed_price,
                    discount_price = EXCLUDED.discount_price,
                    category = EXCLUDED.category,
                    brand_name = EXCLUDED.brand_name,
                    stock_status = EXCLUDED.stock_status;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
            cur.execute(create_function_query)

            # Drop trigger if exists and create it fresh to ensure idempotency
            cur.execute("DROP TRIGGER IF EXISTS trg_sync_prices ON qcomm_catalog_history;")
            create_trigger_query = """
            CREATE TRIGGER trg_sync_prices
            AFTER INSERT OR UPDATE ON qcomm_catalog_history
            FOR EACH ROW
            EXECUTE FUNCTION sync_to_qcomm_prices();
            """
            cur.execute(create_trigger_query)

            # 5. Back-populate existing catalog history into qcomm_prices table
            logger.info("Back-populating historical records from qcomm_catalog_history into qcomm_prices...")
            backpopulate_query = """
            INSERT INTO qcomm_prices (
                timestamp, store_id, parent_ticker, platform_name, 
                product_id, product_name, listed_price, discount_price,
                category, brand_name, stock_status
            )
            SELECT 
                observed_at, store_id, parent_ticker, platform_name, 
                product_id, product_name, listed_price, discount_price,
                category, brand_name, stock_status
            FROM qcomm_catalog_history
            ON CONFLICT (timestamp, platform_name, store_id, product_id) DO NOTHING;
            """
            cur.execute(backpopulate_query)

        logger.info("Database infrastructure initialized successfully for Neon.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    initialize_database()
