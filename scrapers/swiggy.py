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

        # Proxy support
        from scrapers.proxy_manager import ProxyManager
        proxy_mgr = ProxyManager()
        proxies = proxy_mgr.get_proxy_dict(session_key=session_key)

        # Dynamic Cookie & Session Harvesting via Playwright Bootstrapper
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
            if STRICT_PROD_MODE:
                log_structured_error("Swiggy Instamart", self.api_url, "BOOTSTRAP_ERROR", f"Swiggy bootstrapper failed: {boot_err}", zone=session_key, exc=boot_err)
                raise ScraperError(f"Swiggy bootstrapper failed: {boot_err}", status_code="BOOTSTRAP_ERROR", target_url=self.api_url, platform="Swiggy Instamart", zone=session_key) from boot_err
            
        # Merge target coordinate cookies
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
            store_id = "store_swiggy_indiranagar"
            if isinstance(response_json, dict):
                if "storeId" in response_json:
                    store_id = response_json["storeId"]
                elif "store_id" in response_json:
                    store_id = response_json["store_id"]
                elif "data" in response_json and isinstance(response_json["data"], dict):
                    store_id = response_json["data"].get("storeId") or response_json["data"].get("store_id") or store_id
                    
            store_info = {"storeId": store_id}
            
            self._extract_products_recursive(response_json, products, store_info)
        except Exception as e:
            if STRICT_PROD_MODE:
                log_structured_error("Swiggy Instamart", self.api_url, "PARSING_ERROR", f"Layout parsing failed: {e}", exc=e)
                raise ScraperParsingError(f"Swiggy layout parsing failed: {e}", status_code="PARSING_ERROR", target_url=self.api_url, platform="Swiggy Instamart") from e
            else:
                logger.warning(f"Error parsing Swiggy layout: {e}")

        logger.info(f"Swiggy Instamart parsed {len(products)} products from layout response.")
        return products

    def _extract_products_recursive(self, node, products_list, store_info):
        if isinstance(node, dict):
            has_id = "id" in node or "productId" in node or "product_id" in node
            has_price = "price" in node or "mrp" in node or "sellingPrice" in node
            
            if "product" in node and isinstance(node["product"], dict):
                prod = self._parse_product_node(node["product"], store_info)
                if prod:
                    products_list.append(prod)
            elif has_id and has_price and "name" in node:
                prod = self._parse_product_node(node, store_info)
                if prod:
                    products_list.append(prod)
            else:
                for val in node.values():
                    self._extract_products_recursive(val, products_list, store_info)
        elif isinstance(node, list):
            for item in node:
                self._extract_products_recursive(item, products_list, store_info)

    def _parse_product_node(self, node, store_info):
        try:
            product_id = node.get("id") or node.get("productId") or node.get("product_id")
            product_name = node.get("name") or node.get("productName") or node.get("product_name") or node.get("title")
            if not product_id or not product_name:
                return None
            
            brand_name = node.get("brand") or node.get("brandName") or node.get("brand_name") or "Unknown"
            category = node.get("categoryName") or node.get("category_name") or node.get("category") or "General"
            
            mrp_paise = node.get("mrp") or node.get("originalPrice") or node.get("original_price") or node.get("price") or 0
            selling_price_paise = node.get("sellingPrice") or node.get("selling_price") or node.get("discountPrice") or node.get("discount_price") or mrp_paise
            
            try:
                mrp = float(mrp_paise) / 100.0 if float(mrp_paise) > 100 else float(mrp_paise)
            except (ValueError, TypeError):
                mrp = 0.0
                
            try:
                discount_price = float(selling_price_paise) / 100.0 if float(selling_price_paise) > 100 else float(selling_price_paise)
            except (ValueError, TypeError):
                discount_price = mrp
                
            out_of_stock = node.get("outOfStock") or node.get("out_of_stock") or (node.get("stock", 1) == 0) or (node.get("status") == "OUT_OF_STOCK")
            stock_status = not out_of_stock
            
            store_id = store_info.get("storeId") or store_info.get("store_id") or "store_blr_indiranagar"
            
            return {
                "platform_name": "Swiggy Instamart",
                "store_id": str(store_id),
                "product_id": str(product_id),
                "product_name": str(product_name),
                "category": str(category),
                "brand_name": str(brand_name),
                "listed_price": mrp,
                "discount_price": discount_price,
                "stock_status": bool(stock_status),
                "parent_ticker": "SWIGGY"
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
