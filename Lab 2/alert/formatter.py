"""Alert text shared by all notification transports."""
from datetime import datetime


def format_alert(timestamp: datetime) -> str:
    """Use the event's local time, a 12-hour clock, and numeric calendar date."""
    period = "AM" if timestamp.hour < 12 else "PM"
    return (f"Critical Safety Event at {timestamp.hour % 12 or 12:02d}:"
            f"{timestamp.minute:02d} {period} on "
            f"{timestamp.month:02d}/{timestamp.day:02d}/{timestamp.year:04d}")
