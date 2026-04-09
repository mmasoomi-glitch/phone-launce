"""
start_usb.py — Start the phone mirror server for USB-connected Android device.
Run this instead of main.py when your phone is connected via USB cable.

Usage:
    python start_usb.py

Requirements:
    - USB Debugging enabled on phone
    - Phone trusted (tapped Allow on the popup)
    - ADB in PATH (installed with scrcpy or standalone platform-tools)
"""
import json, os, logging, subprocess, sys
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from remote_desktop import start_remote_desktop

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.log")
handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler()])
logger = logging.getLogger("start_usb")


def load_config():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(base_dir, ".env"))
    with open(os.path.join(base_dir, "config.json")) as f:
        return json.load(f)


def get_usb_device():
    """Return serial of first USB-connected ADB device, or None."""
    try:
        out = subprocess.check_output(["adb", "devices", "-l"], text=True, timeout=8)
    except FileNotFoundError:
        logger.error("ADB not found. Install scrcpy (includes adb) or add adb.exe to PATH.")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        logger.error("ADB timed out.")
        return None

    devices = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serial = parts[0]
            if ":" not in serial:   # USB serials have no colon; WiFi = ip:port
                model = next((p.split(":")[1] for p in parts if p.startswith("model:")), serial)
                devices.append((serial, model))
        elif len(parts) >= 2 and parts[1] == "unauthorized":
            logger.warning(f"Device {parts[0]} UNAUTHORIZED — tap Allow on your phone screen.")
        elif len(parts) >= 2 and parts[1] == "offline":
            logger.warning(f"Device {parts[0]} OFFLINE — replug USB cable.")

    if not devices:
        logger.error(
            "No USB Android device found.\n"
            "  1. Is the USB cable plugged in?\n"
            "  2. Is USB Debugging ON in Developer Options?\n"
            "  3. Did you tap 'Allow' on your phone when asked?"
        )
        return None

    serial, model = devices[0]
    if len(devices) > 1:
        logger.info(f"Multiple devices — using first: {model} ({serial})")
    else:
        logger.info(f"USB device ready: {model} ({serial})")
    return serial


def main():
    logger.info("=== AFAQ Phone Mirror — USB Mode ===")
    config = load_config()
    serial = get_usb_device()
    if serial is None:
        input("Press Enter to exit...")
        sys.exit(1)

    port = config.get("remote_desktop_port", 80)
    logger.info(f"Starting server on http://localhost:{port}")
    logger.info(f"  Phone view : http://localhost:{port}/phone")
    logger.info("Press Ctrl+C to stop.\n")

    start_remote_desktop(config, phone_ip=serial)


if __name__ == "__main__":
    main()
