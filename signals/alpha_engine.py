import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def get_zone_from_store(store_id):
    if not store_id:
        return "Other"
    store_lower = str(store_id).lower()
    
    # Check specific neighborhoods first
    if "ind" in store_lower:
        return "Indiranagar"
    elif "hsr" in store_lower:
        return "HSR Layout"
    elif "lpr" in store_lower or "parel" in store_lower:
        return "Lower Parel"
    elif "and" in store_lower:
        return "Andheri West"
    elif "gur" in store_lower:
        return "Gurugram Phase 3"
    elif "sak" in store_lower:
        return "Saket"
        
    # Check city-level fallbacks
    if "blr" in store_lower or "bangalore" in store_lower:
        return "Bangalore"
    elif "bom" in store_lower or "mumbai" in store_lower:
        return "Mumbai"
    elif "del" in store_lower or "delhi" in store_lower:
        return "Delhi-NCR"
        
    return "Other"

def calculate_stockout_metrics(federated_df):
    """
    Groups data by daily intervals and localized cluster zone/urban region,
    calculates the active Stockout Rate (SR_t), the Day-over-Day Stockout
    Velocity Vector (SVV = SR_t - SR_t-1), and a 3-day rolling EMA of SVV.
    """
    if federated_df.empty:
        return pd.DataFrame(columns=["observed_date", "zone", "total_products", "oos_products", "sr", "svv", "svv_ema"])
        
    df = federated_df.copy()
    
    # 1. Standardize observed_at/timestamp to date
    if "observed_at" in df.columns:
        df["observed_date"] = pd.to_datetime(df["observed_at"]).dt.date
    elif "timestamp" in df.columns:
        df["observed_date"] = pd.to_datetime(df["timestamp"]).dt.date
    else:
        df["observed_date"] = pd.to_datetime(datetime.now()).date()
        
    # 2. Extract zone/urban region
    df["zone"] = df["store_id"].apply(get_zone_from_store)
    
    # 3. Group by observed_date and zone to calculate stockout rate
    grouped = df.groupby(["observed_date", "zone"]).agg(
        total_products=("stock_status", "count"),
        in_stock_products=("stock_status", lambda x: (x == True).sum())
    ).reset_index()
    
    grouped["oos_products"] = grouped["total_products"] - grouped["in_stock_products"]
    grouped["sr"] = (grouped["oos_products"] / grouped["total_products"]) * 100.0
    
    # Sort chronologically for diff
    grouped = grouped.sort_values(["zone", "observed_date"])
    
    # 4. DoD Stockout Velocity Vector (SVV = SR_t - SR_{t-1}) per zone
    grouped["svv"] = grouped.groupby("zone")["sr"].diff().fillna(0.0)
    
    # 5. Apply a 3-day rolling Exponential Moving Average (EMA) layer over the velocity vector
    emas = []
    for zone, zone_df in grouped.groupby("zone"):
        ema_series = zone_df["svv"].ewm(span=3, adjust=False).mean()
        emas.append(ema_series)
        
    if emas:
        grouped["svv_ema"] = pd.concat(emas).sort_index()
    else:
        grouped["svv_ema"] = 0.0
        
    return grouped

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
        "timestamp": pd.date_range(end="2026-07-21", periods=10).repeat(3),
        "platform_name": ["Zepto"]*30,
        "store_id": ["zepto_BLR_IND", "blinkit_BOM_LPR", "zepto_BLR_HSR"]*10,
        "product_id": ["p-1", "p-2", "p-3"]*10,
        "product_name": ["Milk", "Apple", "Bread"]*10,
        "category": ["Dairy & Bread", "Fruits & Vegetables", "Groceries"]*10,
        "listed_price": [50.0]*30,
        "discount_price": [48.0]*30,
        "stock_status": [True, False, True]*10,
        "parent_ticker": ["HINDUNILVR"]*30
    })
    result_idx = calculate_staples_index(mock_df)
    assert not result_idx.empty, "Compile verification failed: Staples index output is empty"
    result_so = calculate_stockout_metrics(mock_df)
    assert not result_so.empty, "Compile verification failed: Stockout metrics output is empty"
    print("alpha_engine.py compile check completed successfully.")
