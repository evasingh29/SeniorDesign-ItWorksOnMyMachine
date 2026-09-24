"""Email alerting system for digital thermometer temperature threshold events."""

import datetime
import logging
import smtplib
import threading
from email.message import EmailMessage
from typing import Any, Dict, Optional, Tuple

from .config import Settings

logger = logging.getLogger("thermometer.alerts")


class EmailAlertManager:
    """Manages threshold checking, state-transition alerting, and asynchronous Gmail SMTP alerting."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()

        # In-memory configurable alert settings
        self.enabled: bool = settings.ALERT_ENABLED
        self.recipient_email: str = settings.ALERT_RECIPIENT_EMAIL
        self.min_temperature_c: Optional[float] = settings.ALERT_MIN_TEMP_C
        self.max_temperature_c: Optional[float] = settings.ALERT_MAX_TEMP_C
        self.low_message: str = settings.ALERT_LOW_MESSAGE
        self.high_message: str = settings.ALERT_HIGH_MESSAGE
        self.cooldown_seconds: int = settings.ALERT_COOLDOWN_SECONDS

        # State per sensor: "NORMAL", "HIGH", "LOW"
        self.sensor_states: Dict[int, str] = {1: "NORMAL", 2: "NORMAL"}

    def get_settings(self) -> Dict[str, Any]:
        """Return current alert configuration."""
        with self._lock:
            app_pwd = self.settings.cleaned_app_password
            return {
                "enabled": self.enabled,
                "recipient_email": self.recipient_email,
                "min_temperature_c": self.min_temperature_c,
                "max_temperature_c": self.max_temperature_c,
                "low_message": self.low_message,
                "high_message": self.high_message,
                "cooldown_seconds": self.cooldown_seconds,
                "smtp_sender": self.settings.SMTP_SENDER,
                "smtp_configured": bool(self.settings.SMTP_SENDER and app_pwd),
            }

    def update_settings(
        self,
        enabled: Optional[bool] = None,
        recipient_email: Optional[str] = None,
        min_temperature_c: Optional[float] = None,
        max_temperature_c: Optional[float] = None,
        low_message: Optional[str] = None,
        high_message: Optional[str] = None,
        cooldown_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Update configurable alert parameters."""
        with self._lock:
            if enabled is not None:
                self.enabled = enabled
            if recipient_email is not None:
                self.recipient_email = recipient_email.strip()
            if min_temperature_c is not None:
                self.min_temperature_c = min_temperature_c
            if max_temperature_c is not None:
                self.max_temperature_c = max_temperature_c
            if low_message is not None and low_message.strip():
                self.low_message = low_message.strip()
            if high_message is not None and high_message.strip():
                self.high_message = high_message.strip()
            if cooldown_seconds is not None:
                self.cooldown_seconds = max(1, cooldown_seconds)

        logger.info(
            f"Alert settings updated: enabled={self.enabled}, recipient='{self.recipient_email}', "
            f"min={self.min_temperature_c}°C, max={self.max_temperature_c}°C, "
            f"low_msg='{self.low_message}', high_msg='{self.high_message}'"
        )
        return self.get_settings()

    def format_alert_message(
        self,
        sensor_id: int,
        current_temp_c: float,
        threshold_type: str,
        threshold_val_c: float,
        custom_message: str,
    ) -> Tuple[str, str, str]:
        """
        Generate subject, plain text body, and HTML body clearly
        """
        sensor_rom = (
            self.settings.SENSOR_1_ADDRESS if sensor_id == 1 else self.settings.SENSOR_2_ADDRESS
        )
        current_temp_f = (current_temp_c * 9 / 5) + 32
        thresh_f = (threshold_val_c * 9 / 5) + 32
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        subject = (
            f"[TEMPERATURE ALERT] Sensor {sensor_id} {threshold_type.upper()} "
            f"Threshold Exceeded ({current_temp_c:.1f} °C)"
        )

        comparison_text = (
            f"exceeded maximum threshold of {threshold_val_c:.1f} °C ({thresh_f:.1f} °F)"
            if threshold_type.lower() == "maximum"
            else f"dropped below minimum threshold of {threshold_val_c:.1f} °C ({thresh_f:.1f} °F)"
        )

        body_text = (
            f"DIGITAL THERMOMETER ALERT NOTIFICATION\n"
            f"======================================\n\n"
            f"Message: {custom_message}\n\n"
            f"Triggering Sensor: Sensor {sensor_id}\n"
            f"Hardware ROM Address: {sensor_rom}\n"
            f"Alert Condition: {threshold_type.capitalize()} threshold crossed\n"
            f"Current Reading: {current_temp_c:.1f} °C ({current_temp_f:.1f} °F)\n"
            f"Threshold Setting: {threshold_val_c:.1f} °C ({thresh_f:.1f} °F)\n"
            f"Status: Temperature {comparison_text}\n"
            f"Timestamp: {now_str}\n\n"
            f"ECE:4880 Senior Design Thermometer Gateway\n"
        )

        body_html = (
            f"<!DOCTYPE html><html><body style='font-family: Arial, sans-serif; line-height: 1.6; color: #222;'>"
            f"<div style='max-width: 600px; margin: 0 auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;'>"
            f"<div style='background-color: #d62828; color: white; padding: 16px 20px; font-size: 18px; font-weight: bold;'>"
            f"⚠️ Temperature Alert: Sensor {sensor_id} Threshold Exceeded"
            f"</div>"
            f"<div style='padding: 20px;'>"
            f"<div style='background: #fff3f3; border-left: 4px solid #d62828; padding: 12px 16px; margin-bottom: 20px; font-size: 15px; font-weight: 500;'>"
            f"{custom_message}"
            f"</div>"
            f"<p>The digital thermometer system has detected an out-of-bounds temperature event:</p>"
            f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 20px;'>"
            f"<tr style='border-bottom: 1px solid #eee;'><td style='padding: 8px; font-weight: bold;'>Sensor:</td><td style='padding: 8px;'>Sensor {sensor_id}</td></tr>"
            f"<tr style='border-bottom: 1px solid #eee;'><td style='padding: 8px; font-weight: bold;'>Hardware Address:</td><td style='padding: 8px;'><code>{sensor_rom}</code></td></tr>"
            f"<tr style='border-bottom: 1px solid #eee;'><td style='padding: 8px; font-weight: bold;'>Current Temperature:</td><td style='padding: 8px; color: #d62828; font-size: 16px; font-weight: bold;'>{current_temp_c:.1f} °C ({current_temp_f:.1f} °F)</td></tr>"
            f"<tr style='border-bottom: 1px solid #eee;'><td style='padding: 8px; font-weight: bold;'>Threshold Crossed:</td><td style='padding: 8px;'>{threshold_type.capitalize()} ({threshold_val_c:.1f} °C / {thresh_f:.1f} °F)</td></tr>"
            f"<tr style='border-bottom: 1px solid #eee;'><td style='padding: 8px; font-weight: bold;'>Time:</td><td style='padding: 8px;'>{now_str}</td></tr>"
            f"</table>"
            f"<p style='color: #666; font-size: 13px;'>This is an automated notification from the ECE:4880 Digital Thermometer gateway.</p>"
            f"</div>"
            f"</div></body></html>"
        )

        return subject, body_text, body_html

    def send_smtp_email_sync(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Connect to Gmail SMTP and send an email.
        """
        app_password = self.settings.cleaned_app_password
        sender = self.settings.SMTP_SENDER

        if not app_password:
            err = "Cannot send email: Gmail app_password is not set in configuration."
            logger.error(err)
            return False, err

        if not to_email:
            err = "Cannot send email: recipient_email is empty."
            logger.error(err)
            return False, err

        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = sender
            msg["To"] = to_email
            msg.set_content(body_text)

            if body_html:
                msg.add_alternative(body_html, subtype="html")

            logger.info(f"Connecting to Gmail SMTP at {self.settings.SMTP_HOST}:{self.settings.SMTP_PORT}...")
            with smtplib.SMTP(self.settings.SMTP_HOST, self.settings.SMTP_PORT, timeout=12) as server:
                server.starttls()
                server.login(sender, app_password)
                server.send_message(msg)

            logger.info(f"Successfully sent alert email to {to_email}: '{subject}'")
            return True, f"Email sent successfully to {to_email}"
        except smtplib.SMTPAuthenticationError as e:
            err = f"Gmail SMTP authentication failed: {e}. Check app_password."
            logger.error(err)
            return False, err
        except Exception as e:
            err = f"Failed to send email via SMTP: {e}"
            logger.error(err)
            return False, err

    def send_email_async(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> None:
        """Dispatch email sending in a non-blocking background thread."""
        thread = threading.Thread(
            target=self.send_smtp_email_sync,
            args=(to_email, subject, body_text, body_html),
            daemon=True,
        )
        thread.start()

    def check_sample_and_alert(self, sample: Dict[str, Any]) -> None:
        """
        - Sends ONE email when entering HIGH or LOW state.
        - Does not repeatedly send while remaining in HIGH or LOW.
        - Maintains state independently for Sensor 1 and Sensor 2.
        """
        with self._lock:
            if not self.enabled or not self.recipient_email:
                return

            recipient = self.recipient_email
            min_thresh = self.min_temperature_c
            max_thresh = self.max_temperature_c
            high_msg = self.high_message
            low_msg = self.low_message

            sensors = [
                (1, sample.get("s1")),
                (2, sample.get("s2")),
            ]

            for sensor_id, sensor_data in sensors:
                # Missing or unplugged sensor data must NEVER trigger a temperature alert
                if not sensor_data or not sensor_data.get("ok"):
                    continue

                temp = sensor_data.get("c")
                if temp is None or not isinstance(temp, (int, float)):
                    continue

                prev_state = self.sensor_states.get(sensor_id, "NORMAL")

                # Check HIGH condition
                if max_thresh is not None and temp > max_thresh:
                    if prev_state != "HIGH":
                        self.sensor_states[sensor_id] = "HIGH"
                        subject, body_text, body_html = self.format_alert_message(
                            sensor_id=sensor_id,
                            current_temp_c=temp,
                            threshold_type="maximum",
                            threshold_val_c=max_thresh,
                            custom_message=high_msg,
                        )
                        logger.warning(
                            f"ALERT TRIGGERED: Sensor {sensor_id} entered HIGH state ({temp}°C > {max_thresh}°C)"
                        )
                        self.send_email_async(recipient, subject, body_text, body_html)

                # Check LOW condition
                elif min_thresh is not None and temp < min_thresh:
                    if prev_state != "LOW":
                        self.sensor_states[sensor_id] = "LOW"
                        subject, body_text, body_html = self.format_alert_message(
                            sensor_id=sensor_id,
                            current_temp_c=temp,
                            threshold_type="minimum",
                            threshold_val_c=min_thresh,
                            custom_message=low_msg,
                        )
                        logger.warning(
                            f"ALERT TRIGGERED: Sensor {sensor_id} entered LOW state ({temp}°C < {min_thresh}°C)"
                        )
                        self.send_email_async(recipient, subject, body_text, body_html)

                # Returned within bounds: NORMAL
                else:
                    if prev_state != "NORMAL":
                        logger.info(
                            f"Sensor {sensor_id} returned to NORMAL temperature range ({temp}°C)"
                        )
                        self.sensor_states[sensor_id] = "NORMAL"

    def send_test_email(self, to_email: Optional[str] = None) -> Tuple[bool, str]:
        """Send a test verification email to confirm SMTP connectivity."""
        target_email = to_email.strip() if to_email else self.recipient_email
        if not target_email:
            return False, "Recipient email address is required to send a test email."

        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        subject = "[TEST] Digital Thermometer Alert System Test"
        body_text = (
            f"This is a test message from your ECE:4880 Digital Thermometer Backend.\n\n"
            f"SMTP Sender: {self.settings.SMTP_SENDER}\n"
            f"Configured Recipient: {target_email}\n"
            f"Timestamp: {now_str}\n\n"
            f"If you received this email, temperature threshold alert notifications are working correctly."
        )
        body_html = (
            f"<!DOCTYPE html><html><body style='font-family: Arial, sans-serif; color: #222;'>"
            f"<div style='max-width: 500px; padding: 20px; border: 1px solid #ddd; border-radius: 8px;'>"
            f"<h2 style='color: #1d61c4; margin-top: 0;'>✅ Test Alert Successful</h2>"
            f"<p>This is a test notification from your <strong>ECE:4880 Digital Thermometer</strong> system.</p>"
            f"<p><strong>Sender:</strong> {self.settings.SMTP_SENDER}<br>"
            f"<strong>Recipient:</strong> {target_email}<br>"
            f"<strong>Time:</strong> {now_str}</p>"
            f"<p style='color: #555;'>Your email alert system is ready to deliver temperature threshold alerts.</p>"
            f"</div></body></html>"
        )

        return self.send_smtp_email_sync(target_email, subject, body_text, body_html)
