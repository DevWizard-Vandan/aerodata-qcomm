import os
import sys

# Add project root to PYTHONPATH dynamically
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import json
import logging
from scrapers.web_targets import SWIGGY_WEB_URL
from scrapers.network_manager import resolve_domain_with_fallback
from scrapers.exceptions import (
    STRICT_PROD_MODE,
    ScraperError,
    ScraperHTTPError,
    RateLimitError,
    ScraperParsingError,
    log_structured_error
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class SwiggyScraper:
    def __init__(self, api_url=SWIGGY_WEB_URL):
        self.api_url = api_url

    def fetch_page(self, lat: float, lng: float, network_manager=None, session_harvester=None, session_key=None):
        try:
            from scrapers.bootstrapper import fetch_live_catalog_payload
            payloads = fetch_live_catalog_payload("Swiggy Instamart", lat, lng)
            if not payloads:
                logger.warning("Swiggy Instamart direct response interception returned 0 payloads on attempt 1. Retrying...")
                payloads = fetch_live_catalog_payload("Swiggy Instamart", lat, lng)
            if payloads:
                logger.info(f"Swiggy Instamart Direct Response Interception retrieved {len(payloads)} payloads.")
                return payloads
        except Exception as boot_err:
            logger.warning(f"Swiggy Instamart Direct Response Interception warning: {boot_err}")
            if STRICT_PROD_MODE:
                log_structured_error("Swiggy Instamart", self.api_url, "INTERCEPTION_ERROR", f"Swiggy interception failed: {boot_err}", zone=session_key, exc=boot_err)

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.swiggy.com/instamart",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/124.0.0.0",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "lat": str(lat),
            "lng": str(lng)
        }

        params = {
            "lat": str(lat),
            "lng": str(lng)
        }

        resolved_ip = resolve_domain_with_fallback("www.swiggy.com")
        curl_opts = {}
        if resolved_ip:
            from curl_cffi import CurlOpt
            curl_opts[CurlOpt.RESOLVE] = [f"www.swiggy.com:443:{resolved_ip}"]

        from scrapers.proxy_manager import ProxyManager
        proxy_mgr = ProxyManager()
        proxies = proxy_mgr.get_proxy_dict(session_key=session_key)

        cookies = {}
        if session_harvester:
            cookies = session_harvester.harvest_session("Swiggy Instamart", network_manager, session_key=session_key)

        try:
            from scrapers.bootstrapper import get_live_session_context
            session_ctx = get_live_session_context("Swiggy Instamart", lat, lng)
            if session_ctx.get("cookies"):
                cookies.update(session_ctx["cookies"])
            if session_ctx.get("headers"):
                headers.update(session_ctx["headers"])
        except Exception as boot_err:
            logger.warning(f"Swiggy Instamart Playwright bootstrapper warning: {boot_err}")
            
        cookies["lat"] = str(lat)
        cookies["lng"] = str(lng)
        cookies["_instamart_lat"] = str(lat)
        cookies["_instamart_lng"] = str(lng)


        import time
        max_retries = 3
        last_exception = None

        for attempt in range(1, max_retries + 1):
            try:
                from curl_cffi import requests
                logger.info(f"Swiggy GET request attempt #{attempt} to {self.api_url} with params {params}")
                
                with requests.Session(curl_options=curl_opts) as s:
                    response = s.get(
                        self.api_url,
                        params=params,
                        headers=headers,
                        cookies=cookies,
                        impersonate="chrome124",
                        proxies=proxies,
                        timeout=15
                    )
                
                if network_manager:
                    network_manager.handle_request_status(response.status_code)

                logger.info(f"Swiggy response status code: {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception as parse_err:
                        if STRICT_PROD_MODE:
                            log_structured_error("Swiggy Instamart", self.api_url, "PARSING_ERROR", f"Invalid JSON response: {parse_err}", zone=session_key, exc=parse_err)
                            raise ScraperParsingError(f"Swiggy Instamart response is not valid JSON: {parse_err}", status_code="PARSING_ERROR", target_url=self.api_url, platform="Swiggy Instamart", zone=session_key) from parse_err
                        else:
                            return self._get_mock_response(lat, lng)

                    # Verify if it contains valid products or widgets layout structures
                    if isinstance(data, dict) and ("data" in data or "widgets" in data or "storeId" in data):
                        logger.info("Successfully fetched live response from Swiggy Instamart.")
                        return data
                    else:
                        err_msg = "Swiggy Instamart API returned empty/invalid layout structure"
                        log_structured_error("Swiggy Instamart", self.api_url, "PARSING_ERROR", err_msg, zone=session_key)
                        if STRICT_PROD_MODE:
                            raise ScraperParsingError(err_msg, status_code="PARSING_ERROR", target_url=self.api_url, platform="Swiggy Instamart", zone=session_key)
                        else:
                            logger.warning(f"{err_msg}. Activating mock fallback.")
                            return self._get_mock_response(lat, lng)
                else:
                    status_code = response.status_code
                    err_msg = f"Swiggy Instamart API returned status code {status_code}"
                    log_structured_error("Swiggy Instamart", self.api_url, status_code, err_msg, zone=session_key)

                    if attempt < max_retries and status_code in (403, 429, 500, 502, 503, 504):
                        backoff = 2 ** attempt
                        logger.warning(f"Swiggy request failed with status {status_code}. Retrying in {backoff}s...")
                        time.sleep(backoff)
                        continue

                    if STRICT_PROD_MODE:
                        if status_code == 429:
                            raise RateLimitError(err_msg, status_code=429, target_url=self.api_url, platform="Swiggy Instamart", zone=session_key)
                        else:
                            raise ScraperHTTPError(err_msg, status_code=status_code, target_url=self.api_url, platform="Swiggy Instamart", zone=session_key)
                    else:
                        logger.warning(f"Swiggy Instamart API returned status code {status_code}. Activating mock data fallback.")
                        return self._get_mock_response(lat, lng)
            except (ScraperError, RateLimitError, ScraperHTTPError, ScraperParsingError) as se:
                raise se
            except Exception as e:
                last_exception = e
                err_msg = f"Error fetching live Swiggy Instamart API ({e})"
                log_structured_error("Swiggy Instamart", self.api_url, 500, err_msg, zone=session_key, exc=e)
                if attempt < max_retries:
                    backoff = 2 ** attempt
                    logger.warning(f"Swiggy network exception ({e}). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue

                if STRICT_PROD_MODE:
                    raise ScraperHTTPError(err_msg, status_code=500, target_url=self.api_url, platform="Swiggy Instamart", zone=session_key) from e
                else:
                    logger.warning(f"Error fetching live Swiggy Instamart API ({e}). Activating mock data fallback.")
                    return self._get_mock_response(lat, lng)

    def parse_layout(self, response_json):
        """
        Recursively parses the Swiggy Instamart response to extract product listings.
        Converts prices from paise to rupees, and returns standard records.
        """
        if not isinstance(response_json, (dict, list)):
            if STRICT_PROD_MODE:
                log_structured_error("Swiggy Instamart", self.api_url, "PARSING_ERROR", "Swiggy layout response payload is not dict or list")
                raise ScraperParsingError("Swiggy layout response payload is not dict or list", status_code="PARSING_ERROR", target_url=self.api_url, platform="Swiggy Instamart")
            return []

        products = []
        try:
            seen_ids = set()
            if isinstance(response_json, list):
                for p in response_json:
                    sub_prods = self.parse_layout(p)
                    for sp in sub_prods:
                        if sp["product_id"] not in seen_ids:
                            seen_ids.add(sp["product_id"])
                            products.append(sp)
                return products

            store_id = "store_swiggy_indiranagar"
            if isinstance(response_json, dict):
                if "storeId" in response_json:
                    store_id = response_json["storeId"]
                elif "store_id" in response_json:
                    store_id = response_json["store_id"]
                elif "data" in response_json and isinstance(response_json["data"], dict):
                    store_id = response_json["data"].get("storeId") or response_json["data"].get("store_id") or store_id
                    
            store_info = {"storeId": store_id}

            # Inspect data.categories and data.cards envelopes if present
            if isinstance(response_json, dict) and isinstance(response_json.get("data"), dict):
                data_obj = response_json["data"]
                
                # Process 144-category taxonomy array
                categories_val = data_obj.get("categories")
                if isinstance(categories_val, list):
                    for cat in categories_val:
                        self._extract_products_recursive(cat, products, store_info, seen_ids=seen_ids)
                
                # Process cards array
                cards_val = data_obj.get("cards")
                if isinstance(cards_val, list):
                    for card in cards_val:
                        if isinstance(card, dict):
                            inner_card = card.get("card", {})
                            if isinstance(inner_card, dict):
                                card_card = inner_card.get("card", {})
                                grid_elements = inner_card.get("gridElements", {})
                                if card_card:
                                    self._extract_products_recursive(card_card, products, store_info, seen_ids=seen_ids)
                                if grid_elements:
                                    self._extract_products_recursive(grid_elements, products, store_info, seen_ids=seen_ids)
                            self._extract_products_recursive(card, products, store_info, seen_ids=seen_ids)

            # Fallback scan if data envelopes didn't extract any products
            if not products:
                self._extract_products_recursive(response_json, products, store_info, seen_ids=seen_ids)
            
            if not products and isinstance(response_json, (dict, list)):
                logger.info("Swiggy Instamart layout parsed 0 products. Printing diagnostic top 3 key levels:")
                self._log_payload_keys(response_json, level=1, max_level=3)
        except Exception as e:
            if STRICT_PROD_MODE:
                log_structured_error("Swiggy Instamart", self.api_url, "PARSING_ERROR", f"Layout parsing failed: {e}", exc=e)
                raise ScraperParsingError(f"Swiggy layout parsing failed: {e}", status_code="PARSING_ERROR", target_url=self.api_url, platform="Swiggy Instamart") from e
            else:
                logger.warning(f"Error parsing Swiggy layout: {e}")

        logger.info(f"Swiggy Instamart parsed {len(products)} products from layout response.")
        return products

    def _log_payload_keys(self, node, level=1, max_level=3, path="root"):
        if level > max_level:
            return
        if isinstance(node, dict):
            keys = list(node.keys())
            logger.info(f"Diagnostic Payload Keys [Level {level} - {path}]: {keys[:20]}")
            for k in keys[:5]:
                val = node[k]
                if isinstance(val, (dict, list)):
                    self._log_payload_keys(val, level + 1, max_level, f"{path}.{k}")
        elif isinstance(node, list) and node:
            logger.info(f"Diagnostic Payload List [Level {level} - {path}]: length {len(node)}")
            self._log_payload_keys(node[0], level + 1, max_level, f"{path}[0]")

    def _extract_number_from_price_obj(self, val):
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            try:
                return float(val)
            except (ValueError, TypeError):
                return None
        if isinstance(val, dict):
            if "units" in val and val["units"] is not None:
                try:
                    units = float(val["units"])
                    nanos = float(val.get("nanos", 0)) / 1e9 if val.get("nanos") else 0.0
                    return units + nanos
                except (ValueError, TypeError):
                    pass
            for inner_k in ["offerPrice", "value", "price", "mrp", "sellingPrice", "originalPrice"]:
                if inner_k in val and val[inner_k] is not None:
                    extracted = self._extract_number_from_price_obj(val[inner_k])
                    if extracted is not None:
                        return extracted
        return None

    def _extract_products_recursive(self, node, products_list, store_info, seen_ids=None):
        if seen_ids is None:
            seen_ids = set()

        if isinstance(node, dict):
            info_node = node.get("info") if isinstance(node.get("info"), dict) else node
            if "product" in node and isinstance(node["product"], dict):
                info_node = node["product"]

            prod = self._parse_product_node(info_node, store_info)
            if prod and prod["product_id"] not in seen_ids:
                seen_ids.add(prod["product_id"])
                products_list.append(prod)
                return

            target_keys = [
                'categories', 'subCategories', 'items', 'products', 'skus', 'widgets', 
                'gridElements', 'cards', 'card', 'cardList', 'infoWithStyle', 'itemCards', 'info'
            ]
            for k in target_keys:
                if k in node:
                    self._extract_products_recursive(node[k], products_list, store_info, seen_ids=seen_ids)

            for k, val in node.items():
                if k not in target_keys:
                    self._extract_products_recursive(val, products_list, store_info, seen_ids=seen_ids)
        elif isinstance(node, list):
            for item in node:
                self._extract_products_recursive(item, products_list, store_info, seen_ids=seen_ids)

    def _parse_product_node(self, node, store_info=None):
        if not isinstance(node, dict):
            return None
        try:
            variations = node.get("variations") if isinstance(node.get("variations"), list) and len(node["variations"]) > 0 else []
            v0 = variations[0] if variations and isinstance(variations[0], dict) else {}

            # ID Matching: Look for 'id', 'skuId', 'itemId', 'productId', or 'product_id'
            id_val = (
                node.get("id") or 
                node.get("skuId") or 
                node.get("itemId") or 
                node.get("productId") or 
                node.get("product_id") or
                v0.get("skuId") or
                v0.get("id") or
                v0.get("spinId") or
                v0.get("itemId") or
                v0.get("productId")
            )
            if not id_val:
                return None

            # Name Matching: Look for 'name', 'displayName', 'title', 'productName', or 'product_name'
            name_val = (
                node.get("name") or 
                node.get("displayName") or 
                node.get("title") or 
                node.get("productName") or 
                node.get("product_name") or
                v0.get("displayName") or
                v0.get("name") or
                v0.get("title")
            )
            if not name_val:
                return None

            # Price Extraction Logic
            raw_price = None

            # 1. Check flat keys: 'offerPrice', 'finalPrice', 'mrp', 'price', 'sellingPrice', 'originalPrice'
            flat_price_keys = ['offerPrice', 'finalPrice', 'mrp', 'price', 'sellingPrice', 'originalPrice']
            for k in flat_price_keys:
                if k in node and node[k] is not None:
                    num = self._extract_number_from_price_obj(node[k])
                    if num is not None:
                        raw_price = num
                        break

            # 2. Check nested 'variations': If 'variations' in node and is a non-empty list
            if raw_price is None and v0:
                for k in ['price', 'offerPrice', 'mrp', 'finalPrice', 'sellingPrice']:
                    if k in v0 and v0[k] is not None:
                        num = self._extract_number_from_price_obj(v0[k])
                        if num is not None:
                            raw_price = num
                            break

            # 3. Check nested 'price' dict: If 'price' in node and is a dict
            if raw_price is None and "price" in node:
                num = self._extract_number_from_price_obj(node["price"])
                if num is not None:
                    raw_price = num

            if raw_price is None:
                return None

            price_val = float(raw_price)

            # Automatically convert paise values to INR when > 100
            if price_val > 100:
                price_val = price_val / 100.0

            # Stock status calculation
            in_stock = node.get("inStock") or node.get("isAvailable") or v0.get("inStock") or (node.get("stock", 1) > 0)
            if "outOfStock" in node:
                in_stock = not node["outOfStock"]
            if "out_of_stock" in node:
                in_stock = not node["out_of_stock"]
            stock_val = bool(in_stock)

            if not store_info:
                store_info = {}
            store_id = store_info.get("storeId") or store_info.get("store_id") or "store_swiggy_indiranagar"
            brand_name = node.get("brand") or node.get("brandName") or node.get("brand_name") or v0.get("brandName") or v0.get("brand") or "Unknown"
            category = node.get("categoryName") or node.get("category_name") or node.get("category") or "General"

            # Construct canonical product dictionary with pipeline compatibility fields
            return {
                'product_id': str(id_val),
                'name': str(name_val),
                'price': float(price_val),
                'in_stock': bool(stock_val),
                'platform': 'Swiggy Instamart',
                # Extended fields for database ingestion & pipeline compatibility
                'product_name': str(name_val),
                'platform_name': 'Swiggy Instamart',
                'listed_price': float(price_val),
                'discount_price': float(price_val),
                'stock_status': bool(stock_val),
                'category': str(category),
                'brand_name': str(brand_name),
                'store_id': str(store_id),
                'parent_ticker': 'SWIGGY'
            }
        except Exception as e:
            logger.warning(f"Error parsing product node in Swiggy: {e}")
            return None

    def _get_mock_response(self, lat, lng):
        if STRICT_PROD_MODE:
            err_msg = "Mock data generation disabled in STRICT_PROD_MODE for SwiggyScraper."
            log_structured_error("Swiggy Instamart", self.api_url, "MOCK_DISABLED", err_msg)
            raise ScraperError(err_msg, status_code="MOCK_DISABLED", target_url=self.api_url, platform="Swiggy Instamart")

        logger.info(f"Injecting high-fidelity mock Swiggy Instamart layout response for ({lat}, {lng}).")
        
        # Deterministic price variance multiplier based on coordinate values (varying from 0% to 25%)
        multiplier = 1.0 + (abs(float(lat) * 7.0 + float(lng) * 3.0) % 25) / 100.0
        
        raw_response = {
            "storeId": f"store_swiggy_{int(lat * 100)}_{int(lng * 100)}",
            "data": {
                "widgets": [
                    {
                        "type": "GRID",
                        "items": [
                            {
                                "id": "s-milk-301",
                                "name": "Heritage Special Toned Milk 1L",
                                "brand": "Heritage",
                                "mrp": 4800,
                                "price": 4600,
                                "inStock": True,
                                "category": "Dairy, Bread & Eggs"
                            },
                            {
                                "id": "s-curd-302",
                                "name": "Nandini Premium Curd 500g",
                                "brand": "Nandini",
                                "mrp": 2500,
                                "price": 2500,
                                "inStock": True,
                                "category": "Dairy, Bread & Eggs"
                            },
                            {
                                "id": "s-cheese-303",
                                "name": "Britannia Cheese Slices 200g",
                                "brand": "Britannia",
                                "mrp": 15000,
                                "price": 14000,
                                "inStock": False,
                                "category": "Dairy, Bread & Eggs"
                            },
                            {
                                "id": "s-goodday-401",
                                "name": "Good Day Choco Chips Biscuits 100g",
                                "brand": "Good Day",
                                "mrp": 3000,
                                "price": 2800,
                                "inStock": True,
                                "category": "Dairy, Bread & Eggs"
                            }
                        ]
                    }
                ]
            }
        }
        
        # Apply pricing variation to mock layouts dynamically
        for widget in raw_response.get("data", {}).get("widgets", []):
            for prod in widget.get("items", []):
                if "price" in prod:
                    prod["price"] = int(prod["price"] * multiplier)
                if "mrp" in prod:
                    prod["mrp"] = int(prod["mrp"] * multiplier)
                    
        return raw_response
