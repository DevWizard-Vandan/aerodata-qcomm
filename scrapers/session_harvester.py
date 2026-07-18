import os
import sys

# Add project root to PYTHONPATH dynamically
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import logging
from curl_cffi import requests
from scrapers.web_targets import ZEPTO_HOMEPAGE, BLINKIT_HOMEPAGE, SWIGGY_HOMEPAGE
from scrapers.proxy_manager import ProxyManager

logger = logging.getLogger(__name__)

class SessionHarvester:
    """
    SessionHarvester fetches and caches browser-facing cookies for target platforms.
    Uses curl_cffi impersonation profiles to negotiate headers, cookies, and TLS signatures
    just like standard consumer browsers.
    """
    def __init__(self):
        self.cookie_cache = {}
        self.proxy_manager = ProxyManager()
        # Homepage mapping
        self.homepages = {
            "Zepto": ZEPTO_HOMEPAGE,
            "Blinkit": BLINKIT_HOMEPAGE,
            "Swiggy Instamart": SWIGGY_HOMEPAGE
        }

    def harvest_session(self, platform_name, network_manager=None, session_key=None):
        """
        Executes a pre-flight GET request to harvest CSRF tokens or base cookies
        and stores them in the local session cache.
        """
        homepage_url = self.homepages.get(platform_name)
        if not homepage_url:
            logger.warning(f"No homepage URL mapped for platform: {platform_name}")
            return {}

        # Check if already cached
        if platform_name in self.cookie_cache:
            logger.info(f"Using cached session cookies for platform: {platform_name}")
            return self.cookie_cache[platform_name]

        logger.info(f"Harvesting baseline session cookies for {platform_name} from {homepage_url}...")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/"
        }
        
        # Apply proxy from ProxyManager
        proxies = self.proxy_manager.get_proxy_dict(session_key=session_key)

        try:
            # impersonate Chrome 120 client for valid TLS signature
            response = requests.get(
                homepage_url,
                headers=headers,
                proxies=proxies,
                impersonate="chrome120",
                timeout=12
            )
            cookies_dict = response.cookies.get_dict()
            logger.info(f"Successfully harvested {len(cookies_dict)} cookies for {platform_name}: {list(cookies_dict.keys())}")
            self.cookie_cache[platform_name] = cookies_dict
            return cookies_dict
        except Exception as e:
            logger.warning(f"Session harvesting failed for {platform_name}: {e}. Continuing with empty session state.")
            # Fallback to empty session to allow scraping / mock triggers to continue
            self.cookie_cache[platform_name] = {}
            return {}

    def get_session_cookies(self, platform_name):
        return self.cookie_cache.get(platform_name, {})

if __name__ == "__main__":
    # Diagnostic self-test
    logging.basicConfig(level=logging.INFO)
    harvester = SessionHarvester()
    # Test session harvest on Zepto (mock test connection / root validation)
    cookies = harvester.harvest_session("Zepto")
    print("Harvested cookies:", cookies)
