# Primary ESP32 receiver: USB serial notifications

Upload **`receiver_esp32.ino`**, using **ESP32 Dev Module** and the Espressif ESP32
Arduino core. No ESP Mail Client, Wi-Fi setup, NTP, or `secrets.h` is required.
Copy only this `.ino` into a sketch folder named `receiver_esp32` before opening
it in Arduino IDE. Keep Elif's supporting sketches out of that sketch folder.

Aspyn's signal processing and hardware behavior remain intact: ADC GPIO 34,
4000 Hz / 250 µs sampling, cascaded filters for 425–445 / 490–510 / 525–545 Hz,
thresholds, calibration, hysteresis, 60 ms debounce, LED GPIO 2, spectrum and CSV.
LED ON means broken, OFF means present. Startup assumes blocked; allow automatic
noise calibration (~2.5 seconds), then unblock before testing interruptions.

Serial is **115200 baud**, newline terminated:

| Output | Meaning |
| --- | --- |
| `BREACH` | Debounced transition from present to broken |
| `CLEAR` | Debounced transition from broken to present |
| `# ...`, numeric CSV/spectrum rows | Diagnostics; Python ignores these |

There is no notification cooldown. A continuous blockage emits one transition;
a restoration followed by another interruption emits another `BREACH`. Python
suppresses repeated `BREACH` messages until `CLEAR` and sends email in a background
worker. Timestamps come from the Mac when the event arrives, not from the ESP32.

| Serial control | Behavior |
| --- | --- |
| `1/2/3` | Select detection band |
| `b` / `p` / `r` | Noise calibration / signal calibration / reset thresholds |
| `q` / `s` | Toggle CSV / dump spectrum |
| `e` / `t` | Print instructions for Python email controls; no synthetic event |

Close Serial Monitor before running Python. Reset with the beam blocked after
Python connects, then restore/block/hold/restore/block to test LED behavior and
separate emails less than ten seconds apart. Run one hardware-free email with
`TZ=America/Chicago python main.py --test-email` from `Lab 2/alert` first.

Elif's `capture.ino` is standalone ATmega328P Uno/Nano firmware; it does not belong
on the primary ESP32. `filter_coeffs.h` is a separate 3000 Hz alternative filter
and is not included by the active receiver. `receiver.ino` is still empty.
Local `secrets.h` is ignored and unused; its example is retained for history.

Run `python3 -m unittest discover -s 'Lab 2/firmware/tests' -v` from the repository
root for host C++/Python protocol checks. The harness compiles the entire primary
sketch against fake Arduino/FreeRTOS APIs and tests real transition code; it does
not establish ESP32 compilation, real-time sampling, or hardware behavior. Verify
in Arduino IDE with the ESP32 core, then perform the physical checkoff procedure.
See [the short setup commands](../README.md).
