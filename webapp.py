#!/usr/bin/env python3
"""Local control panel for the overnight station-code detector.

Runs a small Flask server, bound to localhost only, that lets you start/stop
detector.py, silence an active alert, and test the alarm volume from a
browser instead of the command line.

    pip install -r requirements.txt
    cp config.example.json config.json   # if you haven't already
    python3 webapp.py
    # open http://127.0.0.1:8765
"""
import json
import os
import shutil
import subprocess
import sys
import threading

from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
CONFIG_EXAMPLE_PATH = os.path.join(BASE_DIR, "config.example.json")
LOG_PATH = os.path.join(BASE_DIR, "overnight.log")
STOP_FILE_PATH = os.path.join(BASE_DIR, "ALERT_STOP")
LOG_TAIL_LINES = 40

app = Flask(__name__, static_folder=None)

_process_lock = threading.Lock()
_process = None  # subprocess.Popen | None


def ensure_config():
    if not os.path.exists(CONFIG_PATH) and os.path.exists(CONFIG_EXAMPLE_PATH):
        shutil.copy(CONFIG_EXAMPLE_PATH, CONFIG_PATH)


def load_config():
    ensure_config()
    with open(CONFIG_PATH) as f:
        return json.load(f)


def tail_log(n=LOG_TAIL_LINES):
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH) as f:
        lines = f.readlines()
    return [line.rstrip("\n") for line in lines[-n:]]


@app.route("/")
def index():
    return send_from_directory(os.path.join(BASE_DIR, "web"), "index.html")


@app.route("/api/config")
def api_config():
    config = load_config()
    return jsonify({"codes": list(config.get("codes", {}))})


@app.route("/api/devices")
def api_devices():
    try:
        import sounddevice as sd
        devices = [
            {"index": i, "name": d["name"]}
            for i, d in enumerate(sd.query_devices())
            if d.get("max_input_channels", 0) > 0
        ]
        return jsonify({"devices": devices})
    except Exception as exc:
        return jsonify({"devices": [], "error": str(exc)})


@app.route("/api/status")
def api_status():
    with _process_lock:
        running = _process is not None and _process.poll() is None
        pid = _process.pid if running else None
    return jsonify({"running": running, "pid": pid, "log_tail": tail_log()})


@app.route("/api/start", methods=["POST"])
def api_start():
    global _process
    body = request.get_json(silent=True) or {}
    device = body.get("device")

    with _process_lock:
        if _process is not None and _process.poll() is None:
            return jsonify({"error": "Detector is already running."}), 409

        ensure_config()
        cmd = [sys.executable, os.path.join(BASE_DIR, "detector.py"), "run",
               "--config", CONFIG_PATH, "--log-file", LOG_PATH]
        if device is not None:
            try:
                cmd += ["--device", str(int(device))]
            except (TypeError, ValueError):
                return jsonify({"error": f"Invalid device: {device!r}"}), 400

        _process = subprocess.Popen(cmd, cwd=BASE_DIR)
        return jsonify({"status": "started", "pid": _process.pid})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    global _process
    with _process_lock:
        if _process is None or _process.poll() is not None:
            _process = None
            return jsonify({"status": "not_running"})
        _process.terminate()
        try:
            _process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _process.kill()
            _process.wait(timeout=5)
        _process = None
        return jsonify({"status": "stopped"})


@app.route("/api/silence", methods=["POST"])
def api_silence():
    with open(STOP_FILE_PATH, "w"):
        pass
    return jsonify({"status": "silenced"})


@app.route("/api/test-alert", methods=["POST"])
def api_test_alert():
    body = request.get_json(silent=True) or {}
    code = body.get("code", "")
    known_codes = set(load_config().get("codes", {}))
    if code not in known_codes:
        return jsonify({"error": f"Unknown code {code!r}. Known codes: {sorted(known_codes)}"}), 400

    subprocess.Popen(
        [sys.executable, os.path.join(BASE_DIR, "detector.py"), "test-alert",
         "--config", CONFIG_PATH, "--code", code],
        cwd=BASE_DIR,
    )
    return jsonify({"status": "testing", "code": code})


if __name__ == "__main__":
    ensure_config()
    app.run(host="127.0.0.1", port=8765, debug=False)
