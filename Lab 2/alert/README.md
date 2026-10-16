# Electric-eye Python alerts

This subsystem consumes Elif's completed receiver output. It does not sample ADCs,
filter signals, apply thresholds, or control local alarms. The repository's
`firmware/receiver.ino` is separate and is not modified here.

## macOS setup

From the repository root, use Python 3.10 or newer:

```sh
cd 'Lab 2/alert'
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
chmod 600 .env
python -m unittest discover -v
ALERT_CHANNELS=console python main.py --simulate
```

Gmail SMTP is the primary/default delivery method. The simulation command above
overrides delivery to console only. Type `b`, `b`, `c`, `b`, then `q` (press Return
after each). Expect two alerts; repeated breaches before a clear are suppressed.
You can also enter complete receiver lines. Alerts use the computer's local time
captured at the breach, exactly `Critical Safety Event at HH:MM XX on Month/Day/Year`:
for example `Critical Safety Event at 01:20 PM on 10/16/2026`. XX is AM or PM;
month/day and clock fields are numeric and zero-padded.

## Delivery configuration

Edit only `Lab 2/alert/.env` locally, or export environment variables (exports
take precedence). Do not copy credentials from Lab 1. Configure:

```dotenv
ALERT_CHANNELS=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_SECURITY=ssl
SMTP_FROM=your-address@gmail.com
SMTP_TO=recipient@example.com
SMTP_USERNAME=your-address@gmail.com
SMTP_PASSWORD=
```

Replace both sender placeholders with your full Gmail address and set `SMTP_TO`
to the intended recipient (one address for the one-email test). Use the same
address for `SMTP_FROM` and `SMTP_USERNAME`. To also print live alerts, set
`ALERT_CHANNELS=smtp,console`.

1. Enable **2-Step Verification** in your Google Account.
2. Open [Google App Passwords](https://myaccount.google.com/apppasswords), create
   one named `Senior Design Lab 2`, and put its 16 characters in `SMTP_PASSWORD`
   in your local `.env`, without the display spaces. **Never use your regular
   Google password.** Do not paste credentials into terminal commands or chat.
3. If App Passwords is unavailable, check account/administrator restrictions;
   see [Google's App Password guide](https://support.google.com/mail/answer/185833?hl=en).

The existing SMTP notifier uses certificate-verified SSL on `smtp.gmail.com:465`
([Google SMTP settings](https://support.google.com/a/answer/176600?hl=en)).
It requires nonempty credentials for Gmail; it cannot determine whether a supplied
password is an App Password, so supply only the App Password you generated.

### Send one test email without hardware

After configuring `.env`, run from `Lab 2/alert` with the virtual environment active:

```sh
python main.py --test-email
```

This makes exactly one SMTP send attempt, with no retries, no serial connection,
and no ntfy or console delivery, regardless of `ALERT_CHANNELS`. It uses the normal
alert format in the subject and body. Configure a single `SMTP_TO` address to send
to just one recipient. Exit status is 0 when SMTP accepts the message, 1 on failure;
check the inbox/spam folder to confirm arrival. Failures log only the error class,
not credentials or server responses. Do not enable SMTP debug logging. If a send
fails ambiguously, check the inbox before manually running the command again.

For offline keyboard simulation, always use:

```sh
ALERT_CHANNELS=console python main.py --simulate
```

Optionally add `ntfy` to `ALERT_CHANNELS`, set `NTFY_URL` to your HTTPS topic URL,
and set `NTFY_TOKEN` if required. Simulation uses the configured channels too,
so choose `console` for a test without external delivery. Never put secrets in
source files. Existing Git rules exclude `.env`, `.venv`, and `*.log`.

## Live Arduino integration

Connect the Arduino running Elif's receiver firmware over USB and close Arduino
Serial Monitor or any other program using the port:

```sh
python main.py --list-ports
python main.py                          # discovers a single USB serial device
python main.py --port /dev/cu.usbmodem12301
```

Alternatively set `SERIAL_PORT` in `.env`. If multiple USB devices are present,
select the port explicitly. Serial always uses **115200 baud**. The receiver must
terminate messages with a newline; CRLF is supported. Opening the serial port can
reset an Arduino. Wait for receiver startup before interrupting the beam.

Recognized messages:

| Message | Action |
| --- | --- |
| `BREACH` | Log interruption; queue one alert if previously clear |
| `CLEAR` | Log restoration; immediately allow the next breach |
| `ENV <value>` | Log finite numeric filtered signal strength |
| `MISSED <count>` | Log nonnegative deadline count |
| `READY FS=... sections=...` | Log receiver startup information |

Malformed and unknown lines are logged and ignored. Diagnostics never trigger
alerts. Serial errors retry every two seconds; auto discovery runs again on each
retry. Active breach state survives reconnects and READY messages. A CLEAR is
required to rearm, so a restoration missed during disconnection cannot be inferred.

Deliveries run in a background queue with a ten-second network timeout per
transport operation. Each event is attempted once per channel; failures are
logged and later events continue. Automatic network retries are omitted because
an ambiguous failure could duplicate a delivered alert. The queue is in memory;
process crashes can lose pending deliveries. Ctrl-C or `q` allows up to 35 seconds
to drain it, then logs a warning if delivery is still pending.

Logs go to the console and `alert.log` beside the script (override with
`ALERT_LOG`). They include breaches, restorations, diagnostics, delivery successes,
and failures. Check them during checkoff; this Python subsystem is supplemental
to the receiver's local alarm outputs.

## Checkoff procedure and test scope

First verify simulation and automated tests. Then, with actual receiver hardware,
interrupt the beam, hold it interrupted, restore it, and interrupt it again.
Confirm two alerts and matching restoration/delivery logs. Unplug/reconnect USB
to check reconnection, and test an invalid notification configuration to inspect
failure logs. Hardware, SMTP delivery, and ntfy delivery require your own live
validation; automated tests use mocks and do not establish hardware performance.
