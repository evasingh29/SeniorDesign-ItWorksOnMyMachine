# ESP32 electric-eye receiver: direct Gmail notifications

`receiver_esp32.ino` extends Aspyn's receiver with queued, event-based email.
The ESP32 sends Gmail directly over Wi-Fi; a laptop/Python is not required after
upload (Serial Monitor is useful for checkoff diagnostics).

## Arduino IDE setup

1. Install Arduino IDE and **esp32 by Espressif Systems** through Boards Manager.
   If needed add `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
   to Additional Boards Manager URLs. Select **ESP32 Dev Module** and the USB port.
   This sketch targets the original dual-core ESP32, not C3/S2/S3 variants.
2. Install **ESP Mail Client by Mobizt**, version **3.4.24**, through Library Manager.
   Keep a record of the exact ESP32 board package version used during checkoff.
3. Arduino requires a sketch folder matching its primary `.ino` name. Copy
   `receiver_esp32.ino` and the local `secrets.h` into a separate local folder named
   `receiver_esp32`, then open `receiver_esp32/receiver_esp32.ino`. Keep only that
   `.ino` in the sketch folder; do not combine it with `receiver.ino` or supporting `capture.ino`. After edits,
   refresh the copy from this repository. Keep copied secrets outside version control.
4. Verify, upload, and open Serial Monitor at **115200 baud**.

### Library/core compatibility

ESP Mail Client is [deprecated by its author](https://mobizt.github.io/ESP-Mail-Client/),
who recommends ReadyMail. It is intentionally retained to preserve the team's
working mail integration. Its [release notes](https://github.com/mobizt/ESP-Mail-Client/releases)
identify ESP32 core 3.1.x fixes in 3.4.23 and a Client.h API fix in 3.4.24.
Older library versions may fail with newer board packages; install 3.4.24 before
investigating those errors. This is not a guarantee for every later ESP32 core.
Do not silently migrate libraries during checkoff.

The notification path uses ESP32 FreeRTOS `xQueueCreate`, zero-wait `xQueueSend`,
`xQueueReceive`, `portMUX_TYPE` critical sections, and pinned tasks. These follow
ESP32's dual-core APIs; no ISR queue calls are needed because detection runs in
`loop()`. The SNTP callback API follows Espressif's
[Arduino time example](https://github.com/espressif/arduino-esp32/blob/master/libraries/ESP32/examples/Time/SimpleTime/SimpleTime.ino).
Actual compilation against the installed board package/library is still required.

## Credentials

`secrets.h` is local and excluded by `Lab 2/.gitignore`. For a fresh checkout copy
`secrets.example.h` to `secrets.h` and replace placeholders locally:

- `WIFI_SSID`, `WIFI_PASSWORD`: a 2.4 GHz personal WPA/WPA2 network or hotspot;
  enterprise eduroam authentication is not implemented.
- `AUTHOR_EMAIL`: full sender Gmail address.
- `AUTHOR_APP_PW`: Google **App Password**, never the normal Google password.
  Enable 2-Step Verification, then create one at
  [Google App Passwords](https://myaccount.google.com/apppasswords). Enter its 16
  characters without display spaces. Account policy may restrict App Passwords.
- `RECIPIENT`: your intended email recipient.

Gmail host/port remain `smtp.gmail.com:465` (SSL) in the sketch. Do not enable SMTP
debugging or paste credentials into logs, screenshots, commits, or chat. Rotate
credentials from the originally shared sketch before use. No secrets are present
in the example header. Secrets are compiled into the device and are not secure
against extraction by someone with physical access.

## Notification changes

- The first body line is exactly
  `Critical Safety Event at HH:MM XX on Month/Day/Year`, e.g.
  `Critical Safety Event at 01:05 PM on 10/16/2026`. Clock/date fields are numeric
  and zero-padded, with 12-hour time and AM/PM. Group, event number, breach number,
  detection-band snapshot, and TEST/BEAM INTERRUPTION diagnostics follow it.
- Each debounced present-to-broken transition after arming creates a new event
  while alerts are enabled. There is no cooldown. Remaining blocked creates no
  further transitions/events. Startup still assumes blocked and arms only after
  first seeing the beam. Breaches while disabled are counted/logged but not queued.
- A FreeRTOS FIFO holds **16 waiting events**, plus one being delivered. Queue
  records are copied by value and retain event number, breach number, 64-bit
  monotonic detection timestamp, resolved wall timestamp, band, and test flag.
  A full/unavailable queue rejects the newest event and prints
  `ALERT QUEUE OVERFLOW` with event ID and cumulative rejection count. Existing
  events remain intact. This is bounded buffering, not guaranteed unlimited delivery.
- Only the loop owns enable/counter state; the queue transfers records between
  cores. The NTP clock reference is protected by a short critical section. The
  mail task never reads the mutable detection-band selection. Existing analysis
  task sharing is unchanged; this change does not claim to audit its buffer design.
- NTP uses `pool.ntp.org` / `time.nist.gov` with the original Central rule
  `CST6CDT,M3.2.0,M11.1.0` (automatic CST/CDT). A valid SNTP callback is required;
  a fabricated or unavailable date is never emailed. Events captured before first
  sync are back-dated from their monotonic detection time using the NTP reference
  within the same boot. The timestamp freezes when resolved, so retries retain it.
  This reconstruction has NTP/network clock accuracy, not an independent RTC.
- The worker tries each event at most **4 times**, with **2/4/8 second** backoffs.
  Each attempt permits up to 5 seconds for Wi-Fi and 5 seconds for valid time.
  SMTP uses ESP Mail Client's own network timeouts. All network work and retry
  delays stay in the core-0 task; queue insertion never waits for network access.
  Serial logging and core contention can still affect timing: monitor `missed`.
- Logs distinguish `breach detected`, `alert queued`, `delivery attempt`, `retry`,
  `email sent`, `email failed`, and final failure. A successful SMTP result means
  server acceptance, not proof of inbox arrival. An ambiguous SMTP failure can
  result in a duplicate email on retry; event IDs identify these duplicates.
- Final failure discards only the current event and advances to other queued
  events. Retries preserve the rest of the FIFO but can delay them. Queue contents
  are RAM-only and do not survive reset or power loss. There is no laptop fallback.

## Preserved receiver behavior and controls

ADC GPIO **34**, LED GPIO **2**, **4000 samples/s** (250 microseconds), the original
cascaded biquads/envelopes, hysteresis and 60 ms debounce, calibration, spectrum,
and CSV processing are retained. Bands remain **425–445**, **490–510**, **525–545 Hz**.
LED ON means broken, OFF means present.

| Command | Behavior |
| --- | --- |
| `1` / `2` / `3` | Select detection band |
| `b` | Noise calibration, beam blocked, lamp on |
| `p` | Optional signal calibration, beam clear, lamp on |
| `r` | Reset thresholds |
| `q` | Toggle CSV |
| `s` | Dump spectrum |
| `e` | Toggle automatic alerts for future breaches; queued events still deliver |
| `t` | Queue one TEST email through the same queue/time/retry/SMTP pipeline |

`t` works even when automatic alerts are disabled. It has its own event ID, does
not increment the breach count, and is clearly labeled TEST in subject and body.

## Safe checkoff procedure (expected results, not completed hardware tests)

Use your own recipient address and a controlled tabletop beam; retain the local
LED alarm. Start with beam **blocked** and lamp on, wait for automatic noise
calibration (~2.5 seconds), then unblock to arm. Keep CSV on to observe missed
sampling deadlines, or use `q` to reduce monitor output.

1. **One test email:** send `t` once. Expect one TEST event queued, a delivery
   attempt, then `email sent`. Check inbox/spam, exact first body line and Central
   date/time. No real breach should be counted. On failure, inspect retry/final
   diagnostics; don't repeatedly press `t` while delivery is pending.
2. **One real interruption:** block the armed beam for longer than 60 ms. Expect
   LED ON, `beam BROKEN`, one breach ID and one queued event/email.
3. **Restoration:** unblock for longer than 60 ms. Expect LED OFF and
   `beam PRESENT`. Restoration itself does not send an email.
4. **Two interruptions under 10 seconds:** block, restore fully, and block again
   a few seconds later. Expect two breach/event IDs and two emails, even if the
   first is still being sent. Check that timestamps reflect detection, not delivery.
5. **Temporary Wi-Fi failure:** briefly disable your own hotspot/router, then
   interrupt/restore twice. Expect Wi-Fi failure and retry logs while detection,
   LED and CSV continue. Restore network before retries exhaust and check that
   both events arrive. If exhausted, expect explicit final failure, then processing
   of the next event. Longer outages can exhaust retries or fill the queue.
6. **Continuous blockage:** hold blocked for at least 15 seconds. Expect only
   one breach event. Restore and block again to get exactly one new event.
7. **Optional time/enable checks:** boot without internet/NTP, press `t`, verify
   no email is sent with an invalid date. Restore internet within retry limits.
   Toggle `e`, check breaches log without new automatic email, then re-enable.
   Confirm `1/2/3`, `b/p/r`, `q`, `s`, LED states and `missed` still behave as before.

## Validation status

No Arduino CLI, local ESP32 core, or ESP Mail Client install was found in the
standard locations in this workspace session. Static preservation checks and
host-side notification tests with mocked platform APIs are possible; they cannot
establish Arduino preprocessing, ESP32 compilation, real FreeRTOS scheduling,
SMTP/TLS compatibility, ADC timing, email receipt, or hardware behavior. Run Arduino
IDE Verify and the hardware procedure above before claiming checkoff success.

Run the repeatable host checks from the repository root:

```sh
python3 -m unittest discover -s 'Lab 2/firmware/tests' -v
```

Validation in this session: **2 host tests passed**. The C++ harness compiles the
actual notification functions and detection block with `-std=c++11 -Wall -Wextra
-Werror` against fake platform APIs. It checks Central winter/summer dates,
midnight/noon formatting, pre-sync rejection and backdating, frozen timestamps,
queue ordering/overflow, repeated and continuous interruptions, disabled alerts,
TEST labeling, successful retry, exhausted retries, Wi-Fi failure, and NTP failure.
A separate preservation comparison passed for filter structures, calibration and
threshold functions, spectrum/CSV functions, sampling/filter/calibration loop,
ADC/LED/filter/spectrum setup, and detection/debounce/LED transition code.
These host checks do not compile the full sketch against Arduino libraries.
