"""Environment-configured transports and nonblocking delivery worker."""
import logging
import os
import queue
import smtplib
import ssl
import threading
from email.message import EmailMessage
from urllib.request import Request, urlopen

LOG = logging.getLogger(__name__)


def build_transports(channels=None):
    transports = []
    for name in dict.fromkeys((channels if channels is not None else os.getenv("ALERT_CHANNELS", "smtp")).split(",")):
        name = name.strip().lower()
        if name == "console":
            def console(message):
                print(message, flush=True)
            transports.append((name, console))
        elif name == "smtp":
            host = os.getenv("SMTP_HOST", "smtp.gmail.com")
            sender = os.environ["SMTP_FROM"]
            recipients = [x.strip() for x in os.environ["SMTP_TO"].split(",") if x.strip()]
            if not host or not sender or not recipients:
                raise ValueError("SMTP_HOST, SMTP_FROM and SMTP_TO must be nonempty")
            security = os.getenv("SMTP_SECURITY", "ssl").lower()
            if security not in {"starttls", "ssl"}:
                raise ValueError("SMTP_SECURITY must be starttls or ssl")
            port = int(os.getenv("SMTP_PORT", "465" if security == "ssl" else "587"))
            username, password = os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD")
            if host.lower() == "smtp.gmail.com":
                if security != "ssl" or port != 465:
                    raise ValueError("Gmail requires SSL on port 465 in this subsystem")
                if not username or not password:
                    raise ValueError("Gmail requires SMTP_USERNAME and a Google App Password in SMTP_PASSWORD")
            def smtp(message):
                mail = EmailMessage()
                mail["Subject"] = message
                mail["From"] = sender
                mail["To"] = ", ".join(recipients)
                mail.set_content(message)
                context = ssl.create_default_context()
                connection = (smtplib.SMTP_SSL(host, port, timeout=10, context=context)
                              if security == "ssl" else smtplib.SMTP(host, port, timeout=10))
                with connection as client:
                    if security == "starttls":
                        client.starttls(context=context)
                    if username:
                        client.login(username, password or "")
                    refused = client.send_message(mail)
                    if refused:
                        raise RuntimeError("SMTP rejected one or more recipients")
            transports.append((name, smtp))
        elif name == "ntfy":
            url = os.environ["NTFY_URL"]
            if not url.startswith("https://"):
                raise ValueError("NTFY_URL must use HTTPS")
            token = os.getenv("NTFY_TOKEN")
            def ntfy(message):
                headers = {"Content-Type": "text/plain; charset=utf-8"}
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                with urlopen(Request(url, data=message.encode(), headers=headers), timeout=10) as response:
                    response.read()
            transports.append((name, ntfy))
        else:
            raise ValueError(f"Unknown notification channel: {name}")
    return transports


class NotificationWorker:
    """One queued attempt per event/channel; failed sends never stop later events."""
    def __init__(self, transports):
        self.transports = transports
        self.pending = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def submit(self, message):
        self.pending.put(message)

    def _run(self):
        while True:
            message = self.pending.get()
            try:
                if message is None:
                    return
                for name, send in self.transports:
                    try:
                        send(message)
                        LOG.info("Delivery successful channel=%s event=%s", name, message)
                    except Exception as exc:
                        # Log the exception class, not potentially credential-bearing URLs.
                        LOG.error("Delivery failed channel=%s error=%s event=%s",
                                  name, type(exc).__name__, message)
            finally:
                self.pending.task_done()

    def close(self, timeout=35):
        self.pending.put(None)
        self.thread.join(timeout)
        if self.thread.is_alive():
            LOG.warning("Shutdown timeout: queued deliveries may be lost")
