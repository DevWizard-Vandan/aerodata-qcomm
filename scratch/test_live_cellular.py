import sys
import os
import json
import logging
import time
import subprocess

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def execute_adb_command(cmd_args, timeout=15):
    try:
        full_cmd = ["adb"] + cmd_args
        res = subprocess.run(full_cmd, capture_output=True, text=True, check=True, timeout=timeout)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"ADB command failed: {e.cmd}. Error: {e.stderr.strip() if e.stderr else ''}")
        return None
    except Exception as e:
        logger.error(f"Failed to execute ADB command: {e}")
        return None

def wait_for_adb_device(timeout=25):
    try:
        logger.info("Blocking until ADB device is online (wait-for-device)...")
        subprocess.run(["adb", "wait-for-device"], timeout=timeout, check=True)
        logger.info("ADB device detected and online.")
        return True
    except Exception as e:
        logger.warning(f"ADB wait-for-device timed out/failed: {e}")
        return False

def get_phone_public_ip():
    ip = execute_adb_command(["shell", "curl", "-s", "https://api.ipify.org"])
    return ip if ip else "Unknown"

def main():
    logger.info("=== STEP 0: CHECK INITIAL PUBLIC IP (ON PHONE) ===")
    ip_before = get_phone_public_ip()
    logger.info(f"Current cellular IP before rotation: {ip_before}")

    logger.info("=== STEP 1: EXECUTE ADB AIRPLANE MODE TOGGLE ===")
    logger.info("Enabling Airplane Mode...")
    execute_adb_command(["shell", "cmd", "connectivity", "airplane-mode", "enable"])
    
    logger.info("Sleeping 6 seconds in Airplane Mode...")
    time.sleep(6)
    
    logger.info("Disabling Airplane Mode...")
    execute_adb_command(["shell", "cmd", "connectivity", "airplane-mode", "disable"])
    
    # Introduce small delay for USB gadget reset to trigger on the host OS
    logger.info("Sleeping 3 seconds for USB gadget reset to trigger...")
    time.sleep(3)
    
    # Wait for ADB link reconnection
    wait_for_adb_device(25)
    
    logger.info("Sleeping 15 seconds for cellular carrier radio re-authentication...")
    time.sleep(15)
    logger.info("Cellular interface re-authenticated.")

    logger.info("=== STEP 2: CHECK PUBLIC IP AFTER ROTATION (ON PHONE) ===")
    ip_after = get_phone_public_ip()
    logger.info(f"New cellular IP after rotation: {ip_after}")
    if ip_before != "Unknown" and ip_after != "Unknown" and ip_before == ip_after:
        logger.warning("IP address did not change! Ensure mobile network connection is active.")
    else:
        logger.info("IP address successfully rotated!")

    logger.info("=== STEP 3: PERFORM LIVE TARGET CONNECTION TEST (ON PHONE) ===")
    url = "https://api.zepto.com/lms/api/v2/get_page"
    
    payload = {
        "latitude": 12.9716,
        "longitude": 77.5946,
        "pageId": "HOME",
        "pageType": "HOME"
    }
    payload_str = json.dumps(payload)
    
    sh_content = f"""#!/system/bin/sh
curl -i -s -X POST \\
  -H "Content-Type: application/json" \\
  -H "tenant: ZEPTO" \\
  -H "platform: android" \\
  -H "app_version: 12.0.0" \\
  -H "Origin: https://www.zeptonow.com" \\
  -H "Referer: https://www.zeptonow.com/" \\
  -H "User-Agent: Mozilla/5.0 (Linux; Android 13; SM-S918B Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/110.0.5481.154 Mobile Safari/537.36 okhttp/4.12.0" \\
  -d '{payload_str}' \\
  {url}
"""
    
    local_script_path = os.path.join("scratch", "run_curl.sh")
    os.makedirs("scratch", exist_ok=True)
    with open(local_script_path, "w", newline="\n") as f:
        f.write(sh_content)
        
    logger.info("Pushing script to Android temp folder /data/local/tmp/...")
    execute_adb_command(["push", local_script_path, "/data/local/tmp/run_curl.sh"])
    execute_adb_command(["shell", "chmod", "+x", "/data/local/tmp/run_curl.sh"])
    
    logger.info("Executing curl script directly on Android device...")
    output = execute_adb_command(["shell", "/data/local/tmp/run_curl.sh"], timeout=25)
    
    # Cleanup script files
    execute_adb_command(["shell", "rm", "/data/local/tmp/run_curl.sh"])
    if os.path.exists(local_script_path):
        os.remove(local_script_path)
        
    if output:
        logger.info("=== LIVE TARGET API RESPONSE ===")
        parts = output.split("\r\n\r\n", 1)
        headers = parts[0]
        body = parts[1] if len(parts) > 1 else ""
        
        logger.info(f"Response Headers:\n{headers}")
        
        status_line = headers.splitlines()[0] if headers else "Unknown status"
        logger.info(f"Status Code Line: {status_line}")
        logger.info(f"Response Size: {len(body)} bytes")
        
        if len(body) > 600:
            snippet = body[:600] + "... [TRUNCATED]"
        else:
            snippet = body
        logger.info(f"Response snippet:\n{snippet}")
        
        if "layout" in body or "pageLayouts" in body or "modules" in body:
            logger.info("SUCCESS: Successfully fetched genuine storefront JSON layout from rotated cellular IP!")
        else:
            logger.warning("Zepto did not return storefront modules. Checking if blocked or payload mismatched.")
    else:
        logger.error("Failed to receive output from phone curl command.")

if __name__ == "__main__":
    main()
