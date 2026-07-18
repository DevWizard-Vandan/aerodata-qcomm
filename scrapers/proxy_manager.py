import os
import logging
import hashlib
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

class ProxyManager:
    """
    ProxyManager handles proxy configuration and dynamic rotation/stickiness setup.
    Integrates with curl_cffi and requests-based scraping agents.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        # Implement singleton to ensure unified configuration and logging across scrapers
        if not cls._instance:
            cls._instance = super(ProxyManager, cls).__new__(cls, *args, **kwargs)
            cls._instance._init_manager()
        return cls._instance

    def _init_manager(self):
        self.proxy_url = os.environ.get("PROXY_URL")
        self.proxy_user = os.environ.get("PROXY_USER")
        self.proxy_pass = os.environ.get("PROXY_PASS")
        self.has_logged_notice = False

    def get_proxy_dict(self, session_key=None):
        """
        Returns a curl_cffi-compatible proxies dictionary:
        {"http": "http://...", "https": "http://..."} or None if not configured.
        
        If a session_key is provided, applies sticky session logic.
        """
        if not self.proxy_url:
            if not self.has_logged_notice:
                logger.info("No proxy environment configured. Defaulting to direct host adapter footprint.")
                self.has_logged_notice = True
            return None

        # Reconstruct base proxy URL
        url = self.proxy_url
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "http://" + url

        user = self.proxy_user
        
        # 1. Credentials-based Sticky Session (e.g. user-session-BLR_IND)
        if session_key and user:
            user = f"{user}-session-{session_key}"

        if user and self.proxy_pass:
            parsed = urlparse(url)
            netloc = parsed.netloc
            # Rebuild proxy with stickiness suffix credentials
            proxy_str = f"http://{user}:{self.proxy_pass}@{netloc}"
        else:
            # 2. Port-offset Sticky Session (for direct-IP multi-port proxy nodes)
            if session_key:
                parsed = urlparse(url)
                netloc = parsed.netloc
                if ":" in netloc:
                    host, port_str = netloc.rsplit(":", 1)
                    try:
                        base_port = int(port_str)
                        # Deterministic port offset mapping (0-99 range)
                        offset = int(hashlib.md5(session_key.encode('utf-8')).hexdigest(), 16) % 100
                        netloc = f"{host}:{base_port + offset}"
                        parsed = parsed._replace(netloc=netloc)
                        url = urlunparse(parsed)
                    except ValueError:
                        pass
            proxy_str = url

        return {
            "http": proxy_str,
            "https": proxy_str
        }

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Self-test direct fallback
    mgr = ProxyManager()
    p_dict = mgr.get_proxy_dict()
    assert p_dict is None, "Expected None proxy dict when variables are not set"
    
    # Mock environment configuration
    os.environ["PROXY_URL"] = "proxy.example.com:8000"
    os.environ["PROXY_USER"] = "alice"
    os.environ["PROXY_PASS"] = "secret"
    
    # Reset singleton state for testing
    ProxyManager._instance = None
    mgr2 = ProxyManager()
    
    # Verify mock output format
    p_dict2 = mgr2.get_proxy_dict(session_key="BLR_IND")
    expected_user = "alice-session-BLR_IND"
    assert p_dict2 is not None
    assert expected_user in p_dict2["http"], f"Sticky user check failed: {p_dict2}"
    
    # Test port offset mapping without credentials
    os.environ["PROXY_USER"] = ""
    os.environ["PROXY_PASS"] = ""
    ProxyManager._instance = None
    mgr3 = ProxyManager()
    p_dict3 = mgr3.get_proxy_dict(session_key="BOM_LPR")
    assert p_dict3 is not None
    assert "80" in p_dict3["http"] and p_dict3["http"] != "http://proxy.example.com:8000"
    
    print("ProxyManager SRE self-tests passed successfully.")
