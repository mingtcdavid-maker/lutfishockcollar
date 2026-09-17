#!/usr/bin/env python3
"""Generate a synthetic two-tone page WAV, to test the detector without real audio hardware.

    python3 make_test_page.py --config config.example.json --out sample_page.wav
    python3 detector.py run --config config.example.json --input-wav sample_page.wav
"""
import argparse
import json
import wave

import numpy as np

SAMPLE_RATE = 44100


def tone(freq, seconds, sample_rate=SAMPLE_RATE, amplitude=0.6):
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    return amplitude * np.sin(2 * np.pi * freq * t)


def silence(seconds, sample_rate=SAMPLE_RATE):
    return np.zeros(int(sample_rate * seconds))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", default="sample_page.wav")
    parser.add_argument("--noise", type=float, default=0.02, help="Amount of background noise to mix in")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    a_dur = config["min_tone_duration_sec"] + 0.5
    b_dur = config["min_tone_duration_sec"] + 1.5

    signal = np.concatenate([
        silence(2.0),
        tone(config["tone_a_hz"], a_dur),
        tone(config["tone_b_hz"], b_dur),
        silence(2.0),
    ])
    signal = signal + np.random.normal(0, args.noise, size=signal.shape)
    signal = np.clip(signal, -1.0, 1.0)

    pcm = (signal * 32767).astype(np.int16)
    with wave.open(args.out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())

    print(f"Wrote {args.out}: silence -> {config['tone_a_hz']}Hz x{a_dur:.1f}s -> "
          f"{config['tone_b_hz']}Hz x{b_dur:.1f}s -> silence")


if __name__ == "__main__":
    main()
