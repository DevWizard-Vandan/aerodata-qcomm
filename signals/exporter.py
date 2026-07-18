import os
import logging
from datetime import datetime
import pandas as pd

from signals.aggregator import (
    fetch_raw_records,
    calculate_brand_stockouts,
    calculate_inflation_index
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_S3_DIR = "s3_delivery_simulation"

def export_signals():
    """
    Orchestrates the signal generation and exports them to S3 simulated Parquet files.
    """
    logger.info("Initializing Signal Exporter Engine...")
    
    # 1. Fetch data
    df = fetch_raw_records()
    if df.empty:
        logger.warning("No records found in database to export. Exiting export.")
        return False
        
    # 2. Calculate indices
    stockouts_df = calculate_brand_stockouts(df)
    inflation_df = calculate_inflation_index(df)
    
    # We will export files grouped by date to simulate clean S3 point-in-time delivery
    all_dates = set()
    if not stockouts_df.empty:
        all_dates.update(stockouts_df["observed_date"].tolist())
    if not inflation_df.empty:
        all_dates.update(inflation_df["observed_date"].tolist())
        
    if not all_dates:
        logger.warning("No date entries found in signals. Exiting export.")
        return False
        
    logger.info(f"Generating Parquet partitions for {len(all_dates)} distinct dates...")
    
    for dt in all_dates:
        dt_str = str(dt)
        try:
            date_obj = datetime.strptime(dt_str, "%Y-%m-%d")
        except ValueError:
            date_obj = dt
            
        year_str = f"{date_obj.year:04d}"
        month_str = f"{date_obj.month:02d}"
        day_str = f"{date_obj.day:02d}"
        
        # Build path: s3_delivery_simulation/year=2026/month=07/day=16/
        partition_dir = os.path.join(BASE_S3_DIR, f"year={year_str}", f"month={month_str}", f"day={day_str}")
        os.makedirs(partition_dir, exist_ok=True)
        
        # Filter and save stockouts
        if not stockouts_df.empty:
            daily_stockouts = stockouts_df[stockouts_df["observed_date"] == dt]
            if not daily_stockouts.empty:
                daily_stockouts = daily_stockouts.copy()
                daily_stockouts["observed_date"] = daily_stockouts["observed_date"].astype(str)
                
                out_file = os.path.join(partition_dir, "brand_stockouts.parquet")
                daily_stockouts.to_parquet(out_file, index=False, engine="pyarrow")
                logger.info(f"Exported Brand Stockouts to {out_file}")
                
        # Filter and save inflation
        if not inflation_df.empty:
            daily_inflation = inflation_df[inflation_df["observed_date"] == dt]
            if not daily_inflation.empty:
                daily_inflation = daily_inflation.copy()
                daily_inflation["observed_date"] = daily_inflation["observed_date"].astype(str)
                
                out_file = os.path.join(partition_dir, "food_inflation_index.parquet")
                daily_inflation.to_parquet(out_file, index=False, engine="pyarrow")
                logger.info(f"Exported CPI Inflation to {out_file}")
                
    logger.info("Signal Exporter execution completed successfully.")
    return True

if __name__ == "__main__":
    export_signals()
