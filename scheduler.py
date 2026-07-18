import os
import sys
import time
import json
import logging
import argparse
from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler

from main import run_pipeline

# 1. Setup rotating logging
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, "scheduler.log")

logger = logging.getLogger("SchedulerDaemon")
logger.setLevel(logging.INFO)

# RotatingFileHandler: max 5MB, keep 3 backup logs
handler = RotatingFileHandler(
    log_file,
    maxBytes=5 * 1024 * 1024, # 5MB
    backupCount=3
)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

# Also output to stdout for visibility in terminal
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# IST Timezone setup
IST = timezone(timedelta(hours=5, minutes=30))

def write_heartbeat(status, metrics=None):
    """
    Writes a local 'heartbeat.json' file after runs.
    """
    heartbeat_path = "heartbeat.json"
    timestamp_str = datetime.now(IST).isoformat()
    
    heartbeat_data = {
        "timestamp": timestamp_str,
        "run_status": status,
        "total_rows_committed": metrics.get("total_rows_committed", 0) if metrics else 0,
        "platform_breakdown": metrics.get("platform_breakdown", {}) if metrics else {}
    }
    
    try:
        with open(heartbeat_path, "w") as f:
            json.dump(heartbeat_data, f, indent=4)
        logger.info(f"Successfully wrote heartbeat to {heartbeat_path} with status {status}.")
    except Exception as e:
        logger.error(f"Failed to write heartbeat file: {e}")

def execute_with_backoff(test_mode=False):
    """
    Executes the pipeline with Exponential Backoff:
    Initial -> Wait 2m -> Wait 4m -> Wait 8m (or 2s -> 4s -> 8s in test mode)
    """
    max_retries = 3
    retry_delay_multiplier = 2
    
    # Base delays in seconds
    initial_delay = 120 if not test_mode else 2
    
    for attempt in range(1 + max_retries):
        try:
            logger.info(f"Pipeline Execution Attempt #{attempt + 1} starting...")
            metrics = run_pipeline()
            logger.info("Pipeline Execution Attempt succeeded!")
            
            write_heartbeat("SUCCESS", metrics)
            return True
            
        except Exception as e:
            logger.error(f"Pipeline Execution Attempt #{attempt + 1} failed: {e}")
            
            if attempt < max_retries:
                # Calculate backoff delay: initial_delay * (2 ^ attempt)
                delay = initial_delay * (retry_delay_multiplier ** attempt)
                unit = "seconds" if test_mode else "minutes"
                display_delay = delay if test_mode else (delay / 60.0)
                
                logger.warning(f"Failed attempt #{attempt + 1}. Retrying in {display_delay:.1f} {unit}...")
                write_heartbeat("FAILED")
                time.sleep(delay)
            else:
                logger.error("CRITICAL: Maximum retry attempts reached. Pipeline execution failed permanently.")
                
                # Dynamic Telemetry Notification Alert
                try:
                    import traceback
                    from utils.notifier import AlertNotifier
                    traceback_str = traceback.format_exc()
                    notifier = AlertNotifier()
                    notifier.send_alert(
                        error_message=f"CRITICAL: Ingestion Pipeline failed after {max_retries} retries. Error: {e}",
                        traceback_snippet=traceback_str
                    )
                except Exception as alert_err:
                    logger.error(f"Failed to transmit telemetry alert notification: {alert_err}")
                
                write_heartbeat("FAILED")
                raise e
    return False

def daemon_loop(test_mode=False):
    if test_mode:
        logger.info("Daemon started in TEST MODE. Launching test execution in 10 seconds...")
        time.sleep(10)
        try:
            execute_with_backoff(test_mode=True)
            logger.info("Test execution check complete. Exiting test mode daemon.")
            sys.exit(0)
        except Exception:
            logger.critical("Test execution finished with failure.")
            sys.exit(1)

    logger.info("Scheduling Daemon started in PRODUCTION MODE. Monitoring time for 23:30 IST (11:30 PM) daily run...")
    last_run_date = None
    
    while True:
        try:
            now_ist = datetime.now(IST)
            
            # Check if it is 23:30 IST and we haven't run today yet
            if now_ist.hour == 23 and now_ist.minute == 30 and last_run_date != now_ist.date():
                logger.info(f"Time trigger matches! Current time: {now_ist.strftime('%H:%M:%S')} IST. Initiating daily run...")
                
                success = execute_with_backoff(test_mode=False)
                if success:
                    last_run_date = now_ist.date()
                    logger.info(f"Daily crawl run for {last_run_date} completed successfully. Resuming monitor.")
                else:
                    logger.error(f"Daily crawl run for {now_ist.date()} failed all attempts. Resuming monitor.")
            
            # Continuous loop checks: sleep 15 seconds to avoid excessive CPU usage
            time.sleep(15)
            
        except KeyboardInterrupt:
            logger.info("Daemon termination requested by user. Exiting...")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Unexpected error in daemon outer loop: {e}. Retrying loop check in 30 seconds...")
            time.sleep(30)

def main():
    parser = argparse.ArgumentParser(description="aerodata-qcomm Scheduling Daemon")
    parser.add_argument("--test", action="store_true", help="Trigger a test run 10 seconds after execution (overrides IST daily run constraint)")
    args = parser.parse_args()
    
    daemon_loop(test_mode=args.test)

if __name__ == "__main__":
    main()
