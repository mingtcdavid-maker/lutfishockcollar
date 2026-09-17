#!/usr/bin/env python3
"""Overnight two-tone sequential page detector for a fire station.

Listens to an audio input (a mic near your scanner, or a virtual audio
cable fed from the scanner's line-out), watches for your station's
two-tone sequential page, and fires alert.trigger_alert() when it's heard.

Usage:
    python3 detector.py run --config config.json
    python3 detector.py list-devices
    python3 detector.py analyze --device 2 --seconds 20
    python3 detector.py test-alert
    python3 detector.py run --config config.json --input-wav sample_page.wav
"""
import argparse
import datetime
import json
import queue
import sys
import time
import wave

import numpy as np

import alert
import dsp

BLOCK_SEC = 0.2  # ~5 Hz frequency resolution; tones are held for >=1s so this is responsive enough
SAMPLE_RATE = 44100


def log(message: str, log_file=None):
    line = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    if log_file:
        with open(log_file, "a") as f:
            f.write(line + "\n")


def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


class TwoToneStateMachine:
    """IDLE -> tone A held long enough -> WAITING_B -> tone B held long enough -> TRIGGER."""

    IDLE, GOT_A, GOT_B = "idle", "got_a", "got_b"

    def __init__(self, config: dict):
        self.config = config
        self.state = self.IDLE
        self.a_duration = 0.0
        self.b_duration = 0.0
        self.time_since_relevant_tone = 0.0
        self.cooldown_remaining = 0.0

    def _reset(self):
        self.state = self.IDLE
        self.a_duration = 0.0
        self.b_duration = 0.0
        self.time_since_relevant_tone = 0.0

    def process_block(self, tone_label, block_dur: float) -> bool:
        """tone_label is 'A', 'B', or None for this block. Returns True on trigger."""
        cfg = self.config
        if self.cooldown_remaining > 0:
            self.cooldown_remaining -= block_dur
            return False

        if self.state == self.IDLE:
            if tone_label == "A":
                self.a_duration += block_dur
                if self.a_duration >= cfg["min_tone_duration_sec"]:
                    self.state = self.GOT_A
                    self.time_since_relevant_tone = 0.0
            else:
                self.a_duration = 0.0

        elif self.state == self.GOT_A:
            if tone_label == "B":
                self.b_duration += block_dur
                self.time_since_relevant_tone = 0.0
                if self.b_duration >= cfg["min_tone_duration_sec"]:
                    self.cooldown_remaining = cfg["cooldown_sec"]
                    self._reset()
                    return True
            elif tone_label == "A":
                self.time_since_relevant_tone = 0.0
            else:
                self.time_since_relevant_tone += block_dur
                if self.time_since_relevant_tone > cfg["max_gap_sec"]:
                    self._reset()

        return False


def classify_block(samples: np.ndarray, sample_rate: int, config: dict):
    energy = dsp.rms(samples)
    if energy < 1e-6:
        return None
    mag_a = dsp.goertzel_magnitude(samples, sample_rate, config["tone_a_hz"])
    mag_b = dsp.goertzel_magnitude(samples, sample_rate, config["tone_b_hz"])
    ratio_a = mag_a / energy
    ratio_b = mag_b / energy
    threshold = config["detection_threshold"]
    if ratio_a > threshold and ratio_a >= ratio_b:
        return "A"
    if ratio_b > threshold and ratio_b > ratio_a:
        return "B"
    return None


def run_from_stream(block_iter, sample_rate: int, config: dict, log_file=None):
    machine = TwoToneStateMachine(config)
    block_dur = BLOCK_SEC
    for samples in block_iter:
        label = classify_block(samples, sample_rate, config)
        if machine.process_block(label, block_dur):
            log("Two-tone match confirmed.", log_file)
            alert.trigger_alert(config, log=lambda m: log(m, log_file))


def mic_block_iter(device):
    import sounddevice as sd

    block_size = int(SAMPLE_RATE * BLOCK_SEC)
    q: "queue.Queue[np.ndarray]" = queue.Queue()

    def callback(indata, frames, time_info, status):
        if status:
            pass  # dropped frames are logged implicitly by gaps in detection; not fatal overnight
        q.put(indata[:, 0].copy())

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        blocksize=block_size,
        channels=1,
        dtype="float32",
        device=device,
        callback=callback,
    ):
        while True:
            yield q.get()


def wav_block_iter(path: str):
    with wave.open(path, "rb") as wf:
        sample_rate = wf.getframerate()
        block_size = int(sample_rate * BLOCK_SEC)
        sampwidth = wf.getsampwidth()
        dtype = {1: np.int8, 2: np.int16, 4: np.int32}[sampwidth]
        max_val = float(2 ** (8 * sampwidth - 1))
        n_channels = wf.getnchannels()
        while True:
            raw = wf.readframes(block_size)
            if not raw:
                break
            data = np.frombuffer(raw, dtype=dtype).astype(np.float32) / max_val
            if n_channels > 1:
                data = data.reshape(-1, n_channels).mean(axis=1)
            yield data
    return sample_rate


def cmd_list_devices(args):
    import sounddevice as sd

    print(sd.query_devices())


def cmd_analyze(args):
    import sounddevice as sd

    block_size = int(SAMPLE_RATE * BLOCK_SEC)
    print(f"Listening for {args.seconds}s, reporting the strongest tone per block...")
    print("Use this to figure out your station's actual two-tone frequencies from a real page.")

    def callback(indata, frames, time_info, status):
        freq, mag = dsp.dominant_frequency(indata[:, 0], SAMPLE_RATE)
        if freq and mag > 1.0:
            print(f"{time.strftime('%H:%M:%S')}  peak ~{freq:6.1f} Hz  strength {mag:8.1f}")

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        blocksize=block_size,
        channels=1,
        dtype="float32",
        device=args.device,
        callback=callback,
    ):
        time.sleep(args.seconds)


def cmd_test_alert(args):
    config = load_config(args.config) if args.config else {"max_alert_sec": 10, "alert_repeat_sec": 2}
    print("Triggering placeholder alert now (volume to max + repeating sound)...")
    alert.trigger_alert(config)
    time.sleep(config.get("max_alert_sec", 10) + 1)


def cmd_run(args):
    config = load_config(args.config)
    log(f"Starting overnight two-tone detector with config: {config}", args.log_file)
    try:
        if args.input_wav:
            run_from_stream(wav_block_iter(args.input_wav), SAMPLE_RATE, config, args.log_file)
        else:
            run_from_stream(mic_block_iter(args.device), SAMPLE_RATE, config, args.log_file)
    except KeyboardInterrupt:
        log("Stopped by user.", args.log_file)
    except Exception as exc:  # keep this alive overnight; log and let the caller decide whether to restart
        log(f"Detector crashed: {exc!r}", args.log_file)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run the overnight detector")
    p_run.add_argument("--config", required=True)
    p_run.add_argument("--device", type=int, default=None, help="Input device index (see list-devices)")
    p_run.add_argument("--input-wav", default=None, help="Run against a WAV file instead of live mic (for testing)")
    p_run.add_argument("--log-file", default=None)
    p_run.set_defaults(func=cmd_run)

    p_list = sub.add_parser("list-devices", help="List audio input devices")
    p_list.set_defaults(func=cmd_list_devices)

    p_analyze = sub.add_parser("analyze", help="Print dominant frequency per block, to identify unknown tones")
    p_analyze.add_argument("--device", type=int, default=None)
    p_analyze.add_argument("--seconds", type=float, default=15)
    p_analyze.set_defaults(func=cmd_analyze)

    p_test = sub.add_parser("test-alert", help="Fire the placeholder alert immediately, to sanity-check audio/volume")
    p_test.add_argument("--config", default=None)
    p_test.set_defaults(func=cmd_test_alert)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
