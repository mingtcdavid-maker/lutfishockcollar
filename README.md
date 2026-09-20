# Overnight station-code detector

Listens through the night for your fire station's siren codes and fires an
alert when it hears one. The alert action (`alert.trigger_alert`) is
currently a **placeholder**: it maxes out macOS volume and loops a loud
system sound until acknowledged. Swap `alert.py` for whatever the real
response should be later (lights, SMS, a relay board, etc) — nothing else
needs to change.

Two codes are configured out of the box, identified from real reference
recordings (`samples/`):

- **fire** — an alternating hi-lo warble (~683 Hz / ~505 Hz)
- **ambulance** — a single sustained tone (~655 Hz) that pulses in volume
  but never changes pitch

Detection is pattern-based rather than a fixed sequential "tone A then tone
B" page, because that's what these two codes actually sound like — see
`codes.py` for the two pattern types (`alternating`, `sustained`) and
`config.example.json` for how each code is described.

## Setup

```
pip install -r requirements.txt
cp config.example.json config.json
```

`config.json` top level:

| field | meaning |
|---|---|
| `min_block_energy` / `min_block_magnitude` | how loud a ~0.2s block must be before its dominant frequency is trusted at all |
| `min_block_purity` | how much of a block's in-band energy must sit in a single frequency (vs. spread across many, as broadband noise/voices do) before it's trusted; raise this if non-siren noise is triggering false positives |
| `max_alert_sec` / `alert_repeat_sec` | how long the placeholder alarm keeps sounding, and how often it repeats |
| `codes` | map of code name → detection spec (see below) |

An `alternating` code (like `fire`):

| field | meaning |
|---|---|
| `freq_a_hz` / `freq_b_hz` | the two frequencies it warbles between |
| `tolerance_hz` | how far off a block's frequency can be and still count as a match |
| `min_hold_sec` | how long one tone must hold before counting as a "beat" |
| `min_alternations` | how many A↔B switches in a row are required to trigger |
| `max_gap_sec` | silence/noise allowed between beats before the sequence resets |
| `cooldown_sec` | ignore further triggers for this long after a match |

A `sustained` code (like `ambulance`):

| field | meaning |
|---|---|
| `freq_hz` | the tone's frequency |
| `tolerance_hz` | how far off a block's frequency can be and still count as a match |
| `min_duration_sec` | how long the tone must be held (dips allowed, see `max_gap_sec`) before triggering |
| `max_gap_sec` | how long a dip/gap can be before the accumulated duration resets |
| `cooldown_sec` | ignore further triggers for this long after a match |

**Adding a new code you don't have measured yet?** Record it and run:

```
python3 detector.py analyze --seconds 20
```

while replaying it — it prints the dominant frequency of each ~0.2s block
so you can read off the pattern (alternating between two frequencies, or
one steady frequency) and its timing.

## Audio input

The detector needs your scanner's audio somehow reaching the Mac's audio
input:

- Simplest: point a mic at the scanner speaker (works, but sensitive to
  room noise/volume knob).
- More reliable: a physical audio cable from the scanner's line-out /
  headphone jack into the Mac's line-in (needs an interface if the Mac has
  no line-in), or a virtual audio device like
  [BlackHole](https://existential.audio/blackhole/) fed from the scanner
  via USB/Bluetooth audio.

Find your device index with:

```
python3 detector.py list-devices
```

## Running it overnight

```
python3 detector.py run --config config.json --device 2 --log-file overnight.log
```

Leave it running in a terminal (or under `caffeinate` so the Mac doesn't
sleep: `caffeinate -i python3 detector.py run --config config.json ...`).
The log file records every detection with a timestamp and which code
matched, so you can review what happened in the morning even if you slept
through it.

To silence an active alert without killing the script, create a file
named `ALERT_STOP` in the working directory (e.g. `touch ALERT_STOP` from
another terminal, or a Shortcuts/Automator button).

## Diagnosing false positives

Every trigger is logged with the last 5 seconds of classified frequencies
that led up to it, e.g.:

```
Match confirmed for code 'fire'. Last 5s of classified frequencies leading up to it: [None, 680.0, 685.0, ...]
```

That tells you which code fired and roughly what the audio actually looked
like going into it. For a closer look, `--debug` logs every block's
classified frequency (or `None`), not just triggers — verbose, but useful
when you're actively trying to catch a false positive in the act:

```
python3 detector.py run --config config.json --device 2 --log-file overnight.log --debug
```

Once you know what's causing it, the levers worth trying, roughly in order
of "try this first" (see the config tables above for what each field does):

1. Raise `min_hold_sec` / `min_duration_sec` — most false positives are
   short-lived coincidences; real sirens hold a tone deliberately.
2. Raise `min_alternations` (fire only) — harder for noise to coincidentally
   alternate between two narrow bands repeatedly.
3. Raise `min_block_purity` — the strongest general-purpose lever; rejects
   blocks where the frequency isn't cleanly dominant (broadband noise,
   voices, TV).
4. Tighten `tolerance_hz` — last resort; go too far and you risk missing a
   real page instead, especially given how close `fire` and `ambulance`'s
   frequencies already are (see Caveats).
5. If you're using a mic pointed at a speaker, switch to a direct
   cable/virtual-audio feed (see Audio input above) — removes room noise
   as a source entirely, often a bigger win than any config change.

## Testing

Regression-test both real codes against the reference recordings in
`samples/` (requires `ffmpeg` on PATH to decode them; confirms fire
triggers only `fire` and ambulance triggers only `ambulance`):

```
python3 test_samples.py
```

To try a new/hypothetical code without a real recording, generate a
synthetic WAV from its config spec:

```
python3 make_test_page.py --config config.json --code fire --out fire_synthetic.wav
python3 detector.py run --config config.json --input-wav fire_synthetic.wav
```

To sanity-check the alert itself (volume + sound) on your actual Mac:

```
python3 detector.py test-alert --config config.json
```

## Caveats

This is a personal backup/convenience tool, tuned by hand against two
recordings. It is **not** a substitute for your station's official
alerting system — background noise, a scanner volume that's too low, or a
code whose measured frequencies drift under real conditions can all cause
missed or false triggers. Test it against real traffic for a while before
trusting it to wake you up. `fire`'s 683 Hz and `ambulance`'s 655 Hz are
only 28 Hz apart; if you see cross-triggers in practice, tighten
`tolerance_hz` on both before touching anything else.
