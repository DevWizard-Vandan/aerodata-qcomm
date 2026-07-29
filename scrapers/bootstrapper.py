import os
import sys
import json
import logging
from scrapers.exceptions import STRICT_PROD_MODE, ScraperError, log_structured_error

logger = logging.getLogger(__name__)

def fetch_live_catalog_payload(platform: str, lat: float, lng: float, timeout_ms: int = 25000) -> list:
    """
    Launches Playwright Chromium in headless mode, setting geolocation,
    and intercepts incoming network responses to capture raw JSON catalog/product payloads.
    """
    logger.info(f"Initiating Playwright Direct Response Interception for '{platform}' at ({lat}, {lng})...")
    
    target_urls = {
        "Zepto": "https://www.zeptonow.com/",
        "Blinkit": "https://blinkit.com/",
        "Swiggy Instamart": "https://www.swiggy.com/instamart"
    }
    
    target_url = target_urls.get(platform, "https://www.google.com")
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
                user_agent=user_agent_str
            )
            
            page = context.new_page()
            
            def handle_response(response):
                content_type = response.headers.get("content-type", "").lower()
                if "json" in content_type:
                    try:
                        data = response.json()
                        str_data = str(data).lower()
                        if any(k in str_data for k in ["product", "catalog", "layout", "widgets", "items"]):
                            captured_payloads.append(data)
                    except Exception:
                        pass
            
            page.on("response", handle_response)
            
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(5000)
            except Exception as nav_err:
                logger.warning(f"Playwright navigation non-fatal warning for {platform}: {nav_err}")

            browser.close()

        logger.info(f"Playwright Direct Response Interception captured {len(captured_payloads)} JSON payloads for platform '{platform}'.")
        return captured_payloads

    except Exception as e:
        err_msg = f"Playwright Direct Response Interception failed for platform '{platform}': {e}"
        log_structured_error(platform, target_url, "INTERCEPTION_ERROR", err_msg, exc=e)
        if STRICT_PROD_MODE:
            raise ScraperError(err_msg, status_code="INTERCEPTION_ERROR", target_url=target_url, platform=platform) from e
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
        "Zepto": "https://www.zeptonow.com/",
        "Blinkit": "https://blinkit.com/",
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
