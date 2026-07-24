import os
import json
import logging
import traceback
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Global STRICT_PROD_MODE toggle (Defaults to True for production & burn-in)
STRICT_PROD_MODE = os.getenv("STRICT_PROD_MODE", "true").lower() == "true"

class ScraperError(Exception):
    """Base exception for all scraping infrastructure errors."""
    def __init__(self, message, status_code=None, target_url=None, platform=None, store_id=None, zone=None):
        super().__init__(message)
        self.message = str(message)
        self.status_code = status_code
        self.target_url = target_url
        self.platform = platform
        self.store_id = store_id
        self.zone = zone

class ScraperHTTPError(ScraperError):
    """Raised when an HTTP non-200 status code (403, 404, 503, etc.) is returned in STRICT_PROD_MODE."""
    pass

class RateLimitError(ScraperHTTPError):
    """Raised when HTTP 429 Rate Limit or anti-bot challenge is encountered in STRICT_PROD_MODE."""
    pass

class ScraperParsingError(ScraperError):
    """Raised when layout JSON or DOM selector fails to parse in STRICT_PROD_MODE."""
    pass

def log_structured_error(platform, target_url, status_code, error_message, store_id=None, zone=None, exc=None):
    """
    Formats and emits a structured JSON error log payload for production telemetry monitoring.
    """
    tb_snippet = traceback.format_exc() if exc else ""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": platform,
        "store_id": store_id or "UNKNOWN",
        "zone": zone or "UNKNOWN",
        "status_code": status_code,
        "target_url": target_url,
        "error_message": str(error_message),
        "traceback": tb_snippet
    }
    logger.error(f"STRUCTURED_SCRAPER_ERROR: {json.dumps(payload, indent=2)}")
    return payload
