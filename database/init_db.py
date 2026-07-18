import psycopg2
import sys
import logging
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def get_connection():
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
        logger.info(f"Connecting to database {DB_NAME} at {DB_HOST}:{DB_PORT}...")
        conn = get_connection()
        conn.autocommit = True
        with conn.cursor() as cur:
            # 1. Create table
            logger.info("Creating table qcomm_catalog_history...")
            create_table_query = """
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
                PRIMARY KEY (observed_at, platform_name, store_id, product_id)
            );
            """
            cur.execute(create_table_query)

            # 2. Check if already a hypertable
            cur.execute("""
                SELECT 1 FROM _timescaledb_catalog.hypertable 
                WHERE table_name = 'qcomm_catalog_history';
            """)
            is_hypertable = cur.fetchone()

            if not is_hypertable:
                logger.info("Converting qcomm_catalog_history to hypertable...")
                cur.execute("""
                    SELECT create_hypertable(
                        'qcomm_catalog_history', 
                        'observed_at', 
                        chunk_time_interval => INTERVAL '7 days'
                    );
                """)
                logger.info("Hypertable created successfully.")
            else:
                logger.info("qcomm_catalog_history is already a hypertable.")

            # 3. Enable compression
            logger.info("Enabling columnar compression on hypertable...")
            try:
                cur.execute("""
                    ALTER TABLE qcomm_catalog_history SET (
                        timescaledb.compress,
                        timescaledb.compress_segmentby = 'platform_name, product_id, store_id'
                    );
                """)
                logger.info("Compression settings enabled.")
            except psycopg2.Error as e:
                # If compression is already enabled, it might raise an exception or notice, handle it
                logger.info(f"Note on enabling compression: {e}")

            # 4. Add compression policy
            logger.info("Adding compression policy for chunks older than 14 days...")
            try:
                cur.execute("""
                    SELECT add_compression_policy(
                        'qcomm_catalog_history', 
                        INTERVAL '14 days',
                        if_not_exists => true
                    );
                """)
                logger.info("Compression policy set up successfully.")
            except psycopg2.Error as e:
                logger.info(f"Note on compression policy: {e}")

        logger.info("Database infrastructure initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    initialize_database()
