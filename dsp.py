"""Signal-processing helpers for siren/tone-code classification."""
import numpy as np


def rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(samples))) + 1e-12)


def dominant_frequency(samples: np.ndarray, sample_rate: int, min_hz: float = 200, max_hz: float = 3000):
    """FFT peak-finder: the strongest frequency component in [min_hz, max_hz]."""
    windowed = samples * np.hanning(len(samples))
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(len(samples), d=1.0 / sample_rate)
    mask = (freqs >= min_hz) & (freqs <= max_hz)
    if not np.any(mask):
        return None, 0.0
    sub_freqs = freqs[mask]
    sub_spectrum = spectrum[mask]
    peak_idx = int(np.argmax(sub_spectrum))
    return float(sub_freqs[peak_idx]), float(sub_spectrum[peak_idx])


def classify_frequency(samples: np.ndarray, sample_rate: int, min_hz: float, max_hz: float,
                        min_energy: float, min_mag: float):
    """Dominant frequency in-band for this block, or None if the block is too quiet to trust.

    Siren fundamentals live well below their own harmonics, so callers should keep
    max_hz below the lowest harmonic they care about excluding (see config comments).
    """
    energy = rms(samples)
    if energy < min_energy:
        return None
    freq, mag = dominant_frequency(samples, sample_rate, min_hz, max_hz)
    if freq is None or mag < min_mag:
        return None
    return freq
