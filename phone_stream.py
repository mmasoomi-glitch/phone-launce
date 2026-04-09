import re
import subprocess
import logging
import time
import os

logger = logging.getLogger(__name__)


# Separate scrcpy process that routes PC mic → phone (used during calls)
_mic_proc = None


def start_mic_forward(phone_ip, port=5555):
    """Forward PC microphone audio to the phone. Call this when a call starts."""
    global _mic_proc
    if _mic_proc and _mic_proc.poll() is None:
        return  # already running
    target = _adb_target(phone_ip, port)
    exe = SCRCPY_PATH if os.path.exists(SCRCPY_PATH) else "scrcpy"
    try:
        _mic_proc = subprocess.Popen(
            [
                exe, "-s", target,
                "--no-video",
                "--audio-source=mic",   # PC mic → phone speaker
                "--audio-codec=aac",
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        logger.info(f"Mic forward started for {target} (PID {_mic_proc.pid})")
    except Exception as e:
        logger.error(f"Mic forward failed: {e}")


def stop_mic_forward():
    """Stop PC mic → phone routing."""
    global _mic_proc
    if _mic_proc:
        try:
            _mic_proc.terminate()
            _mic_proc.wait(timeout=3)
        except Exception:
            pass
        _mic_proc = None
        logger.info("Mic forward stopped")


def dial_number(phone_ip, number: str, port=5555):
    """Dial a phone number via ADB intent."""
    target = _adb_target(phone_ip, port)
    clean = re.sub(r"[^\d+]", "", number)
    try:
        subprocess.run(
            ["adb", "-s", target, "shell", "am", "start",
             "-a", "android.intent.action.CALL",
             "-d", f"tel:{clean}"],
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        logger.info(f"Dialing {clean} on {target}")
        return True
    except Exception as e:
        logger.error(f"Dial failed: {e}")
        return False


def end_call(phone_ip, port=5555):
    """End the current call via ADB keyevent ENDCALL (6)."""
    target = _adb_target(phone_ip, port)
    try:
        subprocess.run(
            ["adb", "-s", target, "shell", "input", "keyevent", "6"],
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        logger.info(f"Call ended on {target}")
        return True
    except Exception as e:
        logger.error(f"End call failed: {e}")
        return False


def set_call_volume(phone_ip, level: int, port=5555):
    """Set call volume (0–15). Uses ADB media vol command."""
    target = _adb_target(phone_ip, port)
    level = max(0, min(15, level))
    try:
        subprocess.run(
            ["adb", "-s", target, "shell", "media", "volume",
             "--set", str(level), "--stream", "0"],  # stream 0 = VOICE_CALL
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        logger.error(f"Set volume failed: {e}")
        return False


def toggle_mute(phone_ip, port=5555):
    """Toggle phone microphone mute via keyevent MUTE (91)."""
    target = _adb_target(phone_ip, port)
    try:
        subprocess.run(
            ["adb", "-s", target, "shell", "input", "keyevent", "91"],
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        logger.error(f"Mute toggle failed: {e}")
        return False



def _adb_target(phone_ip, port=5555):
    """Return ADB -s target. If phone_ip has no colon it's a USB serial, use as-is."""
    if ":" in phone_ip:
        return _adb_target(phone_ip, port)
    return phone_ip  # USB serial


SCRCPY_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Microsoft", "WinGet", "Packages",
    "Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe",
    "scrcpy-win64-v3.3.4", "scrcpy.exe"
)


def connect_adb_wifi(phone_ip, port=5555):
    """Connect to Android device over WiFi via ADB."""
    target = _adb_target(phone_ip, port)
    try:
        subprocess.run(
            ["adb", "disconnect", target],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=5,
        )
        time.sleep(1)
        result = subprocess.run(
            ["adb", "connect", target],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=10,
        )
        output = result.stdout.strip()
        logger.info(f"ADB connect {target}: {output}")
        return "connected" in output.lower()
    except Exception as e:
        logger.error(f"ADB WiFi connect failed: {e}")
        return False


def disconnect_adb(phone_ip, port=5555):
    try:
        subprocess.run(
            ["adb", "disconnect", _adb_target(phone_ip, port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=5,
        )
    except Exception:
        pass


def capture_phone_screen(phone_ip, port=5555):
    """Capture phone screenshot via ADB. Returns PNG bytes or None."""
    target = _adb_target(phone_ip, port)
    try:
        result = subprocess.run(
            ["adb", "-s", target, "exec-out", "screencap", "-p"],
            capture_output=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 0 and len(result.stdout) > 100:
            return result.stdout
        return None
    except Exception as e:
        logger.error(f"Phone screencap failed: {e}")
        return None


def send_touch(phone_ip, x, y, port=5555):
    target = _adb_target(phone_ip, port)
    try:
        subprocess.Popen(
            ["adb", "-s", target, "shell", "input", "tap", str(x), str(y)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        pass


def send_swipe(phone_ip, x1, y1, x2, y2, duration_ms=300, port=5555):
    target = _adb_target(phone_ip, port)
    try:
        subprocess.Popen(
            ["adb", "-s", target, "shell", "input", "swipe",
             str(x1), str(y1), str(x2), str(y2), str(duration_ms)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        pass


def send_key(phone_ip, keycode, port=5555):
    target = _adb_target(phone_ip, port)
    try:
        subprocess.Popen(
            ["adb", "-s", target, "shell", "input", "keyevent", str(keycode)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        pass


def send_text(phone_ip, text, port=5555):
    target = _adb_target(phone_ip, port)
    try:
        escaped = text.replace(" ", "%s")
        subprocess.Popen(
            ["adb", "-s", target, "shell", "input", "text", escaped],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        pass


def get_phone_resolution(phone_ip, port=5555):
    target = _adb_target(phone_ip, port)
    try:
        result = subprocess.run(
            ["adb", "-s", target, "shell", "wm", "size"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in result.stdout.strip().split("\n"):
            if "size" in line.lower():
                parts = line.split(":")[-1].strip().split("x")
                return int(parts[0]), int(parts[1])
    except Exception as e:
        logger.error(f"Failed to get phone resolution: {e}")
    return None


# ===== Scrcpy =====

def start_scrcpy(phone_ip, port=5555, max_size=720):
    """Start scrcpy with visible window for capture. Returns Popen process."""
    target = _adb_target(phone_ip, port)
    exe = SCRCPY_PATH if os.path.exists(SCRCPY_PATH) else "scrcpy"
    try:
        proc = subprocess.Popen(
            [
                exe, "-s", target,
                # ── Audio: phone speaker → PC speakers ──
                "--audio-source=output",
                "--audio-codec=aac",
                "--audio-bit-rate=128000",
                # ── Video ──
                "--max-size", str(max_size),
                "--window-title", "ScrcpyMirror",
                "--window-borderless",
                "--always-on-top",
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        logger.info(f"scrcpy started for {target} (PID {proc.pid})")
        time.sleep(3)  # wait for window to appear
        return proc
    except Exception as e:
        logger.error(f"scrcpy start failed: {e}")
        return None


def stop_scrcpy(proc):
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
        logger.info("scrcpy stopped")
    except subprocess.TimeoutExpired:
        proc.kill()
    except Exception:
        pass


def capture_scrcpy_window():
    """Capture the scrcpy window by title. Returns PIL Image or None."""
    try:
        import ctypes
        import ctypes.wintypes
        import mss
        from PIL import Image

        # DPI awareness for correct coordinates
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

        hwnd = ctypes.windll.user32.FindWindowW(None, "ScrcpyMirror")
        if not hwnd:
            return None

        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))

        # Get screen position of client area
        point = ctypes.wintypes.POINT(0, 0)
        ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(point))

        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w < 50 or h < 50:
            return None

        with mss.mss() as sct:
            monitor = {"left": point.x, "top": point.y, "width": w, "height": h}
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            return img
    except Exception as e:
        logger.error(f"scrcpy capture failed: {e}")
        return None
