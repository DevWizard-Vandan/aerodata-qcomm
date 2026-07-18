import os
import sys
import numpy as np
import logging

# Add project root to PYTHONPATH dynamically
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from database.init_db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class DataGuardrail:
    """
    DataGuardrail performs automated validations on incoming catalog items.
    Checks price floor/ceiling boundaries, missing/null types, and statistical anomalies.
    """
    def __init__(self):
        pass

    def validate(self, item, conn=None):
        """
        Validates product record dictionary parameters.
        Returns (is_valid: bool, reason: str)
        """
        # 1. Null handling & structural type verification
        mandatory_fields = ['product_name', 'store_id', 'discount_price', 'parent_ticker']
        for field in mandatory_fields:
            if field not in item or item[field] is None:
                return False, f"Null or missing mandatory field: {field}"

        # Clean string formats
        product_name = str(item.get("product_name", "")).strip()
        store_id = str(item.get("store_id", "")).strip()
        parent_ticker = str(item.get("parent_ticker", "")).strip()
        product_id = item.get("product_id")

        if not product_name:
            return False, "Empty product_name"
        if not store_id:
            return False, "Empty store_id"
        if not parent_ticker:
            return False, "Empty parent_ticker"
        if not product_id:
            return False, "Empty product_id"

        # Validate numeric format
        try:
            price = float(item["discount_price"])
            listed_price = float(item.get("listed_price", price))
        except (ValueError, TypeError):
            return False, "Price must be a valid float"

        # 2. Price Ceiling and Floor constraints
        if price <= 0.0:
            return False, f"Price floor violation: price {price} <= 0"
        if price > 5000.0:
            return False, f"Price ceiling violation: price {price} > 5000"

        # 3. Z-Score Outlier Detector (historical median deviation)
        close_conn = False
        if conn is None:
            try:
                conn = get_connection()
                close_conn = True
            except Exception:
                conn = None

        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT discount_price 
                        FROM qcomm_catalog_history 
                        WHERE product_id = %s;
                    """, (product_id,))
                    rows = cur.fetchall()
                    
                    if rows and len(rows) >= 3:
                        prices = [float(r[0]) for r in rows]
                        median = np.median(prices)
                        std = np.std(prices)
                        
                        # Only apply standard deviation Z-score if variance exists
                        if std > 0.05:
                            z_score = abs(price - median) / std
                            if z_score > 3.0:
                                return False, f"Z-Score outlier violation: Z-Score={z_score:.2f} > 3.0 (Price={price}, Median={median:.2f}, Std={std:.2f})"
            except Exception as e:
                # Do not block ingestion if database read fails, log warning
                logger.warning(f"Error querying SKU statistics for Z-score checking: {e}")
            finally:
                if close_conn:
                    conn.close()

        return True, "Passed"

if __name__ == "__main__":
    # Baseline self-test assertions
    guard = DataGuardrail()
    
    # Valid record
    valid_item = {
        "product_id": "z-milk-901",
        "product_name": "Amul Taaza Milk 1L",
        "store_id": "zepto_BLR_IND",
        "discount_price": 54.00,
        "listed_price": 56.00,
        "parent_ticker": "UNLISTED"
    }
    is_v, reason = guard.validate(valid_item)
    assert is_v, f"Failed valid record test: {reason}"
    
    # Boundary violations
    too_expensive = {**valid_item, "discount_price": 6000.00}
    is_v, reason = guard.validate(too_expensive)
    assert not is_v and "ceiling" in reason.lower(), f"Failed ceiling test: {reason}"

    free_item = {**valid_item, "discount_price": 0.00}
    is_v, reason = guard.validate(free_item)
    assert not is_v and "floor" in reason.lower(), f"Failed floor test: {reason}"
    
    # Missing fields
    missing_ticker = {**valid_item, "parent_ticker": None}
    is_v, reason = guard.validate(missing_ticker)
    assert not is_v and "mandatory" in reason.lower(), f"Failed mandatory null test: {reason}"

    print("All DataGuardrail self-tests passed successfully.")
