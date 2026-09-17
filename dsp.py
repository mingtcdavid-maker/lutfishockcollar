"""Signal-processing helpers for two-tone sequential page detection."""
import numpy as np


def goertzel_magnitude(samples: np.ndarray, sample_rate: int, target_freq: float) -> float:
    """Energy at target_freq in `samples`, via the Goertzel algorithm."""
    n = len(samples)
    k = int(0.5 + n * target_freq / sample_rate)
    omega = 2 * np.pi * k / n
    coeff = 2 * np.cos(omega)

    s_prev = 0.0
    s_prev2 = 0.0
    for sample in samples:
        s = sample + coeff * s_prev - s_prev2
        s_prev2 = s_prev
        s_prev = s

    power = s_prev2 ** 2 + s_prev ** 2 - coeff * s_prev * s_prev2
    return float(np.sqrt(max(power, 0.0)) / n)


def rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(samples))) + 1e-12)


def dominant_frequency(samples: np.ndarray, sample_rate: int, min_hz: float = 200, max_hz: float = 3000):
    """Rough FFT peak-finder, used only by --analyze to help identify unknown tone frequencies."""
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
