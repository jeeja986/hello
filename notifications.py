import os
import smtplib
from email.mime.text import MIMEText
from typing import Optional

from twilio.rest import Client


class Notifier:
    def __init__(self, config) -> None:
        self.config = config

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        if not to_email or not self.config.MAIL_USERNAME:
            return False
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self.config.MAIL_FROM or self.config.MAIL_USERNAME
        msg["To"] = to_email
        try:
            with smtplib.SMTP(self.config.MAIL_SERVER, self.config.MAIL_PORT) as server:
                if self.config.MAIL_USE_TLS:
                    server.starttls()
                if self.config.MAIL_USERNAME and self.config.MAIL_PASSWORD:
                    server.login(self.config.MAIL_USERNAME, self.config.MAIL_PASSWORD)
                server.send_message(msg)
            return True
        except Exception:
            return False

    def send_whatsapp(self, to_number: str, message: str) -> bool:
        if not to_number or not (self.config.TWILIO_ACCOUNT_SID and self.config.TWILIO_AUTH_TOKEN):
            return False
        try:
            client = Client(self.config.TWILIO_ACCOUNT_SID, self.config.TWILIO_AUTH_TOKEN)
            to_formatted = to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}"
            client.messages.create(
                from_=self.config.TWILIO_WHATSAPP_FROM,
                to=to_formatted,
                body=message,
            )
            return True
        except Exception:
            return False