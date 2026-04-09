import subprocess
import logging
import time
import json
import urllib.request

logger = logging.getLogger(__name__)


def start_ngrok(config):
    """Start ngrok tunnel with random URL. Returns the Popen process."""
    port = str(config["remote_desktop_port"])
    cmd = ["ngrok", "http", port]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        logger.info(f"ngrok started on localhost:{port}")

        # Retry fetching the public URL from ngrok API
        public_url = None
        for attempt in range(10):
            time.sleep(2)
            try:
                resp = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels")
                data = json.loads(resp.read())
                if data["tunnels"]:
                    public_url = data["tunnels"][0]["public_url"]
                    logger.info(f"ngrok public URL: {public_url}/access")
                    break
            except Exception:
                pass
            logger.info(f"Waiting for ngrok tunnel... (attempt {attempt + 1}/10)")

        if not public_url:
            logger.warning("Could not fetch ngrok URL after retries")
        proc._public_url = public_url

        return proc
    except FileNotFoundError:
        logger.error("ngrok not found. Make sure it's installed and in PATH.")
        return None
    except Exception as e:
        logger.error(f"Failed to start ngrok: {e}")
        return None


def get_ngrok_url(proc):
    """Get the public URL from a running ngrok process."""
    return getattr(proc, "_public_url", None) if proc else None


def stop_ngrok(proc):
    """Stop the ngrok process."""
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
        logger.info("ngrok stopped.")
    except subprocess.TimeoutExpired:
        proc.kill()
        logger.warning("ngrok force-killed.")
    except Exception as e:
        logger.error(f"Error stopping ngrok: {e}")
