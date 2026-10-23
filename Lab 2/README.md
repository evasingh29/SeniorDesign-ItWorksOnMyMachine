# Lab 2 — Robust Electric Eye

ECE:4880 Capstone Senior Design. The ESP32 detects interruption of a modulated
light beam and sends USB serial events to a Python program on the host computer,
which timestamps events and sends email alerts.

## Submission files

| Path | Purpose |
| --- | --- |
| `firmware/receiver_esp32.ino` | Working ESP32 receiver: filtering, calibration, LED, serial events, diagnostics |
| `alert/main.py` | Serial connection, event handling, simulation, and email test |
| `alert/notifier.py`, `alert/formatter.py` | Notification delivery and alert formatting |
| `alert/requirements.txt` | Python runtime dependencies |
| `alert/test_*.py`, `firmware/tests/` | Automated host tests |
| `firmware/capture.ino`, `analysis/capture_fft.py` | Separate AVR capture and FFT tools for transmitter experiments |
| `matlab/*.m`, `firmware/filter_coeffs.h` | Alternative 3000 Hz filter design/export; unused by the ESP32 receiver |

## Receiver setup

Install **esp32 by Espressif Systems** in Arduino IDE Boards Manager. Copy only
`firmware/receiver_esp32.ino` into a sketch folder named `receiver_esp32`, select
**ESP32 Dev Module** and the USB port, then Verify and Upload. The separate AVR
capture sketch must stay outside that sketch folder.

The receiver uses ADC **GPIO 34**, LED **GPIO 2**, and **4000 Hz** sampling.
LED ON indicates a broken beam; OFF indicates a received beam. A 160 Hz high-pass
stage suppresses low-frequency interference, followed by three selectable
band-pass channels: **425–445**, **490–510**, and **525–545 Hz** (nominal ranges;
the code scales each section's bandwidth by 1.5). Band 2 is selected by default.
Noise calibration, separate ON/OFF thresholds, and **60 ms debounce** stabilize
detection. Confirm the appropriate band with measurements of the actual transmitter.

Start with the beam **blocked** (lamp on when testing lamp interference). Reset
after Python connects, allow about **2.5 seconds** for noise calibration, then
unblock the beam before testing interruptions.

| Serial command (115200 baud) | Action |
| --- | --- |
| `1`, `2`, `3` | Select detection band |
| `b`, `p`, `r` | Calibrate noise, calibrate signal, reset thresholds |
| `q`, `s` | Toggle CSV output, dump spectrum |
| `e`, `t` | Display Python email instructions |

The receiver emits newline-terminated `BREACH` and `CLEAR` transitions. Diagnostic
comments, CSV, and spectrum output do not trigger alerts. Close Serial Monitor
before starting Python so the serial port is available.

## Email setup and operation

From the repository root:

```sh
cd 'Lab 2/alert'
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create `alert/.env` (relative to Lab 2) with the following settings, filling in
addresses and a Google App Password locally:

```dotenv
ALERT_CHANNELS=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_SECURITY=ssl
SMTP_FROM=your-address@gmail.com
SMTP_USERNAME=your-address@gmail.com
SMTP_TO=recipient@example.com
SMTP_PASSWORD=
```

Use a Google App Password rather than the account password. `.env` is ignored;
exported environment variables override its values. Keep credentials out of the
submission. Run `chmod 600 .env` from `alert/` after creating it.

Run these commands from `Lab 2/alert` with the virtual environment active:

```sh
# One real email without hardware:
TZ=America/Chicago python main.py --test-email

# Offline simulation: b, b, c, b, q should produce two console alerts:
TZ=America/Chicago ALERT_CHANNELS=console python main.py --simulate

# Find the port, then replace the example with the actual device:
python main.py --list-ports
TZ=America/Chicago python main.py --port /dev/cu.usbserial-0001
```

Omit `--port` for discovery when exactly one USB device is present, or set
`SERIAL_PORT` in `.env`. Keep the host awake, connected to USB and the internet.
Ctrl-C stops the program. Simulation without the console override uses configured
delivery and can send real email.

The subject and body use the host's receive time, for example:
`Critical Safety Event at 01:20 PM on 10/16/2026`.
The clock and date are zero-padded, with a 12-hour clock and AM/PM.

A continuous blockage produces one alert. `CLEAR` rearms detection immediately;
there is no notification cooldown. Email runs in a background worker. Each event
gets one attempt per configured channel, with success/failure recorded in the
terminal and ignored `alert/alert.log`. There are no automatic delivery retries
or durable queues. Serial reconnects preserve event state until `CLEAR`, but
transitions during disconnection cannot be recovered. Shutdown allows up to
35 seconds for queued delivery.

## Verification and report evidence

1. Start Python, reset with the beam blocked, wait for calibration, then unblock.
2. Block: expect LED ON, `BREACH`, and one email. Hold longer than ten seconds
   and confirm no repeats.
3. Restore: expect LED OFF and `CLEAR`. Block again within ten seconds and
   confirm another email with the required timestamp format. Check inbox/spam.
4. Repeat under ambient lighting and interfering sources; record conditions,
   distances, selected band, latency, and missed or false detections.

The lab report must describe experiments on the provided transmitter and the
observed results, justify the filter specification from those measurements, and
report receiver selectivity and alert behavior. This repository does not supply
measured results; use the team's actual observations.

The optional `analysis/capture_fft.py` tool requires NumPy, Matplotlib, and
pyserial, paired with `firmware/capture.ino` on a classic ATmega328P Uno/Nano.
It saves raw captures in `data/` and plots in `docs/`; its protocol differs from
the ESP32 diagnostics. The MATLAB scripts require Signal Processing Toolbox
and export an alternative filter header, not the active ESP32 filter.

From the repository root, run the existing tests:

```sh
python3 -m unittest discover -s 'Lab 2/alert' -v
python3 -m unittest discover -s 'Lab 2/firmware/tests' -v
```

Tests mock SMTP/serial and compile the primary sketch against host Arduino and
FreeRTOS stubs. They do not establish ESP32 toolchain compilation, ADC timing,
physical selectivity, or email receipt. Arduino Verify and physical testing are
still required.
