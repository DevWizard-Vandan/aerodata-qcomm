import socket
import struct
import subprocess
import time
import logging
import random

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def dns_resolve_udp(domain, dns_server="8.8.8.8"):
    """
    Pure-Python UDP DNS client querying DNS server on port 53.
    """
    logger.info(f"Custom DNS resolving {domain} via {dns_server}...")
    try:
        # Transaction ID: 0x1234
        # Flags: 0x0100 (Standard query)
        # Questions: 1, Answer RRs: 0, Authority RRs: 0, Additional RRs: 0
        packet = struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
        
        # Split domain by dots and write each label length followed by the label
        for part in domain.split("."):
            packet += struct.pack("B", len(part)) + part.encode()
        packet += struct.pack("B", 0) # Zero length terminating byte
        
        # Type: A (1), Class: IN (1)
        packet += struct.pack(">HH", 1, 1)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3.0)
        sock.sendto(packet, (dns_server, 53))
        data, _ = sock.recvfrom(512)
        
        if len(data) < 12:
            return None
            
        # Parse transaction details
        _, _, qdcount, ancount, _, _ = struct.unpack(">HHHHHH", data[:12])
        
        # Skip question section
        offset = 12
        for _ in range(qdcount):
            while data[offset] != 0:
                offset += 1 + data[offset]
            offset += 5 # Null byte + Type (2) + Class (2)
            
        # Parse answers
        ips = []
        for _ in range(ancount):
            # Skip name pointer/label
            if (data[offset] & 0xC0) == 0xC0:
                offset += 2
            else:
                while data[offset] != 0:
                    offset += 1 + data[offset]
                offset += 1
            # Type (2), Class (2), TTL (4), RData Length (2)
            atype, aclass, _, rdlength = struct.unpack(">HHIH", data[offset:offset+10])
            offset += 10
            if atype == 1 and aclass == 1 and rdlength == 4: # A (IPv4)
                ip_bytes = data[offset:offset+4]
                ip = ".".join(map(str, ip_bytes))
                ips.append(ip)
            offset += rdlength
        
        if ips:
            resolved_ip = ips[0]
            logger.info(f"Resolved {domain} to {resolved_ip} via {dns_server}")
            return resolved_ip
    except Exception as e:
        logger.warning(f"UDP DNS resolution failed for {domain} via {dns_server}: {e}")
    return None

def resolve_domain_with_fallback(domain):
    """
    Tries to resolve domain using standard socket first,
    falls back to custom UDP DNS (8.8.8.8, 1.1.1.1) programmatically if it fails.
    """
    try:
        ip = socket.gethostbyname(domain)
        logger.info(f"System DNS resolved {domain} to {ip}")
        return ip
    except socket.gaierror:
        logger.warning(f"System DNS failed to resolve {domain}. Activating UDP DNS resolution fallback...")
        ip = dns_resolve_udp(domain, "8.8.8.8")
        if not ip:
            ip = dns_resolve_udp(domain, "1.1.1.1")
        return ip

class NetworkManager:
    def __init__(self, proxies=None):
        # Premium proxy rotation list configuration
        self.proxies_list = proxies or []
        self.consecutive_blocks = 0
        self.max_blocks_before_toggle = 2

    def get_proxy(self):
        if not self.proxies_list:
            return None
        proxy = random.choice(self.proxies_list)
        return {"http": proxy, "https": proxy}

    def handle_request_status(self, status_code):
        if status_code == 429 or status_code in (403, 503):
            self.consecutive_blocks += 1
            logger.warning(f"Request blocked with status {status_code}. Consecutive blocks: {self.consecutive_blocks}")
            if self.consecutive_blocks >= self.max_blocks_before_toggle:
                self.cycle_airplane_mode()
                self.consecutive_blocks = 0
        else:
            self.consecutive_blocks = 0

    def cycle_airplane_mode(self):
        logger.info("CRITICAL LIMIT EXCEEDED. Activating hardware-level cellular IP rotation...")
        try:
            # 1. Turn Airplane Mode ON
            logger.info("Enabling Airplane Mode...")
            subprocess.run(["adb", "shell", "cmd", "connectivity", "airplane-mode", "enable"], check=True, capture_output=True, timeout=5)
            
            # Sleep 6 seconds
            logger.info("Sleeping 6 seconds in Airplane Mode...")
            time.sleep(6)
            
            # 2. Turn Airplane Mode OFF
            logger.info("Disabling Airplane Mode...")
            subprocess.run(["adb", "shell", "cmd", "connectivity", "airplane-mode", "disable"], check=True, capture_output=True, timeout=5)
            
            # Wait for network interface to come back online (up to 30 seconds)
            logger.info("Waiting for cellular network interface to re-authenticate...")
            start_wait = time.time()
            online = False
            while time.time() - start_wait < 30:
                try:
                    socket.setdefaulttimeout(1.5)
                    # Quick TCP connect to Cloudflare/Google public DNS
                    socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
                    online = True
                    break
                except Exception:
                    time.sleep(1)
            
            if online:
                logger.info(f"Cellular interface online after {time.time() - start_wait:.1f} seconds. IP successfully rotated.")
                return True
            else:
                logger.warning("Cellular interface failed to regain connectivity within 30 seconds.")
                return False
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.warning(f"Hardware-level IP rotation bypassed: ADB tool or connected USB device not found ({e}). Continuing gracefully.")
            return False
