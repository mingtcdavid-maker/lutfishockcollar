# Overnight two-tone page detector

Listens through the night for your station's two-tone sequential page
(e.g. Motorola Quik-Call II style dispatch alerting) and fires an alert
when it hears it. The alert action (`alert.trigger_alert`) is currently a
**placeholder**: it maxes out macOS volume and loops a loud system sound
until acknowledged. Swap `alert.py` for whatever the real response should
be later (lights, SMS, a relay board, etc) — nothing else needs to change.

## Setup

```
pip install -r requirements.txt
cp config.example.json config.json
```

Edit `config.json`:

| field | meaning |
|---|---|
| `tone_a_hz` / `tone_b_hz` | your station's two tone frequencies, in order |
| `tolerance_hz` | not currently load-bearing (Goertzel bin width comes from block size), kept for future tightening |
| `min_tone_duration_sec` | how long each tone must hold before it counts |
| `max_gap_sec` | max silence/other-audio allowed between tone A ending and tone B starting |
| `detection_threshold` | tone energy / total block energy needed to count as "present"; raise if you get false triggers, lower if real pages are missed |
| `cooldown_sec` | ignore further triggers for this long after a match, so one page doesn't re-fire |
| `max_alert_sec` / `alert_repeat_sec` | how long the placeholder alarm keeps sounding, and how often it repeats |

**You need to know your station's actual tone frequencies.** If you don't,
record a real page (or ask your radio tech/dispatch agency) and run:

```
python3 detector.py analyze --seconds 20
```

while replaying it — it prints the dominant frequency of each ~0.2s block
so you can read off the two tones and their durations.

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
The log file records every detection with a timestamp, so you can review
what happened in the morning even if you slept through it.

To silence an active alert without killing the script, create a file
named `ALERT_STOP` in the working directory (e.g. `touch ALERT_STOP` from
another terminal, or a Shortcuts/Automator button).

## Testing without a real page

Generate a synthetic recording of your configured tones and run the
detector against it (no mic or macOS needed for this part):

```
python3 make_test_page.py --config config.json --out sample_page.wav
python3 detector.py run --config config.json --input-wav sample_page.wav
```

To sanity-check the alert itself (volume + sound) on your actual Mac:

```
python3 detector.py test-alert --config config.json
```

## Caveats

This is a personal backup/convenience tool, tuned by hand against one
config. It is **not** a substitute for your station's official alerting
system — background noise, a scanner volume that's too low, or slightly
wrong tone frequencies can all cause missed pages. Test it against real
traffic for a while before trusting it to wake you up.
