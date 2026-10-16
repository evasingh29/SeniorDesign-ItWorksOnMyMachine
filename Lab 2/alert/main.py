"""USB serial integration for the receiver's existing beam-state protocol."""
import argparse
from datetime import datetime
import logging
import math
import os
from pathlib import Path
import time

from formatter import format_alert
from notifier import NotificationWorker, build_transports

LOG = logging.getLogger(__name__)
BAUD = 115200


def parse_line(line):
    """Return (kind, payload), or None for malformed/unknown messages."""
    parts = line.strip().split()
    if not parts:
        return None
    kind = parts[0]
    if kind in {"BREACH", "CLEAR"} and len(parts) == 1:
        return kind, None
    if kind == "ENV" and len(parts) == 2:
        try:
            value = float(parts[1])
            if math.isfinite(value):
                return kind, value
        except ValueError:
            pass
    if kind == "MISSED" and len(parts) == 2 and parts[1].isascii() and parts[1].isdigit():
        return kind, int(parts[1])
    if kind == "READY" and len(parts) >= 3:
        values = dict(part.split("=", 1) for part in parts[1:] if "=" in part)
        if values.get("FS") and values.get("sections"):
            return kind, " ".join(parts[1:])
    return None


class EventProcessor:
    def __init__(self, notifier, clock=None):
        self.notifier = notifier
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.active = False

    def process(self, line):
        parsed = parse_line(line)
        if parsed is None:
            LOG.warning("Ignored serial message: %r", line)
            return
        kind, value = parsed
        if kind == "BREACH":
            if not self.active:
                self.active = True
                message = format_alert(self.clock())
                LOG.warning("Breach: %s", message)
                self.notifier.submit(message)
            else:
                LOG.debug("Duplicate BREACH suppressed")
        elif kind == "CLEAR":
            LOG.info("Beam restored (previously active=%s)", self.active)
            self.active = False
        else:
            LOG.info("Receiver %s %s", kind, value)


def discover_port():
    from serial.tools import list_ports
    candidates = [p.device for p in list_ports.comports()
                  if p.vid is not None or "usb" in p.device.lower()]
    if len(candidates) != 1:
        raise ValueError(f"Expected one USB serial device; found {candidates}. Use --port.")
    return candidates[0]


def run_serial(processor, port=None):
    import serial
    while True:
        try:
            device = port or discover_port()
            LOG.info("Connecting to %s at %d baud", device, BAUD)
            with serial.Serial(device, BAUD, timeout=1) as connection:
                buffer = bytearray()
                while True:
                    chunk = connection.read(256)
                    buffer.extend(chunk)
                    while b"\n" in buffer:
                        line, _, remainder = buffer.partition(b"\n")
                        buffer = bytearray(remainder)
                        processor.process(line.decode("ascii", errors="replace"))
                    if len(buffer) > 4096:
                        LOG.warning("Discarded oversized serial line")
                        buffer.clear()
        except (serial.SerialException, OSError, ValueError) as exc:
            LOG.warning("Serial unavailable (%s); retrying in 2 seconds", exc)
            # Preserve active state across reconnects to suppress duplicate alarms.
            time.sleep(2)


def simulate(processor):
    print("Enter b/BREACH, c/CLEAR, any receiver line, or q to quit.")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            return
        if line.lower() in {"q", "quit"}:
            return
        processor.process({"b": "BREACH", "c": "CLEAR"}.get(line.lower(), line))


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).with_name(".env"))
    except ImportError:
        pass  # Exported environment variables also work without python-dotenv.
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--simulate", action="store_true")
    modes.add_argument("--test-email", action="store_true",
                       help="Send one SMTP test email and exit without opening serial")
    parser.add_argument("--port", default=os.getenv("SERIAL_PORT") or None)
    parser.add_argument("--list-ports", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(
                            os.getenv("ALERT_LOG", str(Path(__file__).with_name("alert.log"))))])
    if args.list_ports:
        from serial.tools import list_ports
        for port in list_ports.comports():
            print(f"{port.device}: {port.description}")
        return
    if args.test_email:
        try:
            transports = build_transports("smtp")
            message = format_alert(datetime.now().astimezone())
            transports[0][1](message)
        except Exception as exc:
            LOG.error("Test email failed error=%s (check SMTP settings and App Password)",
                      type(exc).__name__)
            raise SystemExit(1) from None
        LOG.info("Test email accepted by SMTP server; check the recipient inbox/spam folder")
        return
    try:
        worker = NotificationWorker(build_transports())
    except (KeyError, ValueError) as exc:
        parser.error("Invalid notification configuration; check environment settings and App Password")
    try:
        processor = EventProcessor(worker)
        if args.simulate:
            simulate(processor)
        else:
            run_serial(processor, args.port)
    except KeyboardInterrupt:
        LOG.info("Stopping")
    finally:
        worker.close()


if __name__ == "__main__":
    main()
