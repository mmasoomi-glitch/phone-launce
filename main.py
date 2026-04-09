import json
import time
import threading
import logging
import sys
import os
import tempfile
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

from monitor import scan_network, is_phone_present, get_phone_ip
from notifier import send_notification
from remote_desktop import start_remote_desktop
from tunnel import start_ngrok, stop_ngrok, get_ngrok_url
from phone_stream import connect_adb_wifi, disconnect_adb

# --- Logging setup ---
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.log")
handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler()])
logger = logging.getLogger("main")


def load_config():
    """Load settings from config.json + secrets from .env"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(base_dir, ".env"))

    config_path = os.path.join(base_dir, "config.json")
    with open(config_path) as f:
        config = json.load(f)

    # Merge secrets from .env
    config["phone_mac"] = os.getenv("PHONE_MAC", "AA:BB:CC:DD:EE:FF")
    config["gmail_sender"] = os.getenv("GMAIL_SENDER", "")
    config["gmail_app_password"] = os.getenv("GMAIL_APP_PASSWORD", "")
    config["gmail_recipient"] = os.getenv("GMAIL_RECIPIENT", "")
    config["ngrok_url"] = os.getenv("NGROK_URL", "afaq24.store.ngrok.pizza")
    return config


def acquire_lock():
    """Single-instance guard using a lockfile."""
    lock_path = os.path.join(tempfile.gettempdir(), "phone_detect_remote.lock")
    try:
        if os.path.exists(lock_path):
            with open(lock_path) as f:
                old_pid = int(f.read().strip())
            # Check if that process is still running
            try:
                os.kill(old_pid, 0)
                logger.error(f"Another instance is running (PID {old_pid}). Exiting.")
                sys.exit(1)
            except OSError:
                pass  # Old process is dead, safe to continue

        with open(lock_path, "w") as f:
            f.write(str(os.getpid()))
        return lock_path
    except Exception as e:
        logger.error(f"Lock error: {e}")
        sys.exit(1)


def release_lock(lock_path):
    try:
        os.remove(lock_path)
    except Exception:
        pass


def main():
    lock_path = acquire_lock()
    logger.info("Phone Detect Remote Desktop starting...")

    try:
        config = load_config()
        logger.info(f"Monitoring for MAC: {config['phone_mac']} on subnet {config['subnet']}.0/24")

        phone_present = False
        ngrok_proc = None

        while True:
            try:
                arp_table = scan_network(config["subnet"])
                now_present = is_phone_present(arp_table, config["phone_mac"])

                if now_present and not phone_present:
                    phone_ip = get_phone_ip(arp_table, config["phone_mac"])
                    logger.info(f"Phone CONNECTED at {phone_ip}")

                    # 1. Connect ADB over WiFi for phone screen
                    adb_ok = connect_adb_wifi(phone_ip)
                    if adb_ok:
                        logger.info(f"ADB WiFi connected to {phone_ip}")
                    else:
                        logger.warning(f"ADB WiFi connection failed for {phone_ip}")

                    # 2. Start remote desktop server with phone IP (daemon thread)
                    desktop_thread = threading.Thread(
                        target=start_remote_desktop,
                        args=(config, phone_ip if adb_ok else None),
                        daemon=True,
                    )
                    desktop_thread.start()

                    # 3. Start ngrok tunnel (give Flask a moment to bind)
                    time.sleep(2)
                    ngrok_proc = start_ngrok(config)

                    # 4. Send email with the ngrok URL
                    public_url = get_ngrok_url(ngrok_proc)
                    config["_ngrok_url"] = public_url or ""
                    threading.Thread(
                        target=send_notification,
                        args=(config, phone_ip, public_url),
                        daemon=True,
                    ).start()

                    logger.info(f"All services started.")
                    logger.info(f"  PC Desktop: {public_url}/access")
                    logger.info(f"  Phone:      {public_url}/phone")

                elif not now_present and phone_present:
                    logger.info("Phone DISCONNECTED")
                    disconnect_adb(phone_ip)
                    if ngrok_proc:
                        stop_ngrok(ngrok_proc)
                        ngrok_proc = None

                phone_present = now_present

            except Exception as e:
                logger.error(f"Scan loop error: {e}")

            time.sleep(config["scan_interval_seconds"])

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        if ngrok_proc:
            stop_ngrok(ngrok_proc)
        release_lock(lock_path)
        logger.info("Stopped.")


if __name__ == "__main__":
    main()
