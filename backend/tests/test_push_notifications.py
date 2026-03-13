"""
Tests for Phase 11.4 Push Notification delivery.
Covers FCM/APNs dispatching, quiet-hours enforcement, and preference filtering.
"""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock, PropertyMock

from backend.models.entities.mobile import DeviceToken, NotificationPreference
from backend.services.push_notification_service import PushNotificationService


class MockDB:
    def __init__(self):
        self._adds = []
        self._cache = []

    def add(self, entity):
        self._adds.append(entity)
        self._cache.append(entity)

    def commit(self):
        pass

    def refresh(self, entity):
        pass

    def query(self, model):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query

        def mock_first():
            for c in self._cache:
                if isinstance(c, model):
                    return c
            return None

        def mock_all():
            return [c for c in self._cache if isinstance(c, model)]

        mock_query.first = mock_first
        mock_query.all = mock_all
        return mock_query


def test_quiet_hours_blocks_during_quiet():
    """Push should be suppressed during configured quiet hours."""
    pref = NotificationPreference(
        user_id="u1",
        quiet_hours_start="00:00",
        quiet_hours_end="23:59",  # All day quiet
    )
    assert PushNotificationService._should_send(pref) is False


def test_quiet_hours_allows_outside_quiet():
    """Push should be allowed outside quiet hours."""
    pref = NotificationPreference(
        user_id="u1",
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    assert PushNotificationService._should_send(pref) is True


def test_preference_filtering_vote_disabled():
    """Vote alerts should be skipped when votes_enabled is False."""
    db = MockDB()
    pref = NotificationPreference(user_id="u1", votes_enabled=False)
    db.add(pref)

    count = PushNotificationService.send_vote_alert(
        db, "u1", {"description": "Test vote"}
    )
    assert count == 0


def test_preference_filtering_constitutional_disabled():
    """Constitutional alerts should be skipped when constitutional_enabled is False."""
    db = MockDB()
    pref = NotificationPreference(user_id="u1", constitutional_enabled=False)
    db.add(pref)

    count = PushNotificationService.send_constitutional_alert(
        db, "u1", {"severity": "WARNING", "message": "Test alert"}
    )
    assert count == 0


def test_fcm_simulated_delivery():
    """When FCM_SERVER_KEY is not set, FCM delivery should simulate and return token count."""
    tokens = ["token-android-1", "token-android-2"]
    count = PushNotificationService._deliver_fcm(tokens, "Test", "Body")
    assert count == 2


def test_apns_simulated_delivery():
    """When APNS credentials are not set, APNs delivery should simulate and return token count."""
    tokens = ["token-ios-1"]
    count = PushNotificationService._deliver_apns(tokens, "Test", "Body")
    assert count == 1


def test_send_push_routes_by_platform():
    """send_push should route to FCM for android tokens and APNs for iOS tokens."""
    db = MockDB()

    # Create preference (no quiet hours)
    pref = NotificationPreference(user_id="u1")
    db.add(pref)

    # Create devices
    android_device = DeviceToken(user_id="u1", platform="android", token="fcm-tok-1", is_active=True)
    ios_device = DeviceToken(user_id="u1", platform="ios", token="apns-tok-1", is_active=True)
    db.add(android_device)
    db.add(ios_device)

    count = PushNotificationService.send_push(db, "u1", "Hello", "World")
    assert count == 2  # Both simulated
