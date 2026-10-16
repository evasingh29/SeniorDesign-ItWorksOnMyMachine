# Python USB serial → Gmail alerts

The primary `../firmware/receiver_esp32.ino` handles detection/LED and emits
`BREACH` / `CLEAR` over USB at **115200 baud**. This Python subsystem sends Gmail;
the ESP32 does not need Wi-Fi, credentials, NTP, or ESP Mail Client.

## Setup (from repository root)

```sh
cd 'Lab 2/alert'
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
chmod 600 .env
```

Edit `.env` locally:

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

Put a Google **App Password**, without display spaces, in `SMTP_PASSWORD`. Enable
Google 2-Step Verification and create one at
[App Passwords](https://myaccount.google.com/apppasswords). Never use your regular
Google password or put credentials in command arguments, screenshots, source, or
chat. `.env` is ignored; exported environment variables take precedence.

## Test and run

```sh
# Exactly one SMTP attempt, no Arduino; configure .env first:
TZ=America/Chicago python main.py --test-email

# Offline simulation: b, b, c, b, q → two console alerts:
TZ=America/Chicago ALERT_CHANNELS=console python main.py --simulate

# Keyboard simulation with real Gmail: b triggers email, c rearms, q exits:
TZ=America/Chicago ALERT_CHANNELS=smtp python main.py --simulate

# Close Serial Monitor; list ports and select the actual one:
python main.py --list-ports
TZ=America/Chicago ALERT_CHANNELS=smtp python main.py --port /dev/cu.usbserial-0001
```

Omit `--port` for single-device discovery, or configure `SERIAL_PORT` in `.env`.
Keep the Mac awake, USB connected, and internet available. Use Ctrl-C to stop.
Reset the ESP32 with the beam blocked after Python connects, wait for calibration,
then restore, block, hold, restore, and block again within ten seconds. Expect
exactly two email events and matching LED changes. Check inbox/spam to verify receipt.

Alerts use the Mac's receive time in the requested `TZ`, exactly:
`Critical Safety Event at HH:MM XX on Month/Day/Year`, e.g.
`Critical Safety Event at 01:20 PM on 10/16/2026`. Fields are zero-padded numeric
clock/date values, and XX is AM/PM. Keep the Mac clock synchronized.

Only standalone `BREACH` / `CLEAR` messages change state. Repeated breaches are
suppressed until `CLEAR`, with no cooldown. `ENV`, `MISSED`, and `READY` are still
recognized diagnostics for alternative receivers. Primary ESP32 `#` comments,
CSV rows, spectrum lines, and unknown messages are ignored at DEBUG log level.

Deliveries run on a background queue, so SMTP delays do not block serial handling.
Each event gets one send attempt per configured channel; failures are logged and
later events continue. No automatic retries or disk persistence are provided.
Serial disconnects retry every two seconds, preserving active state until `CLEAR`;
transitions occurring offline cannot be recovered. Logs go to the terminal and
ignored `alert.log` (`ALERT_LOG` overrides its location). Shutdown allows up to
35 seconds for queued delivery. `--test-email` exits 0 on SMTP acceptance, 1 on
failure, without printing credentials/server responses.

```sh
python -m unittest discover -v
```

Tests mock SMTP and serial hardware; they do not establish live Gmail delivery.
