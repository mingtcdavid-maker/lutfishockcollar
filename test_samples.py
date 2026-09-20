#!/usr/bin/env python3
"""Regression test: run the detector against the two known-good reference
recordings in samples/ and confirm each triggers its own code and nothing else.

    python3 test_samples.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import detector

CONFIG = detector.load_config(str(Path(__file__).parent / "config.example.json"))
SAMPLES = Path(__file__).parent / "samples"


def convert_to_wav(src: Path, dst: Path):
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ac", "1", "-ar", str(detector.SAMPLE_RATE), str(dst)],
        check=True,
        capture_output=True,
    )


def triggered_codes(wav_path: Path):
    import dsp

    detectors = detector.build_detectors(CONFIG)
    min_energy = CONFIG.get("min_block_energy", 0.01)
    min_mag = CONFIG.get("min_block_magnitude", 5.0)
    min_purity = CONFIG.get("min_block_purity", 0.10)
    fired = set()
    for samples in detector.wav_block_iter(str(wav_path)):
        freq = dsp.classify_frequency(
            samples, detector.SAMPLE_RATE, detector.CLASSIFY_MIN_HZ, detector.CLASSIFY_MAX_HZ,
            min_energy, min_mag, min_purity,
        )
        for name, det in detectors.items():
            if det.process(freq, detector.BLOCK_SEC):
                fired.add(name)
    return fired


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cases = [("fire.mp3", "fire"), ("ambulance.mp4", "ambulance")]
        ok = True
        for filename, expected in cases:
            wav_path = tmp / (filename + ".wav")
            convert_to_wav(SAMPLES / filename, wav_path)
            fired = triggered_codes(wav_path)
            passed = fired == {expected}
            ok &= passed
            status = "PASS" if passed else "FAIL"
            print(f"[{status}] {filename}: expected {{{expected!r}}}, got {fired!r}")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
