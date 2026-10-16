"""Grab a burst of samples from capture.ino and find the dominant frequencies.

Run these commands from Lab 2/. Live capture requires supporting firmware/capture.ino
on a classic AVR Uno/Nano (not the primary ESP32 receiver):
    python analysis/capture_fft.py --label transmitter_30cm
    python analysis/capture_fft.py --port /dev/cu.usbmodem14101 --label lamp

Re-analyze a saved capture:
    python analysis/capture_fft.py --csv data/lamp_2026-10-12_1530.csv

Each capture is saved to data/<label>_<timestamp>.csv and the plot to docs/,
so it can go straight into the report.
"""
import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"


def find_port():
    from serial.tools import list_ports
    ports = [p.device for p in list_ports.comports()
             if any(k in (p.description or "") + p.device for k in ("Arduino", "usbmodem", "usbserial", "ttyACM", "ttyUSB", "CH340"))]
    if not ports:
        raise SystemExit("No Arduino found. Pass --port (see Arduino IDE > Tools > Port).")
    return ports[0]


def capture(port, baud=115200, timeout=10):
    import serial
    with serial.Serial(port, baud, timeout=1) as ser:
        time.sleep(2)  # Arduino resets when the port opens
        ser.reset_input_buffer()
        ser.write(b"c")
        fs, samples, started = None, [], False
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = ser.readline().decode(errors="ignore").strip()
            if line.startswith("BEGIN"):
                _, fs, _ = line.split()
                fs, started = int(fs), True
            elif line == "END" and started:
                return fs, np.array(samples, dtype=float)
            elif started and line.isdigit():
                samples.append(int(line))
    raise SystemExit("Timed out waiting for capture. Is capture.ino uploaded?")


def save_csv(fs, samples, label):
    DATA.mkdir(exist_ok=True)
    path = DATA / f"{label}_{datetime.now():%Y-%m-%d_%H%M%S}.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["fs_hz", fs])
        w.writerow(["sample"])
        w.writerows([[int(s)] for s in samples])
    return path


def load_csv(path):
    with open(path) as f:
        rows = list(csv.reader(f))
    return int(rows[0][1]), np.array([float(r[0]) for r in rows[2:]])


def analyze(fs, samples, n_peaks=5):
    volts = samples * 5.0 / 1023.0
    x = volts - volts.mean()
    win = np.hanning(len(x))
    spec = np.abs(np.fft.rfft(x * win)) * 2 / win.sum()
    freqs = np.fft.rfftfreq(len(x), 1 / fs)
    spec[freqs < 20] = 0  # ignore DC / very slow drift
    idx = np.argsort(spec)[::-1]
    peaks = []
    for i in idx:
        if all(abs(freqs[i] - f) > 3 * fs / len(x) for f, _ in peaks):
            peaks.append((freqs[i], spec[i]))
        if len(peaks) == n_peaks:
            break
    return volts, freqs, spec, peaks


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port")
    p.add_argument("--csv", help="analyze a saved capture instead of capturing")
    p.add_argument("--label", default="capture", help="name for the saved files")
    p.add_argument("--no-plot", action="store_true")
    a = p.parse_args()

    if a.csv:
        fs, samples = load_csv(a.csv)
        label = Path(a.csv).stem
    else:
        fs, samples = capture(a.port or find_port())
        path = save_csv(fs, samples, a.label)
        label = path.stem
        print(f"Saved {path.relative_to(ROOT)}")

    volts, freqs, spec, peaks = analyze(fs, samples)
    print(f"\n{len(samples)} samples at {fs} Hz  ->  resolution {fs/len(samples):.1f} Hz")
    print(f"Signal: min {volts.min():.3f} V, max {volts.max():.3f} V, mean {volts.mean():.3f} V")
    print("\nStrongest frequencies:")
    for f, amp in peaks:
        print(f"  {f:8.1f} Hz   {amp*1000:7.2f} mV")
    if peaks:
        f0 = peaks[0][0]
        harmonics = [f for f, _ in peaks[1:] if abs(f / f0 - round(f / f0)) < 0.05 and round(f / f0) > 1]
        if harmonics:
            print(f"  (looks like a square wave at {f0:.1f} Hz, harmonics at {', '.join(f'{h:.0f}' for h in harmonics)})")

    import matplotlib
    if a.no_plot:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t = np.arange(len(volts)) / fs * 1000
    fig, ax = plt.subplots(2, 1, figsize=(9, 6))
    ax[0].plot(t, volts, lw=0.7)
    ax[0].set(xlabel="Time (ms)", ylabel="Voltage (V)", title=f"{label}: raw signal")
    ax[1].plot(freqs, spec * 1000, lw=0.7)
    for f, amp in peaks[:3]:
        ax[1].annotate(f"{f:.0f} Hz", (f, amp * 1000), textcoords="offset points", xytext=(4, 4), fontsize=8)
    ax[1].set(xlabel="Frequency (Hz)", ylabel="Amplitude (mV)", title="Spectrum")
    for axis in ax:
        axis.grid(alpha=0.3)
    fig.tight_layout()
    DOCS.mkdir(exist_ok=True)
    out = DOCS / f"{label}.png"
    fig.savefig(out, dpi=130)
    print(f"\nSaved plot {out.relative_to(ROOT)}")
    if not a.no_plot:
        plt.show()


if __name__ == "__main__":
    main()
