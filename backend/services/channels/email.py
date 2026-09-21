"""Email (SMTP/IMAP) adapter."""
import logging
from typing import Dict, Any
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate

from .base import BaseChannelAdapter
from backend.models.entities.channels import ExternalMessage

logger = logging.getLogger(__name__)

class EmailAdapter(BaseChannelAdapter):
    """
    Adapter for Email (SMTP send / IMAP receive).
    """

    async def send_message(self, message: ExternalMessage) -> bool:
        """
        Send an email message via SMTP.
        """
        config = self.config

        # Extract SMTP configuration
        smtp_host = config.get("smtp_host")
        smtp_port = config.get("smtp_port", 587)
        smtp_user = config.get("smtp_user")
        smtp_pass = config.get("smtp_pass")
        from_email = config.get("from_email", smtp_user)
        to_email = message.sender_id  # In email context, sender_id is recipient email

        if not all([smtp_host, smtp_user, smtp_pass, to_email]):
            logger.error(f"[Email] Missing configuration for channel {self.channel.id}")
            return False

        # Create message
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Date'] = formatdate(localtime=True)
        msg['Subject'] = "Agentium Message"  # Could be made configurable

        msg.attach(MIMEText(message.content, 'plain'))

        try:
            # Connect to SMTP server
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()  # Enable TLS encryption
            server.login(smtp_user, smtp_pass)

            # Send email
            text = msg.as_string()
            server.sendmail(from_email, to_email, text)
            server.quit()

            return True
        except Exception as e:
            logger.error(f"[Email] Exception sending message: {e}")
            return False

    # Note: Receiving emails via IMAP would typically be handled by a background task
    # or a separate service that polls the IMAP folder and creates ExternalMessage objects
    # For verification purposes, we'll focus on sending capability

    async def validate_config(self) -> bool:
        """Validate config."""
        required_fields = ["smtp_host", "smtp_user", "smtp_pass", "from_email"]
        return all(field in self.config for field in required_fields)