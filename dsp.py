"""Signal-processing helpers for siren/tone-code classification."""
import numpy as np


def rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(samples))) + 1e-12)


def dominant_frequency(samples: np.ndarray, sample_rate: int, min_hz: float = 200, max_hz: float = 3000):
    """FFT peak-finder: the strongest frequency component in [min_hz, max_hz]. Used by --analyze."""
    freq, mag, _purity = spectral_peak(samples, sample_rate, min_hz, max_hz)
    return freq, mag


def spectral_peak(samples: np.ndarray, sample_rate: int, min_hz: float, max_hz: float):
    """(freq, magnitude, purity) of the strongest in-band frequency component.

    purity = peak magnitude / total in-band magnitude. A real tone concentrates
    energy in a few adjacent bins (purity well above ~0.1 in practice); broadband
    noise (voices, TV, appliance hum) spreads it across the whole band instead.
    """
    windowed = samples * np.hanning(len(samples))
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(len(samples), d=1.0 / sample_rate)
    mask = (freqs >= min_hz) & (freqs <= max_hz)
    if not np.any(mask):
        return None, 0.0, 0.0
    sub_freqs = freqs[mask]
    sub_spectrum = spectrum[mask]
    peak_idx = int(np.argmax(sub_spectrum))
    total = float(np.sum(sub_spectrum)) + 1e-12
    return float(sub_freqs[peak_idx]), float(sub_spectrum[peak_idx]), float(sub_spectrum[peak_idx] / total)


def classify_frequency(samples: np.ndarray, sample_rate: int, min_hz: float, max_hz: float,
                        min_energy: float, min_mag: float, min_purity: float):
    """Dominant frequency in-band for this block, or None if it's too quiet or not tonal enough to trust.

    Siren fundamentals live well below their own harmonics, so callers should keep
    max_hz below the lowest harmonic they care about excluding (see config comments).
    """
    energy = rms(samples)
    if energy < min_energy:
        return None
    freq, mag, purity = spectral_peak(samples, sample_rate, min_hz, max_hz)
    if freq is None or mag < min_mag or purity < min_purity:
        return None
    return freq
