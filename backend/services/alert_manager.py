"""
Alert Manager for Agentium (Phase 9)
Handles system-wide alerts, notifications, and escalation to the appropriate channels.

Enhanced with:
- Email alerts (SMTP, optional)
- Webhook alerts (POST to configurable URL)
- CRITIC_VETO alert handling
- EMERGENCY severity support
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
import logging
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import httpx

from backend.models.entities.agents import Agent, AgentType
from backend.models.entities.monitoring import MonitoringAlert, ViolationSeverity
from backend.models.entities.channels import ExternalChannel, ChannelType
from backend.services.channel_manager import ChannelManager
from backend.core.config import settings

# NOTE: websocket_manager is imported lazily (inside methods) to avoid a circular import.
# backend.main imports db_maintenance → alert_manager, so importing backend.main here
# at module level causes: ImportError: cannot import name 'manager' from partially
# initialized module 'backend.main'.

logger = logging.getLogger(__name__)

# Extended alert types for Phase 9
ALERT_TYPE_CRITIC_VETO = "critic_veto"
ALERT_TYPE_EMERGENCY = "emergency"
ALERT_TYPE_ALL_KEYS_DOWN = "all_api_keys_down"


class AlertManager:
    """Central service for managing and dispatching system alerts."""

    def __init__(self, db: Session):
        """Init."""

        self.db = db
        self.channel_manager = ChannelManager()

    async def dispatch_alert(self, alert: MonitoringAlert):
        """Dispatch an alert to the configured channels based on severity."""

        # 1. Format the alert message
        message = self._format_alert_message(alert)
        logger.info(
            f"Dispatching Alert [{alert.severity.value}]: "
            f"{alert.alert_type} - {alert.message}"
        )

        # 2. Always broadcast critical/major/moderate alerts to WebSocket
        if alert.severity in [
            ViolationSeverity.CRITICAL,
            ViolationSeverity.MAJOR,
            ViolationSeverity.MODERATE,
        ]:
            await self._broadcast_websocket(alert, message)

        # 3. Route to external channels based on severity and configuration
        await self._notify_external_channels(alert, message)

        # 4. Send email alert for CRITICAL or EMERGENCY
        if alert.severity == ViolationSeverity.CRITICAL or alert.alert_type in [
            ALERT_TYPE_EMERGENCY,
            ALERT_TYPE_ALL_KEYS_DOWN,
        ]:
            await self._send_email_alert(alert, message)

        # 5. Send webhook alert for MAJOR+
        if alert.severity in [ViolationSeverity.MAJOR, ViolationSeverity.CRITICAL]:
            await self._send_webhook_alert(alert, message)

        # 6. Escalate to Head of Council / Sovereign if Critical
        if alert.severity == ViolationSeverity.CRITICAL:
            self._escalate_critical_alert(alert)

    def _format_alert_message(self, alert: MonitoringAlert) -> str:
        """Format an alert into a readable message string."""
        severity_icons = {
            ViolationSeverity.MINOR: "ℹ️",
            ViolationSeverity.MODERATE: "⚠️",
            ViolationSeverity.MAJOR: "🚨",
            ViolationSeverity.CRITICAL: "💀",
        }
        # String-based fallback for non-enum severity values
        severity_icons_by_value = {
            "minor": "ℹ️",
            "moderate": "⚠️",
            "major": "🚨",
            "critical": "💀",
        }
        icon = severity_icons.get(alert.severity)
        if icon is None:
            # Fallback: try matching by severity.value string
            sev_val = getattr(alert.severity, "value", str(alert.severity))
            icon = severity_icons_by_value.get(sev_val.lower() if isinstance(sev_val, str) else "", "🔔")

        # Special icons for extended alert types
        if alert.alert_type == ALERT_TYPE_CRITIC_VETO:
            icon = "🛑"
        elif alert.alert_type == ALERT_TYPE_EMERGENCY:
            icon = "🆘"
        elif alert.alert_type == ALERT_TYPE_ALL_KEYS_DOWN:
            icon = "🔑❌"

        timestamp = alert.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        return (
            f"{icon} **AGENTIUM SYSTEM ALERT: {alert.severity.value.upper()}**\n\n"
            f"Type: `{alert.alert_type}`\n"
            f"Time: {timestamp}\n"
            f"Message: {alert.message}\n"
            f"Detected By: `{alert.detected_by_agent_id}`\n"
            f"Affected Agent: `{alert.affected_agent_id or 'System-wide'}`"
        )

    async def _broadcast_websocket(self, alert: MonitoringAlert, message: str):
        """Broadcast alert to all connected WebSocket clients (Frontend Dashboard)."""
        try:
            # Lazy import to avoid circular dependency with backend.main
            from backend.main import manager as websocket_manager

            await websocket_manager.broadcast(
                {
                    "type": "system_alert",
                    "severity": alert.severity.value,
                    "alert_type": alert.alert_type,
                    "message": message,
                    "timestamp": alert.created_at.isoformat(),
                }
            )
        except Exception as e:
            logger.error(f"Failed to broadcast WebSocket alert: {e}")

    async def _notify_external_channels(
        self, alert: MonitoringAlert, message: str
    ):
        """Send alerts to configured external messaging channels."""
        # Notify channels for MAJOR, CRITICAL, and CRITIC_VETO alerts
        should_notify = alert.severity in [
            ViolationSeverity.MAJOR,
            ViolationSeverity.CRITICAL,
        ] or alert.alert_type in [
            ALERT_TYPE_CRITIC_VETO,
            ALERT_TYPE_EMERGENCY,
            ALERT_TYPE_ALL_KEYS_DOWN,
        ]
        if not should_notify:
            return

        try:
            # Fetch active channels
            active_channels = (
                self.db.query(ExternalChannel)
                .filter_by(status="active", is_active=True)
                .all()
            )

            for channel in active_channels:
                try:
                    if channel.channel_type == ChannelType.TELEGRAM:
                        asyncio.create_task(
                            self.channel_manager.send_telegram(
                                channel.channel_id, message
                            )
                        )
                    elif channel.channel_type == ChannelType.DISCORD:
                        asyncio.create_task(
                            self.channel_manager.send_discord(
                                channel.channel_id, message
                            )
                        )
                    elif channel.channel_type == ChannelType.SLACK:
                        asyncio.create_task(
                            self.channel_manager.send_slack(
                                channel.channel_id, message
                            )
                        )
                    elif channel.channel_type == ChannelType.WHATSAPP:
                        asyncio.create_task(
                            self.channel_manager.send_whatsapp(
                                channel.channel_id, message
                            )
                        )
                except Exception as channel_err:
                    logger.error(
                        f"Failed to send alert to channel "
                        f"{channel.id} ({channel.channel_type}): {channel_err}"
                    )
        except Exception as e:
            logger.error(f"Error querying channels for alerts: {e}")

    async def _send_email_alert(self, alert: MonitoringAlert, message: str):
        """
        Send email alert via SMTP.
        Skipped entirely if SMTP settings are not configured.
        Phase 9.1 enhancement.
        """
        if not settings.SMTP_HOST or not settings.ALERT_EMAIL_TO:
            return

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._send_email_sync, alert, message
            )
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")

    def _send_email_sync(self, alert: MonitoringAlert, message: str):
        """Synchronous SMTP send (run in executor thread)."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"[Agentium {alert.severity.value.upper()}] {alert.alert_type}"
        )
        msg["From"] = settings.SMTP_USER or "agentium@localhost"
        msg["To"] = settings.ALERT_EMAIL_TO

        # Plain text body
        plain_body = message.replace("**", "").replace("`", "")
        msg.attach(MIMEText(plain_body, "plain"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.ehlo()
            if settings.SMTP_PORT != 25:
                server.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(
                msg["From"], [settings.ALERT_EMAIL_TO], msg.as_string()
            )

        logger.info(
            f"Email alert sent to {settings.ALERT_EMAIL_TO} "
            f"for {alert.alert_type}"
        )

    async def _send_webhook_alert(self, alert: MonitoringAlert, message: str):
        """
        POST alert payload to configured webhook URL.
        Skipped if WEBHOOK_ALERT_URL is not set.
        Phase 9.1 enhancement.
        """
        if not settings.WEBHOOK_ALERT_URL:
            return

        payload = {
            "severity": alert.severity.value,
            "alert_type": alert.alert_type,
            "message": alert.message,
            "detected_by": alert.detected_by_agent_id,
            "affected_agent": alert.affected_agent_id,
            "timestamp": alert.created_at.isoformat(),
            "formatted_message": message,
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    settings.WEBHOOK_ALERT_URL, json=payload
                )
                if resp.status_code >= 400:
                    logger.error(
                        f"Webhook alert failed with status "
                        f"{resp.status_code}: {resp.text}"
                    )
                else:
                    logger.info(
                        f"Webhook alert dispatched to "
                        f"{settings.WEBHOOK_ALERT_URL}"
                    )
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")

    def _escalate_critical_alert(self, alert: MonitoringAlert):
        """Escalation protocol for critical system failures or constitutional violations."""
        # Find the Head of Council to associate the alert or trigger emergency subroutines
        head = self.db.query(Agent).filter_by(
            agent_type=AgentType.HEAD_OF_COUNCIL
        ).first()
        if head:
            logger.critical(
                f"Alert escalated to Head of Council "
                f"({head.agentium_id}): {alert.alert_type}"
            )


def get_alert_manager(db: Session) -> AlertManager:
    """Get alert manager."""

    return AlertManager(db)