import os
import sys

# Add project root to PYTHONPATH dynamically
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import logging
import argparse
from curl_cffi import requests
from scrapers.network_manager import NetworkManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def test_endpoint(url, proxy_protocol=None, proxy_host=None, proxy_port=None, proxy_user=None, proxy_pass=None):
    """
    Test connection to a target endpoint using curl_cffi.
    Optionally configures HTTP or SOCKS5 proxies.
    """
    logger.info(f"Initiating diagnostic connection test to: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S918B Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/110.0.5481.154 Mobile Safari/537.36"
    }
    
    proxies = None
    if proxy_protocol and proxy_host and proxy_port:
        auth_str = ""
        if proxy_user and proxy_pass:
            auth_str = f"{proxy_user}:{proxy_pass}@"
            
        proxy_url = f"{proxy_protocol.lower()}://{auth_str}{proxy_host}:{proxy_port}"
        proxies = {"http": proxy_url, "https": proxy_url}
        logger.info(f"Applying proxy mapping: {proxy_protocol.upper()} -> {proxy_host}:{proxy_port}")
        
    try:
        response = requests.get(
            url,
            headers=headers,
            impersonate="chrome110",
            proxies=proxies,
            timeout=10
        )
        
        logger.info("=== DIAGNOSTIC CONNECTION RESULT ===")
        logger.info(f"HTTP Status Code: {response.status_code}")
        logger.info(f"Response Size: {len(response.content)} bytes")
        logger.info(f"Response Header Keys: {list(response.headers.keys())}")
        logger.info(f"First 150 chars of response body: {response.text[:150]}")
        logger.info("====================================")
        return True
    except Exception as e:
        logger.error(f"Diagnostic connection failed: {e}")
        return False

def trigger_manual_rotation():
    """
    Manually fires the hardware ADB cellular IP cycle.
    """
    logger.info("Triggering manual cellular IP rotation test...")
    manager = NetworkManager()
    success = manager.cycle_airplane_mode()
    if success:
        logger.info("IP rotation execution complete (check logs above for outcome).")
    else:
        logger.warning("IP rotation execution finished with warnings (ADB or device missing).")

def main():
    parser = argparse.ArgumentParser(description="aerodata-qcomm Connection Diagnostics & Cellular IP Rotation Tuner")
    parser.add_argument("--url", default="https://www.google.com", help="Target URL to test (default: https://www.google.com)")
    parser.add_argument("--proxy-proto", choices=["http", "socks5"], help="Proxy protocol (HTTP or SOCKS5)")
    parser.add_argument("--proxy-host", help="Proxy server host IP/domain")
    parser.add_argument("--proxy-port", type=int, help="Proxy server port number")
    parser.add_argument("--proxy-user", help="Proxy username (optional)")
    parser.add_argument("--proxy-pass", help="Proxy password (optional)")
    parser.add_argument("--rotate-ip", action="store_true", help="Manually trigger ADB cellular airplane mode toggle loop")
    
    args = parser.parse_args()
    
    if args.rotate_ip:
        trigger_manual_rotation()
        sys.exit(0)
        
    test_endpoint(
        url=args.url,
        proxy_protocol=args.proxy_proto,
        proxy_host=args.proxy_host,
        proxy_port=args.proxy_port,
        proxy_user=args.proxy_user,
        proxy_pass=args.proxy_pass
    )

if __name__ == "__main__":
    main()
