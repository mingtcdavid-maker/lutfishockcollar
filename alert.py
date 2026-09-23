"""Placeholder alert action, triggered when a station code is detected.

Swap the body of `trigger_alert` for whatever the real response should be
later (lights, SMS, a relay board, etc). For now it wakes a sleeping macOS
user up: volume to max, then plays that same code's own tone twice.

Playing the code's own recorded tone (rather than a generic klaxon) is
deliberate: a false positive is short and immediately recognizable as "oh,
that's just the fire tone" — nobody needs to get up to silence it, it just
finishes on its own after two plays. A real positive is exactly as
recognizable, just at 2am.
"""
import os
import subprocess
import threading
import time

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOP_FILE = os.path.join(_BASE_DIR, "ALERT_STOP")
SOUND_FILES = {
    "fire": os.path.join(_BASE_DIR, "sounds", "fire_alert.mp3"),
    "ambulance": os.path.join(_BASE_DIR, "sounds", "ambulance_alert.mp3"),
}
DEFAULT_SOUND_FILE = "/System/Library/Sounds/Sosumi.aiff"  # fallback for an unrecognized code name

_alert_lock = threading.Lock()
_alerting = False


def _set_mac_volume_max(log):
    try:
        subprocess.run(
            ["osascript", "-e", "set volume output volume 100", "-e", "set volume output muted false"],
            check=False,
        )
    except OSError as exc:
        log(f"Could not set volume (osascript unavailable?): {exc!r}")


def _blare(sound_file: str, repeat_count: int, repeat_gap_sec: float, log):
    try:
        if os.path.exists(STOP_FILE):
            os.remove(STOP_FILE)

        for play_num in range(repeat_count):
            if os.path.exists(STOP_FILE):
                log("Alert silenced via stop file.")
                os.remove(STOP_FILE)
                break
            try:
                subprocess.run(["afplay", sound_file], check=False)
            except OSError as exc:
                log(f"Could not play alert sound (afplay unavailable?): {exc!r}")
                break
            is_last_play = play_num == repeat_count - 1
            if not is_last_play:
                stopped = _wait_or_stop(repeat_gap_sec)
                if stopped:
                    log("Alert silenced via stop file.")
                    break
    finally:
        global _alerting
        with _alert_lock:
            _alerting = False


def _wait_or_stop(seconds: float) -> bool:
    """Sleeps up to `seconds`, checking for the stop file every 0.2s. Returns True if stopped."""
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        if os.path.exists(STOP_FILE):
            os.remove(STOP_FILE)
            return True
        time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
    return False


def trigger_alert(config: dict, code_name: str = "unknown", log=print):
    """Non-blocking: starts the alert in a background thread if one isn't already running.

    Returns the background thread (for callers that want to wait on it, e.g. test-alert),
    or None if an alert was already sounding.

    Create a file at STOP_FILE (ALERT_STOP next to this script) to silence it early.
    A failure here (e.g. running off macOS) is logged, never raised, so it can't
    take down an overnight detection run.
    """
    global _alerting
    with _alert_lock:
        if _alerting:
            log(f"Alert already sounding; '{code_name}' detection logged but not re-triggering.")
            return None
        _alerting = True

    sound_file = SOUND_FILES.get(code_name, DEFAULT_SOUND_FILE)
    repeat_count = config.get("alert_repeat_count", 2)
    log(f"CODE DETECTED: {code_name!r} — playing its tone {repeat_count}x.")
    _set_mac_volume_max(log)
    thread = threading.Thread(
        target=_blare,
        args=(sound_file, repeat_count, config.get("alert_repeat_gap_sec", 1.0), log),
        daemon=True,
    )
    thread.start()
    return thread
