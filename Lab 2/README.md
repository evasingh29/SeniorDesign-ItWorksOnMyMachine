# Lab 2: electric-eye safety system

The team's current receiver implementation is
[`firmware/receiver_esp32.ino`](firmware/receiver_esp32.ino), based on Aspyn's ESP32
receiver with queued Gmail notifications. The ESP32 sends email directly over
Wi-Fi; Python is not required for this firmware. Arduino compilation, hardware
behavior, and live email delivery still require validation on the team's setup.
See the [firmware setup and checkoff guide](firmware/README.md).

## Folder organization

| Folder | Contents |
| --- | --- |
| `matlab/` | MATLAB `.m` filter-design and analysis scripts |
| `analysis/` | FFT, spectrum, plotting, and data-analysis Python scripts |
| `firmware/` | Arduino `.ino` implementations and filter coefficient headers |
| `alert/` | Python serial notification software, configuration examples, and tests |

Elif's supporting files are now present: `firmware/capture.ino`,
`firmware/filter_coeffs.h`, `matlab/design_filter.m`, `matlab/write_coeffs_header.m`,
and `analysis/capture_fft.py`. They remain separate from the primary ESP32 design.
No `elif_original/` folder is used.

## Which firmware to upload

**For the team's actual ESP32 hardware, upload only `receiver_esp32.ino` using
ESP32 Dev Module.** Its existing ADC GPIO 34, 4000 Hz sampling, three filters,
calibration, LED GPIO 2, and direct Gmail pipeline remain unchanged. None of
Elif's ADC/register code or coefficients are incorporated into this sketch.

`capture.ino` is optional bench capture firmware for a **classic ATmega328P Arduino
Uno/Nano**. It samples A0 at a nominal 10000 Hz, stores 1200 samples quantized to
8 bits, and prints them expanded back onto a 10-bit scale. The ADC reference is
assumed to be nominal 5 V by the Python tool; actual voltage accuracy requires
reference measurement. The ADC prescaler is configured with AVR-only registers;
this sketch is not an ESP32 implementation. It now includes `Arduino.h` explicitly
and rejects other MCUs with a clear compile-time error. Its sampling behavior is
otherwise unchanged. Measured sample timing still needs hardware validation.

Each selected Arduino sketch needs its own matching folder and only one `.ino`:

- Primary: a local `receiver_esp32/` folder containing `receiver_esp32.ino` and
  local `secrets.h`; follow [the firmware guide](firmware/README.md).
- Supporting AVR capture: a separate local `capture/` folder containing only
  `capture.ino`, compiled for **Arduino Uno** or classic Nano as appropriate.

Do not open the entire `firmware/` directory as one sketch. Arduino combines `.ino`
files in a sketch, which would produce duplicate `setup()` and `loop()` definitions
and mix incompatible board APIs. This repository groups source by function, not
as a single compilable Arduino sketch folder.

## MATLAB design and FFT analysis

- `matlab/design_filter.m` designs a Butterworth band-pass filter, checks its
  float32 poles/frequency response, and plots a simulated interruption. It requires
  MATLAB with Signal Processing Toolbox. Its existing `f0=500` is explicitly a
  placeholder, not a measured transmitter frequency. Its `fs=3000` belongs to the
  alternative design and differs from the active ESP32's 4000 Hz sampling rate.
  No design settings or active ESP32 coefficients were changed during import.
- `matlab/write_coeffs_header.m` folds gains into SOS numerators, normalizes `a0`,
  and writes `firmware/filter_coeffs.h`. Its destination is resolved relative to
  the writer's own file, not MATLAB's working directory. The firmware directory
  already exists. Running the writer replaces this generated header; review the
  design settings and matching receiver before doing so.
- `analysis/capture_fft.py` captures raw samples from an alternative Arduino
  capture protocol or analyzes an existing capture CSV. It requires NumPy and
  Matplotlib, plus pyserial for live capture. It writes captures to `Lab 2/data/`
  and plots to `Lab 2/docs/`, relative to the script. These outputs are created
  only when the script is run. Its ADC scaling currently assumes 5 V / 10-bit
  counts, so its voltage results are not valid for the current ESP32 unchanged.

In MATLAB, use the actual absolute repository path, for example:

```matlab
run(fullfile('/absolute/path/to/SeniorDesign-ItWorksOnMyMachine', ...
             'Lab 2', 'matlab', 'design_filter.m'));
```

The design script adds its own directory to MATLAB's search path so its companion
writer can be resolved from any working directory. The response plot is saved to
`Lab 2/docs/filter_response.png`. No MATLAB scripts were executed and no coefficient
header was generated as part of this organization change.

For analysis of an existing compatible CSV, from the repository root:

```sh
cd 'Lab 2'
python3 analysis/capture_fft.py --csv /absolute/path/to/capture.csv --no-plot
```

`--no-plot` suppresses the interactive window but still writes a PNG and therefore
still requires Matplotlib.

## Supporting protocol, coefficients, and missing files

- **Capture firmware is present and independent of the receiver.** The Python
  tool sends `c`, then reads `BEGIN <sample_rate> <count>`, one raw integer sample
  per line, and `END`. The supplied sketch implements this format at 115200 baud.
  Neither file needs `filter_coeffs.h` or Elif's original receiver. The ESP32's
  existing CSV/spectrum format is different and is not an input to this tool.
- **Elif's nonempty receiver implementation is still missing.** The existing
  `firmware/receiver.ino` remains a zero-byte placeholder and has not been changed.
- **`filter_coeffs.h` is present.** It defines `FS=3000`, `NUM_SECTIONS=2`, and a
  two-row `SOS` coefficient array for an alternative 450–550 Hz bandpass. Static
  float32 checks find a maximum pole radius of about 0.931618 (stable), near-unity
  gain at 500 Hz, and about -3.01 dB at 450/550 Hz. This checks the supplied numbers,
  not a MATLAB regeneration or measured response. Neither current sketch includes
  this header. It must not replace the ESP32's three 4000 Hz filters.
- **MATLAB generation is separate from the primary firmware.** The writer's
  script-relative destination is `firmware/filter_coeffs.h`, matching the supplied
  header's `FS`, `NUM_SECTIONS`, and `SOS` schema. Default design settings match the
  header description, but reproducing its numbers requires MATLAB and Signal
  Processing Toolbox. Running the writer overwrites the supplied generated header;
  review changes before use. No coefficients were generated during this validation.
- **Elif's separate notification files have not been supplied.** Existing
  `alert/main.py`, `notifier.py`, and `formatter.py` are the current Python
  subsystem, so a teammate-notifier comparison/merge remains pending.

## Receiver implementations and notification paths

- **Current team firmware:** `firmware/receiver_esp32.ino`. Uses ADC GPIO 34,
  LED GPIO 2, 4000 Hz sampling, and three detection bands: 425–445, 490–510,
  and 525–545 Hz. It retains calibration, spectrum/CSV output, and Serial Monitor
  controls, with NTP timestamps, a FreeRTOS event queue, and limited email retries.
- **Existing placeholder:** `firmware/receiver.ino` is empty. It is preserved and
  is not Elif's receiver implementation. Do not select it for checkoff.
- **Optional USB/Python notification path:** [`alert/`](alert/README.md) consumes
  `BREACH`, `CLEAR`, `ENV`, `MISSED`, and `READY` messages at 115200 baud. It has
  Gmail SMTP, console simulation, and optional ntfy support. This is a separate
  integration path for firmware implementing that protocol; the current ESP32's
  diagnostic/CSV output is not assumed to implement that protocol.

Keep alternative firmware implementations separate. Do not combine multiple
`.ino` implementations in one Arduino sketch folder. Follow the firmware guide
for a sketch folder named `receiver_esp32` with only the selected implementation.

## Incorporating Elif's files

Place files by function using the folders above. Retain both implementations on
name collisions, using descriptive names such as `receiver_elif.ino`,
`filter_coefficients_elif.h`, or `notifier_elif.py` after inspecting dependencies.
Update alternative-file imports/includes as necessary, rather than overwriting
`receiver_esp32.ino` or the existing alert modules. Preserve companion coefficient
headers and their relationship to the matching firmware.

Compare alternative notification behavior before merging changes into the active
Python subsystem. Preserve timestamp formatting, per-interruption duplicate
suppression, nonblocking delivery, configuration through environment variables,
and existing tests. Do not change ESP32 signal processing or hardware behavior
solely to accommodate an alternative receiver. No comparison or merge has been
performed because Elif's separate notification source files are unavailable.

## Secrets and local files

- ESP32 credentials belong only in ignored `firmware/secrets.h`; use
  `firmware/secrets.example.h` as the safe template.
- Python credentials belong in ignored `alert/.env` or environment variables;
  use `alert/.env.example` as the template.
- `.env`, virtual environments, Python caches, and generated `*.log` files are
  excluded by existing Git rules. Do not force-add them.
- Inspect imported files for embedded passwords/tokens before staging. Externalize
  real credentials without exposing them in examples, logs, or review output.
  Rotate credentials previously shared in source.

## Available validation

From the repository root:

```sh
python3 -m unittest discover -s 'Lab 2/alert' -v
python3 -m unittest discover -s 'Lab 2/firmware/tests' -v
```

The firmware tests compile extracted notification/detection code against mocked
host APIs; they are not an Arduino/ESP32 build or a hardware test. MATLAB execution requires MATLAB and Signal Processing Toolbox, unavailable in
this session. The bundled Arduino IDE CLI and installed Arduino AVR core/toolchain
can validate supporting capture firmware. The ESP32 core and ESP Mail Client are
not installed in the inspected standard locations, so primary firmware compilation
and hardware/email testing remain unverified. Live receiver and email testing
instructions are in the component READMEs.

### File roles

| Source | Role / dependencies |
| --- | --- |
| `firmware/receiver_esp32.ino` | **Primary** ESP32 receiver; ESP32 core, Wi-Fi, FreeRTOS, ESP Mail Client, local credentials |
| `firmware/capture.ino` | Supporting ATmega328P raw capture; Arduino AVR core only |
| `firmware/receiver.ino` | Empty placeholder; not uploadable as a working receiver |
| `firmware/filter_coeffs.h` | Supporting generated SOS header; currently unused by either nonempty sketch |
| `firmware/secrets.example.h` | Safe credential template; copy locally to ignored `secrets.h` |
| `matlab/design_filter.m` | Supporting Butterworth design/plots; MATLAB Signal Processing Toolbox |
| `matlab/write_coeffs_header.m` | Supporting coefficient export; MATLAB |
| `analysis/capture_fft.py` | Supporting capture/FFT/plots; NumPy, Matplotlib, pyserial |
| `alert/main.py` | Optional serial notification path; pyserial and optional python-dotenv |
| `alert/notifier.py` | Optional Python background console/Gmail/ntfy delivery; standard library |
| `alert/formatter.py` | Optional Python alert text formatter; standard library |
| `alert/test_main.py`, `alert/test_formatter.py` | Notification/parser/formatter unit tests with mocked transports |
| `firmware/tests/test_notifications.py` | Primary notification host tests with fake ESP32/SMTP APIs and a host C++ compiler |

The optional Python alert path is not required by the primary ESP32 firmware.
The existing ESP32 spectrum/CSV functionality already supplies spectral diagnostics;
no supporting capture or coefficient functionality was merged into primary firmware.

### Reproducible diagnostic causes

- `capture.ino` uses `ADCSRA`, `ADPS2`, `ADPS1`, `ADPS0`, `_SFR_BYTE`, and `_BV`.
  These AVR definitions are unavailable in ESP32 board headers. A0 is also a
  board-specific pin alias. Several editor errors can share this one board/core
  mismatch; their exact count cannot be established from source alone.
- Arduino automatically supplies core declarations during normal sketch builds.
  Generic C++ IntelliSense without board include paths can flag `Serial`, `micros`,
  `analogRead`, and `uint8_t` even when an Uno build succeeds. An explicit
  `Arduino.h` include helps identify the dependency but does not install/configure it.
- Primary ESP32 dependencies such as `WiFi.h`, `ESP_Mail_Client.h`, `esp_timer.h`,
  `esp_sntp.h`, and FreeRTOS headers require the selected ESP32 core and mail library.
  Unresolved headers in a generic host build are not proof of C++ logic errors.
- `capture_fft.py` expects nominal 5 V/10-bit capture samples, not ESP32 12-bit ADC
  values. Its `--no-plot` flag still requires Matplotlib because it saves a PNG.
- The active receiver's spectrum buffers/shared analysis state are preserved.
  Their real-time behavior, including possible buffer reuse if analysis takes too
  long, is not verified by notification host tests. Monitor the CSV `missed` count
  during network tests rather than treating host tests as an ADC timing guarantee.

### Validation from this inspection

- All **15 Python alert tests** and **2 primary notification host tests** passed.
- All seven Lab 2 Python sources parsed successfully.
- `capture.ino` passed an actual **Arduino Uno build** using bundled Arduino CLI
  1.3.1, Arduino AVR core 1.8.7, and the installed AVR toolchain: **2068 bytes flash,
  1422 bytes RAM**, with 626 bytes RAM remaining. No upload was performed.
- AVR compiler syntax checks passed with the Uno target; an unsupported MCU
  correctly triggered the explicit board guard. This does not reproduce the exact
  editor Problems list or prove ESP32 compilation.
- The supplied SOS header passed host C++ syntax checks and float32 pole/response
  checks. It was preserved without regeneration.
- `analyze()` recovered a 500 Hz sinusoid and the expected nominal amplitude from
  synthetic 10000 Hz / 1200-sample input using Anaconda's installed NumPy. These
  are simulated samples, not transmitter measurements or physical test results.
- The current `python3` lacks NumPy, Matplotlib, pyserial, and python-dotenv.
  Anaconda has NumPy and Matplotlib but lacks pyserial. Select/configure the intended
  interpreter before live Python capture; mock-based tests do not establish that
  these runtime dependencies are installed. For the supporting analysis tool,
  install `numpy matplotlib pyserial` into its selected virtual environment.
- MATLAB/Octave are unavailable. MATLAB generation was inspected but not executed.
  The installed Arduino packages include AVR and Renesas Uno, but no ESP32 core;
  ESP Mail Client was not found in the standard sketchbook library directory.
- `secrets.h` and `.env` are ignored and not tracked. A heuristic scan of nonignored
  Lab 2 source found no candidate hardcoded passwords/tokens. No credentials were
  read from local secret files or displayed, and no files were staged.

Before physical checkoff, install/select the ESP32 core and ESP Mail Client as
explained in the firmware guide, compile/upload only the primary ESP32 sketch,
configure local credentials, and test NTP/Central timestamps, one `t` test email,
one interruption/restoration, two interruptions less than ten seconds apart,
continuous blockage, and Wi-Fi failure/recovery. Verify LED/calibration/CSV/spectrum
behavior and sampling deadlines during delivery. Neither the Uno build nor host
tests establish primary ESP32 compilation, email receipt, or hardware performance.
