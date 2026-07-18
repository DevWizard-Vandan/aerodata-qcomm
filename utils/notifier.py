import os
import sys
import logging
from datetime import datetime, timezone
import requests

logger = logging.getLogger(__name__)

class AlertNotifier:
    """
    AlertNotifier manages automated notifications for critical system alarms.
    Supports Discord Webhook embeds and Telegram Bot APIs with graceful direct fallbacks.
    """
    def __init__(self):
        self.provider = os.environ.get("NOTIFICATION_PROVIDER", "none").lower().strip()
        self.discord_url = os.environ.get("DISCORD_WEBHOOK_URL")
        self.telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    def send_alert(self, error_message, traceback_snippet=None):
        """
        Sends pipeline alarm to the configured notification channel.
        Gracefully handles credentials checking to ensure zero scheduler crashes.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Check active provider validation
        if self.provider == "none":
            logger.info("Alert notification skipped: No active provider keys found (provider is set to 'none').")
            return True

        if self.provider == "discord":
            if not self.discord_url:
                logger.warning("Discord notifications requested but DISCORD_WEBHOOK_URL is missing. Alert skipped.")
                return False
            return self._send_discord(error_message, traceback_snippet, timestamp)

        elif self.provider == "telegram":
            if not self.telegram_token or not self.telegram_chat_id:
                logger.warning("Telegram notifications requested but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing. Alert skipped.")
                return False
            return self._send_telegram(error_message, traceback_snippet, timestamp)

        else:
            logger.info(f"Alert notification skipped: Unknown provider '{self.provider}'.")
            return True

    def _send_discord(self, error_msg, traceback_snippet, timestamp):
        # Format clean Discord Embed schema
        trace_str = traceback_snippet or "No traceback provided."
        if len(trace_str) > 1000:
            trace_str = trace_str[:980] + "\n...[TRUNCATED]"

        payload = {
            "embeds": [
                {
                    "title": "🔴 Pipeline Alert",
                    "color": 16711680, # Red
                    "fields": [
                        {"name": "Environment", "value": "Production", "inline": True},
                        {"name": "Timestamp", "value": timestamp, "inline": True},
                        {"name": "Error Message Summary", "value": error_msg, "inline": False},
                        {"name": "Exception Stack Trace", "value": f"```py\n{trace_str}\n```", "inline": False}
                    ]
                }
            ]
        }
        try:
            response = requests.post(self.discord_url, json=payload, timeout=10)
            if response.status_code in [200, 204]:
                logger.info("Alert successfully broadcasted to Discord.")
                return True
            else:
                logger.error(f"Failed to post to Discord. Status: {response.status_code}, Body: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error executing Discord webhook POST request: {e}")
            return False

    def _send_telegram(self, error_msg, traceback_snippet, timestamp):
        # Format clean bold Markdown payload
        text = f"⚠️ *aerodata-qcomm Alert*\n\n" \
               f"*Error:* {error_msg}\n" \
               f"*Time:* {timestamp}"
               
        if traceback_snippet:
            trace_str = traceback_snippet
            if len(trace_str) > 1000:
                trace_str = trace_str[:980] + "\n...[TRUNCATED]"
            text += f"\n\n*Traceback:*\n`{trace_str}`"

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Alert successfully broadcasted to Telegram.")
                return True
            else:
                logger.error(f"Failed to post to Telegram. Status: {response.status_code}, Body: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error executing Telegram API request: {e}")
            return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Self-test Direct Fallback
    notifier = AlertNotifier()
    assert notifier.send_alert("Diagnostic self-test"), "Fallback check must succeed cleanly"
    print("notifier.py self-test completed successfully.")
