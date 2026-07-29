import os
import sys

# Add project root to PYTHONPATH dynamically
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import json
import logging
from scrapers.web_targets import ZEPTO_WEB_URL
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

class ZeptoScraper:
    def __init__(self, api_url=ZEPTO_WEB_URL):
        self.api_url = api_url

    def fetch_page(self, lat: float, lng: float, network_manager=None, session_harvester=None, session_key=None):
        """
        Fetches Zepto catalog layout by first attempting Playwright Direct Response Interception,
        with fallback to curl_cffi requests.
        """
        try:
            from scrapers.bootstrapper import fetch_live_catalog_payload
            payloads = fetch_live_catalog_payload("Zepto", lat, lng)
            if payloads:
                logger.info(f"Zepto Direct Response Interception retrieved {len(payloads)} payloads.")
                # Combine list of payloads into a unified format or return the first containing items
                for p in payloads:
                    if isinstance(p, dict) and any(k in p for k in ["layout", "widgets", "items", "data", "storeDetails"]):
                        return p
                return payloads[0]
        except Exception as boot_err:
            logger.warning(f"Zepto Direct Response Interception warning: {boot_err}")
            if STRICT_PROD_MODE:
                log_structured_error("Zepto", self.api_url, "INTERCEPTION_ERROR", f"Zepto interception failed: {boot_err}", zone=session_key, exc=boot_err)

        payload = {
            "latitude": lat,
            "longitude": lng,
            "pageId": "HOME",
            "pageType": "HOME"
        }
        
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://www.zeptonow.com",
            "Referer": "https://www.zeptonow.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "x-user-sub-platform": "WEB",
            "app_version": "12.0.0",
            "latitude": str(lat),
            "longitude": str(lng)
        }
        
        resolved_ip = resolve_domain_with_fallback("api.zepto.com")
        curl_opts = {}
        if resolved_ip:
            from curl_cffi import CurlOpt
            curl_opts[CurlOpt.RESOLVE] = [f"api.zepto.com:443:{resolved_ip}"]
            
        from scrapers.proxy_manager import ProxyManager
        proxy_mgr = ProxyManager()
        proxies = proxy_mgr.get_proxy_dict(session_key=session_key)
        
        cookies = {}
        if session_harvester:
            cookies = session_harvester.harvest_session("Zepto", network_manager, session_key=session_key)
        
        try:
            from scrapers.bootstrapper import get_live_session_context
            session_ctx = get_live_session_context("Zepto", lat, lng)
            if session_ctx.get("cookies"):
                cookies.update(session_ctx["cookies"])
            if session_ctx.get("headers"):
                headers.update(session_ctx["headers"])
        except Exception as boot_err:
            logger.warning(f"Zepto Playwright bootstrapper warning: {boot_err}")

        import time
        max_retries = 3
        last_exception = None

        for attempt in range(1, max_retries + 1):
            try:
                from curl_cffi import requests
                logger.info(f"Zepto POST request attempt #{attempt} to {self.api_url} (lat={lat}, lng={lng})")
                
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
                    
                logger.info(f"Zepto response status code: {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception as parse_err:
                        if STRICT_PROD_MODE:
                            log_structured_error("Zepto", self.api_url, "PARSING_ERROR", f"Invalid JSON response: {parse_err}", zone=session_key, exc=parse_err)
                            raise ScraperParsingError(f"Zepto response is not valid JSON: {parse_err}", status_code="PARSING_ERROR", target_url=self.api_url, platform="Zepto", zone=session_key) from parse_err
                        else:
                            return self._get_mock_response(lat, lng)
                    logger.info("Successfully fetched live response from Zepto API.")
                    return data
                else:
                    status_code = response.status_code
                    err_msg = f"Zepto API returned status code {status_code}"
                    log_structured_error("Zepto", self.api_url, status_code, err_msg, zone=session_key)
                    
                    if attempt < max_retries and status_code in (403, 429, 500, 502, 503, 504):
                        backoff = 2 ** attempt
                        logger.warning(f"Zepto request failed with status {status_code}. Retrying in {backoff}s...")
                        time.sleep(backoff)
                        continue

                    if STRICT_PROD_MODE:
                        if status_code == 429:
                            raise RateLimitError(err_msg, status_code=429, target_url=self.api_url, platform="Zepto", zone=session_key)
                        else:
                            raise ScraperHTTPError(err_msg, status_code=status_code, target_url=self.api_url, platform="Zepto", zone=session_key)
                    else:
                        logger.warning(f"Zepto API returned status code {status_code}. Activating mock data fallback.")
                        return self._get_mock_response(lat, lng)
                    
            except (ScraperError, RateLimitError, ScraperHTTPError, ScraperParsingError) as se:
                raise se
            except Exception as e:
                last_exception = e
                err_msg = f"Error fetching live Zepto API ({e})"
                log_structured_error("Zepto", self.api_url, 500, err_msg, zone=session_key, exc=e)
                if attempt < max_retries:
                    backoff = 2 ** attempt
                    logger.warning(f"Zepto network exception ({e}). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue

                if STRICT_PROD_MODE:
                    raise ScraperHTTPError(err_msg, status_code=500, target_url=self.api_url, platform="Zepto", zone=session_key) from e
                else:
                    logger.warning(f"Error fetching live Zepto API ({e}). Activating mock data fallback.")
                    return self._get_mock_response(lat, lng)

    def parse_layout(self, response_json):
        """
        Recursively parses the layout widget array from the JSON response to extract product catalog data.
        """
        if not isinstance(response_json, (dict, list)):
            if STRICT_PROD_MODE:
                log_structured_error("Zepto", self.api_url, "PARSING_ERROR", "Zepto layout response payload is not dict or list")
                raise ScraperParsingError("Zepto layout response payload is not dict or list", status_code="PARSING_ERROR", target_url=self.api_url, platform="Zepto")
            return []

        products = []
        try:
            store_info = {}
            if isinstance(response_json, dict):
                if "storeDetails" in response_json:
                    store_info = response_json["storeDetails"]
                elif "store_details" in response_json:
                    store_info = response_json["store_details"]
                elif "store" in response_json:
                    store_info = response_json["store"]

            self._extract_products_recursive(response_json, products, store_info)
        except Exception as e:
            if STRICT_PROD_MODE:
                log_structured_error("Zepto", self.api_url, "PARSING_ERROR", f"Layout parsing failed: {e}", exc=e)
                raise ScraperParsingError(f"Zepto layout parsing failed: {e}", status_code="PARSING_ERROR", target_url=self.api_url, platform="Zepto") from e
            else:
                logger.warning(f"Error parsing Zepto layout: {e}")

        logger.info(f"Parsed {len(products)} products from the layout response.")
        return products

    def _get_mock_response(self, lat, lng):
        if STRICT_PROD_MODE:
            err_msg = "Mock data generation disabled in STRICT_PROD_MODE for ZeptoScraper."
            log_structured_error("Zepto", self.api_url, "MOCK_DISABLED", err_msg)
            raise ScraperError(err_msg, status_code="MOCK_DISABLED", target_url=self.api_url, platform="Zepto")

        logger.info(f"Injecting high-fidelity mock Zepto layout response for ({lat}, {lng}).")
        
        # Deterministic price variance multiplier based on coordinate values (varying from 0% to 25%)
        multiplier = 1.0 + (abs(float(lat) * 7.0 + float(lng) * 3.0) % 25) / 100.0
        
        raw_response = {
            "storeDetails": {
                "storeId": f"store_indiranagar_{int(lat * 100)}_{int(lng * 100)}",
                "name": "Indiranagar Central Darkstore"
            },
            "layout": [
                {
                    "widgetType": "PRODUCT_GRID",
                    "widgetName": "Daily Essentials",
                    "data": {
                        "items": [
                            {
                                "product": {
                                    "id": "z-milk-901",
                                    "name": "Amul Taaza Toned Fresh Milk 1L",
                                    "brand": "Amul",
                                    "mrp": 5600,
                                    "sellingPrice": 5400,
                                    "outOfStock": False,
                                    "categoryName": "Dairy, Bread & Eggs"
                                }
                            },
                            {
                                "product": {
                                    "id": "z-butter-102",
                                    "name": "Amul Pasteurised Butter 100g",
                                    "brand": "Amul",
                                    "mrp": 5800,
                                    "sellingPrice": 5800,
                                    "outOfStock": False,
                                    "categoryName": "Dairy, Bread & Eggs"
                                }
                            },
                            {
                                "product": {
                                    "id": "z-bread-304",
                                    "name": "Harvest Gold Brown Bread 400g",
                                    "brand": "Harvest Gold",
                                    "mrp": 5000,
                                    "sellingPrice": 4800,
                                    "outOfStock": True,
                                    "categoryName": "Dairy, Bread & Eggs"
                                }
                            },
                            {
                                "product": {
                                    "id": "z-maggi-201",
                                    "name": "Maggi Instant Noodles 2-Min 70g",
                                    "brand": "Maggi",
                                    "mrp": 1400,
                                    "sellingPrice": 1400,
                                    "outOfStock": False,
                                    "categoryName": "Groceries"
                                }
                            },
                            {
                                "product": {
                                    "id": "z-outlier-expensive",
                                    "name": "Outlier Expensive Milk 1L",
                                    "brand": "Amul",
                                    "mrp": 600000,
                                    "sellingPrice": 600000,
                                    "outOfStock": False,
                                    "categoryName": "Dairy, Bread & Eggs"
                                }
                            },
                            {
                                "product": {
                                    "id": "z-outlier-free",
                                    "name": "Free Trial Bread 400g",
                                    "brand": "Harvest Gold",
                                    "mrp": 0,
                                    "sellingPrice": 0,
                                    "outOfStock": False,
                                    "categoryName": "Dairy, Bread & Eggs"
                                }
                            }
                        ]
                    }
                },
                {
                    "widgetType": "PRODUCT_CAROUSEL",
                    "widgetName": "Fresh Veggies",
                    "data": {
                        "items": [
                            {
                                "product": {
                                    "id": "z-onion-502",
                                    "name": "Fresh Onion 1kg",
                                    "brand": "Fresh Produce",
                                    "mrp": 4500,
                                    "sellingPrice": 3900,
                                    "outOfStock": False,
                                    "categoryName": "Fruits & Vegetables"
                                }
                            },
                            {
                                "product": {
                                    "id": "z-potato-602",
                                    "name": "Fresh Potato 1kg",
                                    "brand": "Fresh Produce",
                                    "mrp": 3500,
                                    "sellingPrice": 3200,
                                    "outOfStock": False,
                                    "categoryName": "Fruits & Vegetables"
                                }
                            },
                            {
                                "product": {
                                    "id": "z-tomato-702",
                                    "name": "Hybrid Tomato 500g",
                                    "brand": "Fresh Produce",
                                    "mrp": 4000,
                                    "sellingPrice": 3600,
                                    "outOfStock": True,
                                    "categoryName": "Fruits & Vegetables"
                                }
                            }
                        ]
                    }
                }
            ]
        }
        
        # Apply pricing variation to mock layouts dynamically
        for widget in raw_response.get("layout", []):
            for item in widget.get("data", {}).get("items", []):
                prod = item.get("product", {})
                if prod.get("id") == "z-outlier-free":
                    continue
                if prod.get("id") == "z-outlier-expensive":
                    continue
                if "mrp" in prod:
                    prod["mrp"] = int(prod["mrp"] * multiplier)
                if "sellingPrice" in prod:
                    prod["sellingPrice"] = int(prod["sellingPrice"] * multiplier)
                    
        return raw_response
