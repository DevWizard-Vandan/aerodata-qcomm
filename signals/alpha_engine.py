import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def calculate_staples_index(federated_df):
    """
    Computes a daily Staples Price Index from federated catalog data.
    Standardizes categories and calculates a weighted index value:
    - Dairy & Bread: Weight = 0.4
    - Fruits & Vegetables: Weight = 0.3
    - Groceries: Weight = 0.3
    
    Also calculates:
    - DoD Drift (\Delta CPI) = (Index_t - Index_t-1) / Index_t-1
    - 7-day rolling volatility (Standard Deviation of Drift)
    """
    if federated_df.empty:
        return pd.DataFrame(columns=["observed_date", "index_value", "drift_dod", "volatility_7d"])
        
    df = federated_df.copy()
    
    # 1. Standardize observed_at/timestamp to date
    if "observed_at" in df.columns:
        df["observed_date"] = pd.to_datetime(df["observed_at"]).dt.date
    elif "timestamp" in df.columns:
        df["observed_date"] = pd.to_datetime(df["timestamp"]).dt.date
    else:
        df["observed_date"] = pd.to_datetime(datetime.now()).date()
        
    # 2. Standardize categories for basket weighting matrix
    def map_sector(cat):
        if not cat:
            return "Other"
        cat_lower = str(cat).lower()
        if "dairy" in cat_lower or "milk" in cat_lower or "bread" in cat_lower or "egg" in cat_lower:
            return "Dairy & Bread"
        elif "fruit" in cat_lower or "veg" in cat_lower:
            return "Fruits & Vegetables"
        elif "grocery" in cat_lower or "staple" in cat_lower or "oil" in cat_lower or "grain" in cat_lower or "rice" in cat_lower:
            return "Groceries"
        return "Other"
        
    df["staple_sector"] = df["category"].apply(map_sector)
    
    # 3. Filter only in-stock baseline essentials
    essentials = df[(df["staple_sector"] != "Other") & (df["stock_status"] == True)]
    if essentials.empty:
        # Fallback if empty to ensure index math computes
        essentials = df.copy()
        essentials["staple_sector"] = "Groceries"
        
    # 4. Group daily average price per sector
    daily_sector = essentials.groupby(["observed_date", "staple_sector"]).agg(
        total_price=("discount_price", "sum"),
        total_count=("discount_price", "count")
    ).reset_index()
    
    daily_sector["avg_price"] = daily_sector["total_price"] / daily_sector["total_count"]
    
    # Pivot sectors to columns
    pivoted = daily_sector.pivot(index="observed_date", columns="staple_sector", values="avg_price").reset_index()
    
    # Enforce standard columns
    for sector in ["Dairy & Bread", "Fruits & Vegetables", "Groceries"]:
        if sector not in pivoted.columns:
            pivoted[sector] = np.nan
            
    # Forward-fill and backward-fill missing data to handle sparse dates
    pivoted = pivoted.ffill().bfill().fillna(0.0)
    
    # 5. Apply basket weights
    w_dairy = 0.4
    w_veg = 0.3
    w_groceries = 0.3
    pivoted["index_value"] = (
        pivoted["Dairy & Bread"] * w_dairy +
        pivoted["Fruits & Vegetables"] * w_veg +
        pivoted["Groceries"] * w_groceries
    )
    
    # Sort chronologically for rolling computations
    pivoted = pivoted.sort_values("observed_date")
    
    # 6. DoD Price Drift: (Index_t - Index_t-1) / Index_t-1
    pivoted["drift_dod"] = pivoted["index_value"].pct_change().fillna(0.0)
    
    # 7. Volatility bounds: 7-day rolling standard deviation
    pivoted["volatility_7d"] = pivoted["drift_dod"].rolling(window=7, min_periods=1).std().fillna(0.0)
    
    logger.info("Micro-Price Index Drift signal successfully computed.")
    return pivoted

if __name__ == "__main__":
    # Small validation compile check
    mock_df = pd.DataFrame({
        "timestamp": pd.date_range(end="2026-07-19", periods=5),
        "platform_name": ["Zepto"]*5,
        "store_id": ["store_blr"]*5,
        "product_id": ["p-1"]*5,
        "product_name": ["Milk"]*5,
        "category": ["Dairy & Bread"]*5,
        "listed_price": [50.0]*5,
        "discount_price": [48.0]*5,
        "stock_status": [True]*5,
        "parent_ticker": ["HINDUNILVR"]*5
    })
    result = calculate_staples_index(mock_df)
    assert not result.empty, "Compile verification failed: Staples index output is empty"
    print("alpha_engine.py compile check completed successfully.")
