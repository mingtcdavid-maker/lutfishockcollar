"""Per-code detection state machines.

Real station tones aren't sequential two-tone pages (tone A once, then tone B
once) — they're sirens. Two shapes cover the two codes this was built for:

- "alternating": a hi-lo warble, e.g. a fire turnout alarm switching between
  two fixed frequencies on a beat.
- "sustained": a single frequency held for a while, e.g. an ambulance tone
  that pulses in volume but never changes pitch.
"""


class AlternatingCodeDetector:
    def __init__(self, name, freq_a_hz, freq_b_hz, tolerance_hz, min_hold_sec,
                 min_alternations, max_gap_sec, cooldown_sec):
        self.name = name
        self.freq_a_hz = freq_a_hz
        self.freq_b_hz = freq_b_hz
        self.tolerance_hz = tolerance_hz
        self.min_hold_sec = min_hold_sec
        self.min_alternations = min_alternations
        self.max_gap_sec = max_gap_sec
        self.cooldown_sec = cooldown_sec
        self._reset_progress()
        self.cooldown_remaining = 0.0

    def _reset_progress(self):
        self.current_label = None
        self.current_hold = 0.0
        self.gap = 0.0
        self.committed_sequence = []

    def _classify(self, freq):
        if freq is None:
            return None
        if abs(freq - self.freq_a_hz) <= self.tolerance_hz:
            return "A"
        if abs(freq - self.freq_b_hz) <= self.tolerance_hz:
            return "B"
        return None

    def _commit(self, label):
        if not self.committed_sequence or self.committed_sequence[-1] != label:
            self.committed_sequence.append(label)
            self.committed_sequence = self.committed_sequence[-6:]

        seq = self.committed_sequence
        if len(seq) < self.min_alternations + 1:
            return False
        run = 1
        for i in range(len(seq) - 1, 0, -1):
            if seq[i] != seq[i - 1]:
                run += 1
            else:
                break
        return (run - 1) >= self.min_alternations

    def process(self, freq, block_dur: float) -> bool:
        if self.cooldown_remaining > 0:
            self.cooldown_remaining -= block_dur
            return False

        label = self._classify(freq)
        if label is None:
            self.gap += block_dur
            if self.gap > self.max_gap_sec:
                self._reset_progress()
            return False

        self.gap = 0.0
        self.current_hold = self.current_hold + block_dur if label == self.current_label else block_dur
        self.current_label = label

        if self.current_hold >= self.min_hold_sec and self._commit(label):
            self._reset_progress()
            self.cooldown_remaining = self.cooldown_sec
            return True
        return False


class SustainedCodeDetector:
    def __init__(self, name, freq_hz, tolerance_hz, min_duration_sec, max_gap_sec, cooldown_sec):
        self.name = name
        self.freq_hz = freq_hz
        self.tolerance_hz = tolerance_hz
        self.min_duration_sec = min_duration_sec
        self.max_gap_sec = max_gap_sec
        self.cooldown_sec = cooldown_sec
        self.hold = 0.0
        self.gap = 0.0
        self.cooldown_remaining = 0.0

    def process(self, freq, block_dur: float) -> bool:
        if self.cooldown_remaining > 0:
            self.cooldown_remaining -= block_dur
            return False

        matches = freq is not None and abs(freq - self.freq_hz) <= self.tolerance_hz
        if matches:
            self.hold += block_dur
            self.gap = 0.0
        else:
            self.gap += block_dur
            if self.gap > self.max_gap_sec:
                self.hold = 0.0

        if self.hold >= self.min_duration_sec:
            self.hold = 0.0
            self.gap = 0.0
            self.cooldown_remaining = self.cooldown_sec
            return True
        return False


def build_detector(name: str, spec: dict):
    kind = spec["type"]
    if kind == "alternating":
        return AlternatingCodeDetector(
            name=name,
            freq_a_hz=spec["freq_a_hz"],
            freq_b_hz=spec["freq_b_hz"],
            tolerance_hz=spec["tolerance_hz"],
            min_hold_sec=spec["min_hold_sec"],
            min_alternations=spec["min_alternations"],
            max_gap_sec=spec["max_gap_sec"],
            cooldown_sec=spec["cooldown_sec"],
        )
    if kind == "sustained":
        return SustainedCodeDetector(
            name=name,
            freq_hz=spec["freq_hz"],
            tolerance_hz=spec["tolerance_hz"],
            min_duration_sec=spec["min_duration_sec"],
            max_gap_sec=spec["max_gap_sec"],
            cooldown_sec=spec["cooldown_sec"],
        )
    raise ValueError(f"Unknown code type: {kind!r}")
