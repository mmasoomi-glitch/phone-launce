import subprocess
import re
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


def _ping(ip):
    """Ping a single IP to populate ARP cache. Returns None."""
    try:
        subprocess.run(
            ["ping", "-n", "1", "-w", "100", ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        pass


def populate_arp_cache(subnet):
    """Ping sweep the /24 subnet to refresh ARP entries."""
    ips = [f"{subnet}.{i}" for i in range(1, 255)]
    with ThreadPoolExecutor(max_workers=50) as pool:
        pool.map(_ping, ips)


def get_arp_table():
    """Parse 'arp -a' output. Returns dict of normalized MAC -> IP."""
    try:
        output = subprocess.check_output(
            ["arp", "-a"], text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
    except Exception as e:
        logger.error(f"Failed to read ARP table: {e}")
        return {}

    table = {}
    pattern = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s+([\w-]{17})\s+dynamic", re.IGNORECASE)
    for match in pattern.finditer(output):
        ip = match.group(1)
        mac = match.group(2).replace("-", ":").lower()
        table[mac] = ip
    return table


def normalize_mac(mac):
    """Normalize a MAC address to lowercase colon-separated format."""
    return mac.replace("-", ":").lower().strip()


def scan_network(subnet):
    """Populate ARP cache and return the current ARP table."""
    populate_arp_cache(subnet)
    return get_arp_table()


def is_phone_present(arp_table, target_mac):
    """Check if the target MAC is in the ARP table."""
    return normalize_mac(target_mac) in arp_table


def get_phone_ip(arp_table, target_mac):
    """Get the IP address of the target phone."""
    return arp_table.get(normalize_mac(target_mac))
