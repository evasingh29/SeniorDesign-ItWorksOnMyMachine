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

Three of Elif's emailed files are now present: `matlab/design_filter.m`,
`matlab/write_coeffs_header.m`, and `analysis/capture_fft.py`. The FFT script was
moved from `matlab/` into `analysis/`. No `elif_original/` folder is used.

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

## Missing files and integration limits

- **`capture.ino` is missing.** Live FFT capture expects a `c` command followed by
  `BEGIN <sample_rate> <count>`, one raw integer sample per line, and `END`. The
  current ESP32 receiver's CSV/spectrum protocol is different; do not upload or
  modify the active firmware merely to satisfy this script.
- **Elif's nonempty receiver implementation is missing.** The existing
  `firmware/receiver.ino` remains an empty placeholder.
- **`filter_coeffs.h` is absent.** The corrected MATLAB writer can produce it
  under `firmware/` after the design is reviewed and MATLAB is run; no placeholder
  coefficients have been invented. The active ESP32 firmware does not consume it.
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
host APIs; they are not an Arduino/ESP32 build or a hardware test. MATLAB execution requires MATLAB and Signal Processing Toolbox, which are not
available in this session; the missing alternative firmware cannot be tested. Live
receiver and email testing instructions are in the component READMEs.
