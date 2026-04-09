from gevent import monkey
monkey.patch_all(thread=False, subprocess=False)

import io
import logging
import threading
import base64
import ctypes

# DPI awareness for correct scrcpy window capture
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import mss
import numpy as np
import pyautogui
import soundcard as sc
import qrcode
from flask import Flask, render_template, make_response, request, send_file
from flask_socketio import SocketIO
from PIL import Image

from phone_stream import (
    capture_phone_screen, send_touch, send_swipe,
    send_key as phone_send_key, send_text as phone_send_text,
    get_phone_resolution,
    start_scrcpy, stop_scrcpy, capture_scrcpy_window,
)

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

app = Flask(__name__)
app.config["SECRET_KEY"] = "remote-desktop-secret"
socketio = SocketIO(
    app, cors_allowed_origins="*", async_mode="gevent",
    max_http_buffer_size=10 * 1024 * 1024,
)

# Global config set by start_remote_desktop()
_config = {}
_screen_width = 0
_screen_height = 0
_audio_streaming = False
_phone_ip = None
_phone_streaming = False
_scrcpy_mode = False
_scrcpy_proc = None

# JS key name -> pyautogui key name
KEY_MAP = {
    "Enter": "enter", "Backspace": "backspace", "Tab": "tab",
    "Escape": "escape", "Delete": "delete", "Insert": "insert",
    "Home": "home", "End": "end", "PageUp": "pageup", "PageDown": "pagedown",
    "ArrowUp": "up", "ArrowDown": "down", "ArrowLeft": "left", "ArrowRight": "right",
    "F1": "f1", "F2": "f2", "F3": "f3", "F4": "f4", "F5": "f5", "F6": "f6",
    "F7": "f7", "F8": "f8", "F9": "f9", "F10": "f10", "F11": "f11", "F12": "f12",
    "Control": "ctrl", "Shift": "shift", "Alt": "alt", "Meta": "win",
    "CapsLock": "capslock", " ": "space",
}


def _to_abs(x_pct, y_pct):
    return int(x_pct * _screen_width), int(y_pct * _screen_height)


def _map_key(js_key):
    if js_key in KEY_MAP:
        return KEY_MAP[js_key]
    if len(js_key) == 1:
        return js_key
    return js_key.lower()


# ===== Routes =====

@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
def landing_page():
    import socket
    import json
    import urllib.request
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"
    ngrok_url = ""
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2)
        data = json.loads(resp.read())
        if data["tunnels"]:
            ngrok_url = data["tunnels"][0]["public_url"]
    except Exception:
        pass
    return render_template("landing.html", local_ip=local_ip, ngrok_url=ngrok_url)


@app.route("/access")
def desktop_page():
    return render_template("index.html")


@app.route("/phone")
def phone_page():
    return render_template("phone.html")


@app.route("/qr")
def qr_code():
    """Generate QR code for any URL passed as ?url= param."""
    url = request.args.get("url", request.host_url + "phone")
    img = qrcode.make(url, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# ===== PC Desktop Events =====

@socketio.on("connect")
def on_connect():
    global _audio_streaming
    logger.info("Client connected")
    socketio.start_background_task(stream_screen)
    if not _audio_streaming:
        _audio_streaming = True
        socketio.start_background_task(stream_audio)


@socketio.on("disconnect")
def on_disconnect():
    logger.info("Client disconnected")


def stream_screen():
    import numpy as np

    fps = _config.get("capture_fps", 15)
    quality = _config.get("capture_quality", 40)
    max_w = _config.get("capture_max_width", 1280)
    interval = 1.0 / fps

    sct = mss.mss()
    monitor = sct.monitors[1]
    mon_w, mon_h = monitor["width"], monitor["height"]
    step = max(1, mon_w // max_w)
    step_w = step
    step_h = step

    buf = io.BytesIO()
    while True:
        try:
            raw = sct.grab(monitor)
            # Fast numpy downsample + drop alpha channel
            arr = np.frombuffer(raw.bgra, dtype=np.uint8).reshape(mon_h, mon_w, 4)
            small = arr[::step_h, ::step_w, 2::-1]  # BGRA -> RGB via slice reversal
            img = Image.fromarray(small)

            buf.seek(0)
            buf.truncate()
            img.save(buf, format="JPEG", quality=quality, optimize=False)
            socketio.emit("frame", buf.getvalue())
            socketio.sleep(0.03)  # ~30fps cap, yield to gevent
        except Exception as e:
            logger.error(f"Screen capture error: {e}")
            socketio.sleep(1)


def stream_audio():
    sample_rate = _config.get("audio_sample_rate", 44100)
    chunk_size = _config.get("audio_chunk_size", 4096)

    try:
        speaker = sc.default_speaker()
        loopback = sc.get_microphone(speaker.id, include_loopback=True)
        logger.info(f"Audio loopback: {loopback.name} @ {sample_rate}Hz")
    except Exception as e:
        logger.error(f"Failed to open audio loopback: {e}")
        return

    try:
        with loopback.recorder(samplerate=sample_rate, channels=1) as recorder:
            while True:
                try:
                    data = recorder.record(numframes=chunk_size)
                    pcm = (data[:, 0] * 32767).astype(np.int16)
                    socketio.emit("audio", {
                        "pcm": base64.b64encode(pcm.tobytes()).decode("ascii"),
                        "rate": sample_rate,
                    })
                    socketio.sleep(0.01)
                except Exception as e:
                    logger.error(f"Audio capture error: {e}")
                    socketio.sleep(1)
    except Exception as e:
        logger.error(f"Audio recorder failed: {e}")


@socketio.on("mouse_move")
def on_mouse_move(data):
    try:
        x, y = _to_abs(data["x"], data["y"])
        pyautogui.moveTo(x, y, _pause=False)
    except Exception:
        pass


@socketio.on("mouse_click")
def on_mouse_click(data):
    try:
        x, y = _to_abs(data["x"], data["y"])
        button = data.get("button", "left")
        pyautogui.click(x, y, button=button, _pause=False)
    except Exception:
        pass


@socketio.on("mouse_dblclick")
def on_mouse_dblclick(data):
    try:
        x, y = _to_abs(data["x"], data["y"])
        pyautogui.doubleClick(x, y, _pause=False)
    except Exception:
        pass


@socketio.on("mouse_scroll")
def on_mouse_scroll(data):
    try:
        x, y = _to_abs(data["x"], data["y"])
        delta = data.get("delta", 0)
        pyautogui.scroll(delta, x, y, _pause=False)
    except Exception:
        pass


@socketio.on("key_press")
def on_key_press(data):
    try:
        key = _map_key(data["key"])
        pyautogui.press(key, _pause=False)
    except Exception:
        pass


@socketio.on("key_combo")
def on_key_combo(data):
    try:
        keys = [_map_key(k) for k in data["keys"]]
        pyautogui.hotkey(*keys, _pause=False)
    except Exception:
        pass


# ===== Phone Events =====

@socketio.on("phone_start")
def on_phone_start():
    global _phone_streaming
    if not _phone_ip:
        logger.warning("Phone stream requested but no phone IP set")
        return
    if not _phone_streaming:
        _phone_streaming = True
        res = get_phone_resolution(_phone_ip)
        if res:
            socketio.emit("phone_resolution", {"width": res[0], "height": res[1]})
        socketio.start_background_task(stream_phone)


@socketio.on("toggle_scrcpy")
def on_toggle_scrcpy():
    global _scrcpy_mode, _scrcpy_proc
    if not _phone_ip:
        return
    if not _scrcpy_mode:
        # Enable scrcpy mode
        _scrcpy_proc = start_scrcpy(_phone_ip)
        if _scrcpy_proc:
            _scrcpy_mode = True
            logger.info("Switched to scrcpy capture mode")
            socketio.emit("scrcpy_status", {"active": True})
        else:
            socketio.emit("scrcpy_status", {"active": False, "error": "scrcpy failed to start"})
    else:
        # Disable scrcpy mode, back to adb screencap
        stop_scrcpy(_scrcpy_proc)
        _scrcpy_proc = None
        _scrcpy_mode = False
        logger.info("Switched back to ADB screencap mode")
        socketio.emit("scrcpy_status", {"active": False})


def stream_phone():
    global _phone_streaming
    quality = _config.get("phone_quality", 30)
    max_w = _config.get("phone_max_width", 540)
    fps = _config.get("phone_fps", 5)
    interval = 1.0 / fps

    while _phone_streaming and _phone_ip:
        try:
            img = None

            if _scrcpy_mode:
                # Capture from scrcpy window
                img = capture_scrcpy_window()
            else:
                # Capture via ADB screencap
                png_data = capture_phone_screen(_phone_ip)
                if png_data:
                    img = Image.open(io.BytesIO(png_data)).convert("RGB")

            if img:
                w, h = img.size
                if w > max_w:
                    ratio = max_w / w
                    img = img.resize((max_w, int(h * ratio)), Image.BILINEAR)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality, optimize=False)
                socketio.emit("phone_frame", buf.getvalue())

            socketio.sleep(0.1 if _scrcpy_mode else interval)
        except Exception as e:
            logger.error(f"Phone stream error: {e}")
            socketio.sleep(1)


@socketio.on("phone_tap")
def on_phone_tap(data):
    if _phone_ip:
        send_touch(_phone_ip, data["x"], data["y"])


@socketio.on("phone_swipe")
def on_phone_swipe(data):
    if _phone_ip:
        send_swipe(_phone_ip, data["x1"], data["y1"],
                   data["x2"], data["y2"], data.get("duration", 300))


@socketio.on("phone_key")
def on_phone_key(data):
    if _phone_ip:
        phone_send_key(_phone_ip, data["keycode"])


@socketio.on("phone_text")
def on_phone_text(data):
    if _phone_ip:
        phone_send_text(_phone_ip, data["text"])


# ===== Start =====

def start_remote_desktop(config, phone_ip=None):
    """Start the remote desktop Flask-SocketIO server (blocking)."""
    global _config, _screen_width, _screen_height, _phone_ip
    _config = config
    _phone_ip = phone_ip
    port = config.get("remote_desktop_port", 80)

    with mss.mss() as sct:
        mon = sct.monitors[1]
        _screen_width = mon["width"]
        _screen_height = mon["height"]

    logger.info(f"Remote desktop on port {port} (screen: {_screen_width}x{_screen_height})")
    if phone_ip:
        logger.info(f"Phone streaming enabled for {phone_ip}")
    socketio.run(app, host="0.0.0.0", port=port, log_output=False)
