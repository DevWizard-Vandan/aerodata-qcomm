import os
import sys
import logging
import pandas as pd
import psycopg2
from huggingface_hub import HfApi

# Add project root to PYTHONPATH dynamically
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database.init_db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def offload_historical_records():
    # 1. Parse connection routing and secrets parameters
    db_url = os.environ.get("DATABASE_URL")
    hf_token = os.environ.get("HF_TOKEN")
    hf_repo_id = os.environ.get("HF_REPO_ID")

    logger.info("Initializing Hot/Cold Serverless Data Archival Process...")

    if not hf_token or not hf_repo_id:
        logger.warning("HF_TOKEN or HF_REPO_ID not configured in environment. Skipping offload.")
        return True

    conn = None
    try:
        conn = get_connection()
        # Set autocommit to False to manage manual transaction transactions
        conn.autocommit = False
        
        with conn.cursor() as cur:
            # 2. Select partition candidates older than 30 days
            logger.info("Checking for records older than 30 days inside qcomm_prices...")
            query = "SELECT * FROM qcomm_prices WHERE timestamp < NOW() - INTERVAL '30 days';"
            
            # Use Pandas to read SQL query directly
            df = pd.read_sql_query(query, conn)
            
            if df.empty:
                logger.info("Zero partition records found matching archival parameters (< 30 days). Clean skip.")
                conn.commit()
                return True
                
            logger.info(f"Detected {len(df)} records for cold storage archival. Starting serialization...")

            # 3. Create local target directory and serialize to gzip Parquet
            os.makedirs("data", exist_ok=True)
            local_parquet_path = "data/archive_cold_tier.parquet"
            
            # Serialize using pyarrow engine with gzip compression
            df.to_parquet(
                local_parquet_path,
                engine="pyarrow",
                compression="gzip",
                index=False
            )
            logger.info(f"Parquet compression serialization written to: {local_parquet_path}")

            # 4. Upload file to Hugging Face
            logger.info(f"Transmitting parquet archive to Hugging Face Repository: {hf_repo_id}...")
            api = HfApi()
            
            # Determine repo type based on namespace or default to dataset
            repo_type = "dataset"
            if hf_repo_id.startswith("spaces/"):
                repo_type = "space"
                hf_repo_id = hf_repo_id.replace("spaces/", "")
            elif hf_repo_id.startswith("models/"):
                repo_type = "model"
                hf_repo_id = hf_repo_id.replace("models/", "")

            api.upload_file(
                path_or_fileobj=local_parquet_path,
                path_in_repo="archive_cold_tier.parquet",
                repo_id=hf_repo_id,
                token=hf_token,
                repo_type=repo_type
            )
            logger.info("Parquet transmission to Hugging Face successfully completed.")

            # 5. Safe Database Purge (Strict transaction execution)
            logger.info("Executing safe database deletion of offloaded rows...")
            delete_query = "DELETE FROM qcomm_prices WHERE timestamp < NOW() - INTERVAL '30 days';"
            cur.execute(delete_query)
            
            # Commit only when transmission succeeds without error exceptions
            conn.commit()
            logger.info("Database transaction committed. Reclaimed serverless storage slots.")
            
            # Clean up local archive file to free workspace space
            if os.path.exists(local_parquet_path):
                os.remove(local_parquet_path)
                
            return True
            
    except Exception as e:
        logger.error(f"Archival transaction failed: {e}. Executing rollback...")
        if conn:
            try:
                conn.rollback()
            except Exception as rb_err:
                logger.error(f"Rollback execution failed: {rb_err}")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    success = offload_historical_records()
    if not success:
        sys.exit(1)
