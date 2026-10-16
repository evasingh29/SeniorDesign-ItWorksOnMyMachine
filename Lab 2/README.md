# Lab 2 checkoff: ESP32 → USB serial → Python → Gmail

**Upload `firmware/receiver_esp32.ino` to the ESP32. Run `alert/main.py` on the Mac.**
The ESP32 retains Aspyn's ADC GPIO 34, 4000 Hz sampling, three band-pass filters,
calibration, thresholds, 60 ms debounce, LED GPIO 2, CSV, and spectrum analysis.
It prints `BREACH` / `CLEAR` at 115200 baud; it needs no Wi-Fi, ESP Mail Client,
NTP, Gmail credentials, or `secrets.h`. Python timestamps received events and
sends Gmail in the background. Keep the Mac awake, connected to USB and internet.

## Upload

1. Arduino IDE → Boards Manager → install **esp32 by Espressif Systems**.
2. Copy **only** `firmware/receiver_esp32.ino` into a local folder named
   `receiver_esp32`, then open that sketch. Do not combine the other `.ino` files.
3. Select **ESP32 Dev Module**, select the USB port, Verify, and Upload.
4. Close Serial Monitor before starting Python; only one program may own the port.

## Start Python (from repository root)

```sh
cd 'Lab 2/alert'
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
chmod 600 .env
```

Edit `.env` locally: `ALERT_CHANNELS=smtp`, `SMTP_HOST=smtp.gmail.com`,
`SMTP_PORT=465`, `SMTP_SECURITY=ssl`, your Gmail in `SMTP_FROM` and
`SMTP_USERNAME`, recipient in `SMTP_TO`, and a **Google App Password** in
`SMTP_PASSWORD`. Never use your normal Google password or paste credentials
into terminal commands. `.env` is ignored. Existing exported variables override it.

```sh
# One real email without hardware (configure .env first):
TZ=America/Chicago python main.py --test-email

# Offline keyboard simulation: b, b, c, b, q → two alerts
TZ=America/Chicago ALERT_CHANNELS=console python main.py --simulate

# List ports, then start Gmail notifications (replace the example port):
python main.py --list-ports
TZ=America/Chicago ALERT_CHANNELS=smtp python main.py --port /dev/cu.usbserial-0001
```

Or omit `--port` for automatic discovery when exactly one USB device is present.
On later runs, just `cd 'Lab 2/alert'`, `source .venv/bin/activate`, and run the
last command. `--simulate` without the console override uses configured delivery,
so typing `b` can send a real Gmail alert without hardware. Ctrl-C stops Python.

## Checkoff

Start with the beam **blocked** (lamp on), reset the ESP32 after Python connects,
and wait ~2.5 seconds for noise calibration. Unblock, then:

1. Block → LED ON, `BREACH`, one email. Hold blocked >10 seconds: no repeats.
2. Restore → LED OFF, `CLEAR`. Block again within 10 seconds: another email.
3. Confirm subject/body format: `Critical Safety Event at 01:20 PM on 10/16/2026`
   (actual Central receive time; zero-padded 12-hour clock/date and AM/PM).
4. Check Python's terminal and ignored `alert/alert.log` for delivery success/failure.

`1/2/3`, `b/p/r`, `q`, and `s` still control the receiver. `e/t` now print help
for the Mac email controls and never fabricate a beam event. Perform calibration
commands in Serial Monitor before closing it and starting Python; a reset triggers
automatic noise calibration again. CSV/spectrum diagnostics never trigger email.
A disconnected Mac misses transitions; active Python state persists across reconnects
until `CLEAR`. Network failure is logged; existing sends are attempted once per event
without automatic retries. Pending deliveries are in memory, not durable storage.

## Files

| Folder / file | Role |
| --- | --- |
| `firmware/receiver_esp32.ino` | **Primary** ESP32 detection and serial events |
| `alert/main.py`, `notifier.py`, `formatter.py` | **Primary** Mac serial/Gmail integration |
| `firmware/capture.ino` | Elif's separate classic ATmega328P Uno/Nano capture sketch |
| `firmware/filter_coeffs.h` | Elif's alternative 3000 Hz SOS filter; unused by primary firmware |
| `firmware/receiver.ino` | Empty placeholder; Elif's nonempty alternative receiver is still missing |
| `matlab/*.m` | Supporting design/export to `firmware/filter_coeffs.h`; MATLAB Signal Processing Toolbox |
| `analysis/capture_fft.py` | Supporting AVR FFT tool; NumPy, Matplotlib, pyserial; not the ESP32 CSV protocol |

Elif's separate notification files are still unavailable. Supporting files are
unchanged by this architecture switch. Old local `firmware/secrets.h` remains
ignored and unused; do not copy it into the upload sketch or commit it.

## Tests / verification limits

```sh
python3 -m unittest discover -s 'Lab 2/alert' -v
python3 -m unittest discover -s 'Lab 2/firmware/tests' -v
```

Host tests validate the receiver's serial transition code with mocked Arduino APIs
and feed its output through Python. They do not verify ADC timing, ESP32 scheduling,
USB hardware, SMTP receipt, or the actual ESP32 toolchain. Arduino Verify and the
physical steps above remain required. See [firmware details](firmware/README.md)
and [Python details](alert/README.md).
