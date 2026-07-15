"""
Tests for GET /ws/genesis-status precedence (Spec §3, P9).

Uses monkeypatched get_fresh_db + Redis so no live services are required.
"""
import json
from unittest.mock import patch, MagicMock

import pytest

from backend.api.routes import websocket as ws


@pytest.fixture
def fake_redis():
    r = MagicMock()
    r.get.return_value = None
    return r


def _make_head_query(exists: bool):
    head = MagicMock()
    head.first.return_value = (object() if exists else None)
    return head


def _db_side_effect(head_q, cfg_q):
    def _eff(*a, **k):
        sig = str(a)
        if "HeadOfCouncil" in sig:
            return head_q
        return cfg_q
    return _eff


async def test_complete_when_head_exists(fake_redis):
    with patch.object(ws, "get_fresh_db") as gdb, \
         patch("backend.core.redis.get_redis_client", lambda: fake_redis):
        db = MagicMock()
        db.query.return_value.filter_by.return_value = _make_head_query(exists=True)
        gdb.return_value.__enter__.return_value = db
        resp = await ws.genesis_status(current_user=MagicMock())
        assert resp["status"] == "complete"


async def test_failed_returns_reason(fake_redis):
    fake_redis.get.return_value = json.dumps({"phase": "failed", "reason": "boom"})
    with patch.object(ws, "get_fresh_db") as gdb, \
         patch("backend.core.redis.get_redis_client", lambda: fake_redis):
        db = MagicMock()
        db.query.return_value.filter_by.return_value = _make_head_query(exists=False)
        gdb.return_value.__enter__.return_value = db
        resp = await ws.genesis_status(current_user=MagicMock())
        assert resp["status"] == "failed"
        assert resp["reason"] == "boom"


async def test_running_when_key_present(fake_redis):
    cfg_q = MagicMock()
    cfg_q.first.return_value = object()
    head_q = _make_head_query(exists=False)
    with patch.object(ws, "get_fresh_db") as gdb, \
         patch("backend.core.redis.get_redis_client", lambda: fake_redis):
        db = MagicMock()
        db.query.side_effect = _db_side_effect(head_q, cfg_q)
        gdb.return_value.__enter__.return_value = db
        resp = await ws.genesis_status(current_user=MagicMock())
        assert resp["status"] == "running"


async def test_not_started_when_no_key(fake_redis):
    cfg_q = MagicMock()
    cfg_q.first.return_value = None
    head_q = _make_head_query(exists=False)
    with patch.object(ws, "get_fresh_db") as gdb, \
         patch("backend.core.redis.get_redis_client", lambda: fake_redis):
        db = MagicMock()
        db.query.side_effect = _db_side_effect(head_q, cfg_q)
        gdb.return_value.__enter__.return_value = db
        resp = await ws.genesis_status(current_user=MagicMock())
        assert resp["status"] == "not_started"


async def test_failed_takes_precedence_over_key(fake_redis):
    fake_redis.get.return_value = json.dumps({"phase": "failed", "reason": "kaboom"})
    cfg_q = MagicMock()
    cfg_q.first.return_value = object()  # a config row exists
    head_q = _make_head_query(exists=False)
    with patch.object(ws, "get_fresh_db") as gdb, \
         patch("backend.core.redis.get_redis_client", lambda: fake_redis):
        db = MagicMock()
        db.query.side_effect = _db_side_effect(head_q, cfg_q)
        gdb.return_value.__enter__.return_value = db
        resp = await ws.genesis_status(current_user=MagicMock())
        assert resp["status"] == "failed"
        assert resp["reason"] == "kaboom"
