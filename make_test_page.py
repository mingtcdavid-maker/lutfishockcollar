#!/usr/bin/env python3
"""Generate a synthetic WAV for one configured code, to test new/hypothetical
codes without needing a real recording (samples/ + test_samples.py already
cover the fire and ambulance codes this was built for).

    python3 make_test_page.py --config config.example.json --code fire --out fire_synthetic.wav
    python3 detector.py run --config config.example.json --input-wav fire_synthetic.wav
"""
import argparse
import json
import wave

import numpy as np

SAMPLE_RATE = 44100


def tone(freq, seconds, sample_rate=SAMPLE_RATE, amplitude=0.6, modulate=False):
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    wave_ = amplitude * np.sin(2 * np.pi * freq * t)
    if modulate:
        wave_ *= 0.6 + 0.4 * np.sin(2 * np.pi * 3.0 * t)  # mimics a pulsing/yelp siren
    return wave_


def silence(seconds, sample_rate=SAMPLE_RATE):
    return np.zeros(int(sample_rate * seconds))


def build_alternating(spec):
    a_dur = spec["min_hold_sec"] + 0.5
    b_dur = spec["min_hold_sec"] + 0.4
    cycle = [tone(spec["freq_a_hz"], a_dur), tone(spec["freq_b_hz"], b_dur)]
    return np.concatenate([silence(1.0)] + cycle * (spec["min_alternations"] + 1) + [silence(1.0)])


def build_sustained(spec):
    duration = spec["min_duration_sec"] + 1.0
    return np.concatenate([silence(1.0), tone(spec["freq_hz"], duration, modulate=True), silence(1.0)])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--code", required=True, help="Name of a code in the config's \"codes\" map")
    parser.add_argument("--out", default="synthetic.wav")
    parser.add_argument("--noise", type=float, default=0.02, help="Amount of background noise to mix in")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)
    spec = config["codes"][args.code]

    if spec["type"] == "alternating":
        signal = build_alternating(spec)
    elif spec["type"] == "sustained":
        signal = build_sustained(spec)
    else:
        raise ValueError(f"Unknown code type: {spec['type']!r}")

    signal = signal + np.random.normal(0, args.noise, size=signal.shape)
    signal = np.clip(signal, -1.0, 1.0)

    pcm = (signal * 32767).astype(np.int16)
    with wave.open(args.out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())

    print(f"Wrote {args.out} for code {args.code!r} ({spec['type']})")


if __name__ == "__main__":
    main()
