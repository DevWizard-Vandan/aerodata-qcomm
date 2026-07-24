import os
import sys

# Add project root to PYTHONPATH dynamically
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import json
import logging
from scrapers.web_targets import BLINKIT_WEB_URL
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

class BlinkitScraper:
    def __init__(self, api_url=BLINKIT_WEB_URL):
        self.api_url = api_url

    def fetch_page(self, lat: float, lng: float, network_manager=None, session_harvester=None, session_key=None):
        payload = {
            "latitude": lat,
            "longitude": lng,
            "page_context": "home"
        }
        
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://blinkit.com",
            "Referer": "https://blinkit.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "lat": str(lat),
            "lon": str(lng),
            "app_client_id": "consumer_web"
        }

        # Resolve IP via network manager DNS fallback mapping to web domain
        resolved_ip = resolve_domain_with_fallback("blinkit.com")
        curl_opts = {}
        if resolved_ip:
            from curl_cffi import CurlOpt
            curl_opts[CurlOpt.RESOLVE] = [f"blinkit.com:443:{resolved_ip}"]

        # Proxy support
        from scrapers.proxy_manager import ProxyManager
        proxy_mgr = ProxyManager()
        proxies = proxy_mgr.get_proxy_dict(session_key=session_key)

        # Dynamic Cookie Harvesting
        cookies = {}
        if session_harvester:
            cookies = session_harvester.harvest_session("Blinkit", network_manager, session_key=session_key)

        import time
        max_retries = 3
        last_exception = None

        for attempt in range(1, max_retries + 1):
            try:
                from curl_cffi import requests
                logger.info(f"Blinkit POST request attempt #{attempt} to {self.api_url} (lat={lat}, lng={lng})")
                
                with requests.Session(curl_options=curl_opts) as s:
                    response = s.post(
                        self.api_url,
                        json=payload,
                        headers=headers,
                        cookies=cookies,
                        impersonate="chrome124",
                        proxies=proxies,
                        timeout=15
                    )
                
                if network_manager:
                    network_manager.handle_request_status(response.status_code)

                logger.info(f"Blinkit response status code: {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception as parse_err:
                        if STRICT_PROD_MODE:
                            log_structured_error("Blinkit", self.api_url, "PARSING_ERROR", f"Invalid JSON response: {parse_err}", zone=session_key, exc=parse_err)
                            raise ScraperParsingError(f"Blinkit response is not valid JSON: {parse_err}", status_code="PARSING_ERROR", target_url=self.api_url, platform="Blinkit", zone=session_key) from parse_err
                        else:
                            return self._get_mock_response(lat, lng)

                    # Verify if it contains valid products or tab structures
                    if isinstance(data, dict) and ("tabs" in data or "sections" in data or "merchant_id" in data):
                        logger.info("Successfully fetched live response from Blinkit API.")
                        return data
                    else:
                        err_msg = "Blinkit API returned empty/invalid layout structure"
                        log_structured_error("Blinkit", self.api_url, "PARSING_ERROR", err_msg, zone=session_key)
                        if STRICT_PROD_MODE:
                            raise ScraperParsingError(err_msg, status_code="PARSING_ERROR", target_url=self.api_url, platform="Blinkit", zone=session_key)
                        else:
                            logger.warning(f"{err_msg}. Activating mock fallback.")
                            return self._get_mock_response(lat, lng)
                else:
                    status_code = response.status_code
                    err_msg = f"Blinkit API returned status code {status_code}"
                    log_structured_error("Blinkit", self.api_url, status_code, err_msg, zone=session_key)

                    if attempt < max_retries and status_code in (403, 429, 500, 502, 503, 504):
                        backoff = 2 ** attempt
                        logger.warning(f"Blinkit request failed with status {status_code}. Retrying in {backoff}s...")
                        time.sleep(backoff)
                        continue

                    if STRICT_PROD_MODE:
                        if status_code == 429:
                            raise RateLimitError(err_msg, status_code=429, target_url=self.api_url, platform="Blinkit", zone=session_key)
                        else:
                            raise ScraperHTTPError(err_msg, status_code=status_code, target_url=self.api_url, platform="Blinkit", zone=session_key)
                    else:
                        logger.warning(f"Blinkit API returned status code {status_code}. Activating mock fallback.")
                        return self._get_mock_response(lat, lng)
            except (ScraperError, RateLimitError, ScraperHTTPError, ScraperParsingError) as se:
                raise se
            except Exception as e:
                last_exception = e
                err_msg = f"Error fetching live Blinkit API ({e})"
                log_structured_error("Blinkit", self.api_url, 500, err_msg, zone=session_key, exc=e)
                if attempt < max_retries:
                    backoff = 2 ** attempt
                    logger.warning(f"Blinkit network exception ({e}). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue

                if STRICT_PROD_MODE:
                    raise ScraperHTTPError(err_msg, status_code=500, target_url=self.api_url, platform="Blinkit", zone=session_key) from e
                else:
                    logger.warning(f"Error fetching live Blinkit API ({e}). Activating mock fallback.")
                    return self._get_mock_response(lat, lng)

    def parse_layout(self, response_json):
        """
        Traverses the layout recursively to parse products and store mappings.
        Converts prices from paise to rupees, and returns formatted catalog data.
        """
        if not isinstance(response_json, (dict, list)):
            if STRICT_PROD_MODE:
                log_structured_error("Blinkit", self.api_url, "PARSING_ERROR", "Blinkit layout response payload is not dict or list")
                raise ScraperParsingError("Blinkit layout response payload is not dict or list", status_code="PARSING_ERROR", target_url=self.api_url, platform="Blinkit")
            return []

        products = []
        try:
            store_id = "store_blinkit_indiranagar"
            if isinstance(response_json, dict):
                if "merchant_id" in response_json:
                    store_id = response_json["merchant_id"]
                elif "store_id" in response_json:
                    store_id = response_json["store_id"]
                elif "merchant" in response_json and isinstance(response_json["merchant"], dict):
                    store_id = response_json["merchant"].get("id") or store_id
                    
            store_info = {"storeId": store_id}
            
            self._extract_products_recursive(response_json, products, store_info)
        except Exception as e:
            if STRICT_PROD_MODE:
                log_structured_error("Blinkit", self.api_url, "PARSING_ERROR", f"Layout parsing failed: {e}", exc=e)
                raise ScraperParsingError(f"Blinkit layout parsing failed: {e}", status_code="PARSING_ERROR", target_url=self.api_url, platform="Blinkit") from e
            else:
                logger.warning(f"Error parsing Blinkit layout: {e}")

        logger.info(f"Blinkit parsed {len(products)} products from the layout response.")
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
                "platform_name": "Blinkit",
                "store_id": str(store_id),
                "product_id": str(product_id),
                "product_name": str(product_name),
                "category": str(category),
                "brand_name": str(brand_name),
                "listed_price": mrp,
                "discount_price": discount_price,
                "stock_status": bool(stock_status),
                "parent_ticker": "BLINKIT"
            }
        except Exception as e:
            logger.warning(f"Error parsing product node in Blinkit: {e}")
            return None

    def _get_mock_response(self, lat, lng):
        if STRICT_PROD_MODE:
            err_msg = "Mock data generation disabled in STRICT_PROD_MODE for BlinkitScraper."
            log_structured_error("Blinkit", self.api_url, "MOCK_DISABLED", err_msg)
            raise ScraperError(err_msg, status_code="MOCK_DISABLED", target_url=self.api_url, platform="Blinkit")

        logger.info(f"Injecting high-fidelity mock Blinkit layout response for ({lat}, {lng}).")
        
        # Deterministic price variance multiplier based on coordinate values (varying from 0% to 25%)
        multiplier = 1.0 + (abs(float(lat) * 7.0 + float(lng) * 3.0) % 25) / 100.0
        
        raw_response = {
            "merchant_id": f"store_blinkit_{int(lat * 100)}_{int(lng * 100)}",
            "tabs": [
                {
                    "id": "tab-1",
                    "title": "Home Feed",
                    "sections": [
                        {
                          "id": "section-1",
                          "layout_items": [
                            {
                              "products": [
                                {
                                  "id": "b-milk-201",
                                  "name": "Nandini Toned Fresh Milk 1L",
                                  "brand": "Nandini",
                                  "price": 4600,
                                  "mrp": 4600,
                                  "out_of_stock": False,
                                  "category": "Dairy, Bread & Eggs"
                                },
                                {
                                  "id": "b-paneer-302",
                                  "name": "Amul Fresh Paneer 200g",
                                  "brand": "Amul",
                                  "price": 9000,
                                  "mrp": 9200,
                                  "out_of_stock": False,
                                  "category": "Dairy, Bread & Eggs"
                                },
                                {
                                  "id": "b-egg-404",
                                  "name": "Eggs Table White 30pcs",
                                  "brand": "Egg Brand",
                                  "price": 18000,
                                  "mrp": 21000,
                                  "out_of_stock": True,
                                  "category": "Dairy, Bread & Eggs"
                                },
                                {
                                  "id": "b-parachute-501",
                                  "name": "Parachute Coconut Hair Oil 250ml",
                                  "brand": "Parachute",
                                  "price": 13500,
                                  "mrp": 13500,
                                  "out_of_stock": False,
                                  "category": "Groceries"
                                }
                              ]
                            }
                          ]
                        }
                    ]
                }
            ]
        }
        
        # Apply pricing variation to mock layouts dynamically
        for tab in raw_response.get("tabs", []):
            for sec in tab.get("sections", []):
                for item in sec.get("layout_items", []):
                    for prod in item.get("products", []):
                        if "price" in prod:
                            prod["price"] = int(prod["price"] * multiplier)
                        if "mrp" in prod:
                            prod["mrp"] = int(prod["mrp"] * multiplier)
                            
        return raw_response
