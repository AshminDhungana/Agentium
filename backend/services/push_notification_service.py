"""
Push Notification Service (Phase 11.4)
======================================
Handles device token management, notification preferences, and push alert
dispatch for mobile clients (iOS / Android).

Push delivery is simulated when FCM_SERVER_KEY / APNS credentials are not
configured.  When credentials are present the service is ready to integrate
with Firebase Admin SDK (FCM) or Apple Push Notification service (APNs).
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import logging
import json

from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.models.entities.mobile import DeviceToken, NotificationPreference
from backend.models.entities.user import User
from backend.core.config import settings

logger = logging.getLogger(__name__)


class PushNotificationService:

    # ── Device Token Management ────────────────────────────────────────────

    @staticmethod
    def register_device(
        db: Session, user: User, platform: str, token: str
    ) -> DeviceToken:
        """Register a new device token for a user."""
        if platform not in ["ios", "android"]:
            raise HTTPException(status_code=400, detail="Invalid platform. Must be 'ios' or 'android'.")

        device = db.query(DeviceToken).filter(DeviceToken.token == token).first()

        if device:
            device.user_id = user.id
            device.platform = platform
            device.is_active = True
            device.last_used_at = datetime.utcnow()
        else:
            device = DeviceToken(
                user_id=user.id,
                platform=platform,
                token=token,
                is_active=True,
                last_used_at=datetime.utcnow()
            )
            db.add(device)

        db.commit()
        db.refresh(device)
        return device

    @staticmethod
    def unregister_device(db: Session, user: User, token: str) -> None:
        """Unregister a device token."""
        device = db.query(DeviceToken).filter(
            DeviceToken.token == token,
            DeviceToken.user_id == user.id
        ).first()

        if not device:
            raise HTTPException(status_code=404, detail="Device token not found.")

        device.is_active = False
        db.commit()

    @staticmethod
    def get_user_tokens(db: Session, user_id: str) -> List[str]:
        """Get all active tokens for a user."""
        devices = db.query(DeviceToken).filter(
            DeviceToken.user_id == user_id,
            DeviceToken.is_active == True
        ).all()
        return [d.token for d in devices]

    # ── Notification Preferences ───────────────────────────────────────────

    @staticmethod
    def get_preferences(db: Session, user_id: str) -> NotificationPreference:
        """Get (or create default) notification preferences for a user."""
        pref = db.query(NotificationPreference).filter(
            NotificationPreference.user_id == user_id
        ).first()
        if not pref:
            pref = NotificationPreference(user_id=user_id)
            db.add(pref)
            db.commit()
            db.refresh(pref)
        return pref

    @staticmethod
    def update_preferences(
        db: Session,
        user_id: str,
        votes_enabled: Optional[bool] = None,
        alerts_enabled: Optional[bool] = None,
        tasks_enabled: Optional[bool] = None,
        constitutional_enabled: Optional[bool] = None,
        quiet_hours_start: Optional[str] = None,
        quiet_hours_end: Optional[str] = None,
    ) -> NotificationPreference:
        """Update notification preferences for a user."""
        pref = PushNotificationService.get_preferences(db, user_id)
        if votes_enabled is not None:
            pref.votes_enabled = votes_enabled
        if alerts_enabled is not None:
            pref.alerts_enabled = alerts_enabled
        if tasks_enabled is not None:
            pref.tasks_enabled = tasks_enabled
        if constitutional_enabled is not None:
            pref.constitutional_enabled = constitutional_enabled
        if quiet_hours_start is not None:
            pref.quiet_hours_start = quiet_hours_start
        if quiet_hours_end is not None:
            pref.quiet_hours_end = quiet_hours_end
        db.commit()
        db.refresh(pref)
        return pref

    @staticmethod
    def _should_send(pref: NotificationPreference) -> bool:
        """
        Checks quiet hours. Returns False if the current time falls
        within the user's configured quiet hours.
        """
        if not pref.quiet_hours_start or not pref.quiet_hours_end:
            return True
        try:
            now = datetime.utcnow()
            start_h, start_m = map(int, pref.quiet_hours_start.split(":"))
            end_h, end_m = map(int, pref.quiet_hours_end.split(":"))
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m
            now_minutes = now.hour * 60 + now.minute

            if start_minutes <= end_minutes:
                return not (start_minutes <= now_minutes <= end_minutes)
            else:  # wraps midnight
                return not (now_minutes >= start_minutes or now_minutes <= end_minutes)
        except Exception:
            return True

    @staticmethod
    def _deliver_fcm(tokens: List[str], title: str, body: str, data: Optional[dict] = None) -> int:
        """
        Deliver push notification via Firebase Cloud Messaging.
        Requires settings.FCM_SERVER_KEY to be configured.
        Falls back to log-only when credentials are missing.
        """
        if not getattr(settings, 'FCM_SERVER_KEY', None):
            logger.info(f"[FCM SIMULATED] → {len(tokens)} devices | {title}: {body}")
            return len(tokens)

        try:
            import httpx
            delivered = 0
            for token in tokens:
                payload = {
                    "to": token,
                    "notification": {"title": title, "body": body},
                    "data": data or {}
                }
                resp = httpx.post(
                    "https://fcm.googleapis.com/fcm/send",
                    json=payload,
                    headers={
                        "Authorization": f"key={settings.FCM_SERVER_KEY}",
                        "Content-Type": "application/json"
                    },
                    timeout=10
                )
                if resp.status_code == 200:
                    delivered += 1
                else:
                    logger.warning(f"FCM delivery failed for token {token[:12]}...: {resp.status_code}")
            return delivered
        except Exception as e:
            logger.error(f"FCM delivery error: {e}")
            return 0

    @staticmethod
    def _deliver_apns(tokens: List[str], title: str, body: str, data: Optional[dict] = None) -> int:
        """
        Deliver push notification via Apple Push Notification service.
        Requires settings.APNS_KEY_ID and settings.APNS_TEAM_ID.
        Falls back to log-only when credentials are missing.
        """
        apns_key_id = getattr(settings, 'APNS_KEY_ID', None)
        apns_team_id = getattr(settings, 'APNS_TEAM_ID', None)
        apns_key_path = getattr(settings, 'APNS_KEY_PATH', None)

        if not apns_key_id or not apns_team_id:
            logger.info(f"[APNs SIMULATED] → {len(tokens)} devices | {title}: {body}")
            return len(tokens)

        try:
            import httpx
            import jwt
            import time

            # Read the APNs auth key
            with open(apns_key_path, 'r') as f:
                auth_key = f.read()

            # Generate JWT for APNs
            token_payload = {
                "iss": apns_team_id,
                "iat": int(time.time())
            }
            apns_token = jwt.encode(token_payload, auth_key, algorithm="ES256", headers={"kid": apns_key_id})

            delivered = 0
            for device_token in tokens:
                apns_payload = {
                    "aps": {
                        "alert": {"title": title, "body": body},
                        "sound": "default"
                    }
                }
                if data:
                    apns_payload.update(data)

                resp = httpx.post(
                    f"https://api.push.apple.com/3/device/{device_token}",
                    json=apns_payload,
                    headers={
                        "authorization": f"bearer {apns_token}",
                        "apns-topic": getattr(settings, 'APNS_BUNDLE_ID', 'com.agentium.app'),
                    },
                    timeout=10
                )
                if resp.status_code == 200:
                    delivered += 1
                else:
                    logger.warning(f"APNs delivery failed for token {device_token[:12]}...: {resp.status_code}")
            return delivered
        except Exception as e:
            logger.error(f"APNs delivery error: {e}")
            return 0

    @staticmethod
    def send_push(db: Session, user_id: str, title: str, body: str, data: Optional[dict] = None) -> int:
        """
        Send a push notification to all active devices for a user.
        Routes to FCM (Android) or APNs (iOS) based on device platform.
        Respects quiet hours.
        """
        # Check quiet hours
        pref = PushNotificationService.get_preferences(db, user_id)
        if not PushNotificationService._should_send(pref):
            logger.info(f"Push suppressed for user {user_id} (quiet hours)")
            return 0

        devices = db.query(DeviceToken).filter(
            DeviceToken.user_id == user_id,
            DeviceToken.is_active == True
        ).all()

        if not devices:
            return 0

        android_tokens = [d.token for d in devices if d.platform == 'android']
        ios_tokens = [d.token for d in devices if d.platform == 'ios']

        delivered = 0
        if android_tokens:
            delivered += PushNotificationService._deliver_fcm(android_tokens, title, body, data)
        if ios_tokens:
            delivered += PushNotificationService._deliver_apns(ios_tokens, title, body, data)

        logger.info(f"Push sent to {delivered}/{len(devices)} devices for user {user_id}")
        return delivered

    @staticmethod
    def send_vote_alert(db: Session, user_id: str, vote_data: Dict[str, Any]) -> int:
        """Send a push notification for a new vote. Respects notification preferences."""
        pref = PushNotificationService.get_preferences(db, user_id)
        if not pref.votes_enabled:
            return 0
        title = "New Vote Initiated"
        body = vote_data.get("description", "A new vote requires your attention.")
        return PushNotificationService.send_push(db, user_id, title, body, data=vote_data)

    @staticmethod
    def send_constitutional_alert(db: Session, user_id: str, alert_data: Dict[str, Any]) -> int:
        """Send a push for a constitutional violation alert. Respects notification preferences."""
        pref = PushNotificationService.get_preferences(db, user_id)
        if not pref.constitutional_enabled:
            return 0
        severity = alert_data.get("severity", "WARNING")
        title = f"Constitutional Alert ({severity})"
        body = alert_data.get("message", "A constitutional event occurred.")
        return PushNotificationService.send_push(db, user_id, title, body, data=alert_data)

    @staticmethod
    def send_task_update(db: Session, user_id: str, task_data: Dict[str, Any]) -> int:
        """Send a push for a task status change. Respects notification preferences."""
        pref = PushNotificationService.get_preferences(db, user_id)
        if not pref.tasks_enabled:
            return 0
        task_status = task_data.get("status", "updated")
        title = f"Task {task_status.capitalize()}"
        body = task_data.get("description", "A task has been updated.")[:100]
        return PushNotificationService.send_push(db, user_id, title, body, data=task_data)

    # ── Maintenance ────────────────────────────────────────────────────────

    @staticmethod
    def cleanup_stale_tokens(db: Session, days_stale: int = 180) -> int:
        """Mark tokens as inactive if they haven't been used recently."""
        cutoff_date = datetime.utcnow() - timedelta(days=days_stale)
        stale_devices = db.query(DeviceToken).filter(
            DeviceToken.is_active == True,
            DeviceToken.last_used_at < cutoff_date
        ).all()

        for device in stale_devices:
            device.is_active = False

        if stale_devices:
            db.commit()

        return len(stale_devices)
