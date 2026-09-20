#!/usr/bin/env python3
"""Overnight station-code detector for a fire station.

Listens to an audio input (a mic near your scanner, or a virtual audio
cable fed from the scanner's line-out), watches for your station's known
siren codes (see config.json), and fires alert.trigger_alert() when one
is heard.

Usage:
    python3 detector.py run --config config.json
    python3 detector.py list-devices
    python3 detector.py analyze --device 2 --seconds 20
    python3 detector.py test-alert
    python3 detector.py run --config config.json --input-wav fire.wav
    python3 detector.py run --config config.json --device 2 --debug
"""
import argparse
import datetime
import json
import queue
import sys
import time
import wave
from collections import deque

import numpy as np

import alert
import codes
import dsp

BLOCK_SEC = 0.2  # ~5 Hz frequency resolution; codes hold each tone for well over a second
SAMPLE_RATE = 44100
CLASSIFY_MIN_HZ = 300
CLASSIFY_MAX_HZ = 1300  # stays below the ~1500-2000Hz harmonics real siren tones throw off


def log(message: str, log_file=None):
    line = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    if log_file:
        with open(log_file, "a") as f:
            f.write(line + "\n")


def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def build_detectors(config: dict):
    return {name: codes.build_detector(name, spec) for name, spec in config["codes"].items()}


HISTORY_SECONDS = 5.0


def run_from_stream(block_iter, sample_rate: int, config: dict, log_file=None, debug=False):
    detectors = build_detectors(config)
    min_energy = config.get("min_block_energy", 0.01)
    min_mag = config.get("min_block_magnitude", 5.0)
    min_purity = config.get("min_block_purity", 0.10)
    history = deque(maxlen=max(1, int(HISTORY_SECONDS / BLOCK_SEC)))
    block_index = 0

    for samples in block_iter:
        freq = dsp.classify_frequency(
            samples, sample_rate, CLASSIFY_MIN_HZ, CLASSIFY_MAX_HZ, min_energy, min_mag, min_purity
        )
        history.append(freq)
        if debug:
            log(f"debug t+{block_index * BLOCK_SEC:6.1f}s freq={freq}", log_file)
        for name, detector in detectors.items():
            if detector.process(freq, BLOCK_SEC):
                trail = [round(f, 1) if f is not None else None for f in history]
                log(f"Match confirmed for code '{name}'. Last {HISTORY_SECONDS:.0f}s of "
                    f"classified frequencies leading up to it: {trail}", log_file)
                alert.trigger_alert(config, code_name=name, log=lambda m: log(m, log_file))
        block_index += 1


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


def cmd_list_devices(args):
    import sounddevice as sd

    print(sd.query_devices())


def cmd_analyze(args):
    import sounddevice as sd

    block_size = int(SAMPLE_RATE * BLOCK_SEC)
    print(f"Listening for {args.seconds}s, reporting the strongest tone per block...")
    print("Use this to figure out an unknown station code's frequencies from a real recording.")

    def callback(indata, frames, time_info, status):
        freq, mag = dsp.dominant_frequency(indata[:, 0], SAMPLE_RATE, CLASSIFY_MIN_HZ, CLASSIFY_MAX_HZ)
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
    config = load_config(args.config) if args.config else {}
    print(f"Triggering placeholder alert now for code {args.code!r} (volume to max + its tone x2)...")
    thread = alert.trigger_alert(config, code_name=args.code)
    if thread:
        thread.join()


def cmd_run(args):
    config = load_config(args.config)
    log(f"Starting overnight detector for codes: {list(config['codes'])}", args.log_file)
    try:
        if args.input_wav:
            run_from_stream(wav_block_iter(args.input_wav), SAMPLE_RATE, config, args.log_file, debug=args.debug)
        else:
            run_from_stream(mic_block_iter(args.device), SAMPLE_RATE, config, args.log_file, debug=args.debug)
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
    p_run.add_argument("--debug", action="store_true",
                        help="Log every block's classified frequency, not just triggers (verbose; useful for tuning)")
    p_run.set_defaults(func=cmd_run)

    p_list = sub.add_parser("list-devices", help="List audio input devices")
    p_list.set_defaults(func=cmd_list_devices)

    p_analyze = sub.add_parser("analyze", help="Print dominant frequency per block, to identify an unknown code")
    p_analyze.add_argument("--device", type=int, default=None)
    p_analyze.add_argument("--seconds", type=float, default=15)
    p_analyze.set_defaults(func=cmd_analyze)

    p_test = sub.add_parser("test-alert", help="Fire the placeholder alert immediately, to sanity-check audio/volume")
    p_test.add_argument("--config", default=None)
    p_test.add_argument("--code", default="test")
    p_test.set_defaults(func=cmd_test_alert)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
