"""Placeholder alert action, triggered when the two-tone page is detected.

Swap the body of `trigger_alert` for whatever the real response should be
later (lights, SMS, siren relay, etc). For now it just wakes a sleeping
macOS user up: volume to max, then loop a loud system sound until the
configured max duration elapses or a stop-file appears.
"""
import os
import subprocess
import threading
import time

STOP_FILE = "ALERT_STOP"
SOUND_FILE = "/System/Library/Sounds/Sosumi.aiff"

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


def _blare(max_alert_sec: float, repeat_sec: float, log):
    try:
        deadline = time.monotonic() + max_alert_sec
        if os.path.exists(STOP_FILE):
            os.remove(STOP_FILE)

        while time.monotonic() < deadline:
            if os.path.exists(STOP_FILE):
                log("Alert silenced via stop file.")
                os.remove(STOP_FILE)
                break
            try:
                subprocess.run(["afplay", SOUND_FILE], check=False)
            except OSError as exc:
                log(f"Could not play alert sound (afplay unavailable?): {exc!r}")
                break
            time.sleep(max(0.0, repeat_sec))
    finally:
        global _alerting
        with _alert_lock:
            _alerting = False


def trigger_alert(config: dict, log=print):
    """Non-blocking: starts the alert in a background thread if one isn't already running.

    Create a file named ALERT_STOP in the working directory to silence it early.
    A failure here (e.g. running off macOS) is logged, never raised, so it can't
    take down an overnight detection run.
    """
    global _alerting
    with _alert_lock:
        if _alerting:
            log("Alert already sounding; new detection logged but not re-triggering.")
            return
        _alerting = True

    log("TWO-TONE PAGE DETECTED — triggering alert.")
    _set_mac_volume_max(log)
    threading.Thread(
        target=_blare,
        args=(config.get("max_alert_sec", 300), config.get("alert_repeat_sec", 2), log),
        daemon=True,
    ).start()
