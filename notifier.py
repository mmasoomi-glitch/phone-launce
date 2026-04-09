import smtplib
import logging
from email.mime.text import MIMEText
from datetime import datetime

logger = logging.getLogger(__name__)


def send_notification(config, phone_ip, public_url=None):
    """Send a Gmail notification that the phone has connected."""
    try:
        base = public_url if public_url else "ngrok URL unavailable"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        subject = "Phone Connected to WiFi"
        body = (
            f"Your phone connected to the network.\n\n"
            f"  Time:       {now}\n"
            f"  Phone IP:   {phone_ip}\n"
            f"  Phone MAC:  {config['phone_mac']}\n\n"
            f"Remote Access:\n"
            f"  PC Desktop: {base}/access\n"
            f"  Phone:      {base}/phone\n"
        )

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = config["gmail_sender"]
        msg["To"] = config["gmail_recipient"]

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(config["gmail_sender"], config["gmail_app_password"])
            server.sendmail(config["gmail_sender"], config["gmail_recipient"], msg.as_string())

        logger.info(f"Email notification sent to {config['gmail_recipient']}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
