import os
import sys
import json
import logging
from scrapers.exceptions import STRICT_PROD_MODE, ScraperError, log_structured_error

logger = logging.getLogger(__name__)

def fetch_live_catalog_payload(platform: str, lat: float, lng: float, timeout_ms: int = 30000) -> list:
    """
    Launches Playwright Chromium in headless mode with spatial geolocation permissions,
    attaches a network response listener before navigation, and executes subtle scroll interactions
    to trigger lazy-loaded XHR catalog responses.
    """
    logger.info(f"Initiating Playwright Direct Response Interception for '{platform}' at ({lat}, {lng})...")
    
    target_urls_map = {
        "Zepto": [
            "https://www.zeptonow.com/search?query=milk",
            "https://www.zeptonow.com/cn/dairy-bread-eggs/cid/21b3fa12-1f48-4e8a-bf90-349f863d1efc"
        ],
        "Blinkit": [
            "https://blinkit.com/s/?q=milk",
            "https://blinkit.com/cn/fresh-vegetables/cid/1487/1489"
        ],
        "Swiggy Instamart": [
            "https://www.swiggy.com/instamart/search?custom_back=true&query=milk",
            "https://www.swiggy.com/instamart"
        ]
    }
    
    urls_to_try = target_urls_map.get(platform, ["https://www.google.com"])
    user_agent_str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    captured_payloads = []
    
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            context = browser.new_context(
                geolocation={"latitude": float(lat), "longitude": float(lng), "accuracy": 100},
                permissions=["geolocation"],
                viewport={"width": 1366, "height": 768},
                user_agent=user_agent_str,
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"'
                }
            )
            
            # Inject spatial geolocation cookies for Swiggy, Zepto, Blinkit
            cookies_to_add = [
                {"name": "lat", "value": str(lat), "url": "https://www.swiggy.com"},
                {"name": "lng", "value": str(lng), "url": "https://www.swiggy.com"},
                {"name": "_instamart_lat", "value": str(lat), "url": "https://www.swiggy.com"},
                {"name": "_instamart_lng", "value": str(lng), "url": "https://www.swiggy.com"},
                {"name": "swiggy_location", "value": f"{lat}%2C{lng}", "url": "https://www.swiggy.com"},
                {"name": "latitude", "value": str(lat), "url": "https://www.zeptonow.com"},
                {"name": "longitude", "value": str(lng), "url": "https://www.zeptonow.com"},
                {"name": "lat", "value": str(lat), "url": "https://blinkit.com"},
                {"name": "lon", "value": str(lng), "url": "https://blinkit.com"}
            ]
            try:
                context.add_cookies(cookies_to_add)
            except Exception as cookie_err:
                logger.warning(f"Failed to add location cookies: {cookie_err}")
            
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            """)
            
            page = context.new_page()
            
            def handle_response(response):
                try:
                    if response.status not in (200, 201):
                        return
                    ct = response.headers.get("content-type", "").lower()
                    if "json" in ct or "application/json" in ct or ct.endswith("/json"):
                        try:
                            data = response.json()
                            str_data = str(data).lower()
                            if any(k in str_data for k in ["product", "catalog", "layout", "widgets", "items", "categories", "variations", "storeid", "price", "mrp", "search", "searchresult"]):
                                captured_payloads.append(data)
                        except Exception:
                            pass
                except Exception:
                    pass
            
            page.on("response", handle_response)
            
            for target_url in urls_to_try:
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(3000)
                    
                    for _ in range(3):
                        page.evaluate("window.scrollBy(0, 1000)")
                        page.wait_for_timeout(1500)

                    if captured_payloads:
                        break
                except Exception as nav_err:
                    logger.warning(f"Playwright navigation fallback for {platform} on {target_url}: {nav_err}")

            browser.close()

        logger.info(f"Playwright Direct Response Interception captured {len(captured_payloads)} JSON payloads for platform '{platform}'.")
        return captured_payloads

    except Exception as e:
        err_msg = f"Playwright Direct Response Interception failed for platform '{platform}': {e}"
        log_structured_error(platform, urls_to_try[0], "INTERCEPTION_ERROR", err_msg, exc=e)
        if STRICT_PROD_MODE:
            raise ScraperError(err_msg, status_code="INTERCEPTION_ERROR", target_url=urls_to_try[0], platform=platform) from e
        else:
            logger.warning(f"{err_msg}. Returning empty payload list.")
            return []


def get_live_session_context(platform: str, lat: float, lng: float, timeout_ms: int = 25000) -> dict:
    """
    Launches Playwright Chromium in headless mode to render platform PWAs, inject geolocations,
    and intercept outgoing session cookies, authorization headers, and spatial tokens.
    """
    logger.info(f"Initiating Playwright session bootstrapper for platform '{platform}' at ({lat}, {lng})...")
    
    target_urls = {
        "Zepto": "https://www.zeptonow.com/cn/dairy-bread-eggs/cid/21b3fa12-1f48-4e8a-bf90-349f863d1efc",
        "Blinkit": "https://blinkit.com/cn/fresh-vegetables/cid/1487/1489",
        "Swiggy Instamart": "https://www.swiggy.com/instamart"
    }
    
    target_url = target_urls.get(platform, "https://www.google.com")
    
    captured_cookies = {}
    captured_headers = {}
    user_agent_str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            context = browser.new_context(
                geolocation={"latitude": float(lat), "longitude": float(lng), "accuracy": 100},
                permissions=["geolocation"],
                viewport={"width": 1366, "height": 768},
                user_agent=user_agent_str
            )
            
            page = context.new_page()
            
            def handle_request(request):
                url = request.url.lower()
                req_headers = request.headers
                
                if platform.lower() in ("zepto", "zeptonow") and "zepto" in url:
                    for key in ("x-session-id", "x-user-sub-platform", "app_version", "authorization", "x-xsrf-token"):
                        if key in req_headers:
                            captured_headers[key] = req_headers[key]
                elif platform.lower() in ("blinkit",) and "blinkit" in url:
                    for key in ("app_client_id", "lat", "lon", "auth_key", "device_id"):
                        if key in req_headers:
                            captured_headers[key] = req_headers[key]
                elif platform.lower() in ("swiggy", "swiggy instamart") and "swiggy" in url:
                    for key in ("lat", "lng", "user-id", "version-code"):
                        if key in req_headers:
                            captured_headers[key] = req_headers[key]
            
            page.on("request", handle_request)
            
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(3000)
            except Exception as nav_err:
                logger.warning(f"Playwright navigation non-fatal warning for {platform}: {nav_err}")

            raw_cookies = context.cookies()
            for c in raw_cookies:
                captured_cookies[c["name"]] = c["value"]
                
            browser.close()

        captured_cookies["lat"] = str(lat)
        captured_cookies["lng"] = str(lng)
        captured_cookies["_instamart_lat"] = str(lat)
        captured_cookies["_instamart_lng"] = str(lng)

        logger.info(f"Playwright successfully bootstrapped {len(captured_cookies)} cookies and {len(captured_headers)} headers for {platform}.")
        
        return {
            "cookies": captured_cookies,
            "headers": captured_headers,
            "user_agent": user_agent_str
        }

    except Exception as e:
        err_msg = f"Playwright session bootstrapping failed for platform '{platform}': {e}"
        log_structured_error(platform, target_url, "BOOTSTRAP_ERROR", err_msg, exc=e)
        if STRICT_PROD_MODE:
            raise ScraperError(err_msg, status_code="BOOTSTRAP_ERROR", target_url=target_url, platform=platform) from e
        else:
            logger.warning(f"{err_msg}. Falling back to empty session context.")
            return {"cookies": {"lat": str(lat), "lng": str(lng)}, "headers": {}, "user_agent": user_agent_str}
