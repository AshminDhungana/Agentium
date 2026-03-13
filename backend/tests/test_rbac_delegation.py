"""
Tests for Phase 11.1 RBAC functionality.
Focuses on delegation lifecycle and observer middleware.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from fastapi import Request
from fastapi.responses import JSONResponse

from backend.models.entities.user import User, ROLE_PRIMARY_SOVEREIGN, ROLE_OBSERVER
from backend.models.entities.delegation import Delegation
from backend.services.rbac_service import RBACService
from backend.core.observer_middleware import ObserverReadOnlyMiddleware

class MockDB:
    def __init__(self):
        self._adds = []
        self._queries = []
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
        
        # Specific handler for checking active delegations
        def mock_first():
            return None
            
        def mock_all():
            if model == Delegation:
                return [d for d in self._cache if isinstance(d, Delegation) and isinstance(d.expires_at, datetime) and d.expires_at < datetime.utcnow() and d.revoked_at is None]
            return []
            
        mock_query.first = mock_first
        mock_query.all = mock_all
        return mock_query

def test_delegation_lifecycle():
    db = MockDB()
    
    grantor = User(id="sovereign-1", username="sov", role=ROLE_PRIMARY_SOVEREIGN, is_admin=True)
    grantee = User(id="grantee-1", username="grantee", role=ROLE_OBSERVER)
    
    # 1. Grant
    expires_in_future = datetime.utcnow() + timedelta(hours=1)
    delegation = RBACService.delegate_capabilities(
        db=db,
        grantor=grantor,
        grantee_id=grantee.id,
        capabilities=["configure_agents"],
        expires_at=expires_in_future,
        reason="Test delegation"
    )
    
    assert delegation.is_active is True
    assert delegation.capabilities == ["configure_agents"]
    
    # Check expiry
    count = RBACService.expire_stale_delegations(db)
    assert count == 0 # no expiry
    
    # 2. Force expire by artificially backdating
    delegation.expires_at = datetime.utcnow() - timedelta(hours=1)
    
    # Run expiry background task
    count = RBACService.expire_stale_delegations(db)
    assert count == 1
    assert delegation.is_active is False
    assert delegation.revoked_at is not None

@pytest.mark.asyncio
async def test_observer_middleware_enforcement():
    middleware = ObserverReadOnlyMiddleware(MagicMock())
    
    class MockCallNext:
        async def __call__(self, request):
            return JSONResponse({"status": "ok"})
            
    call_next = MockCallNext()
            
    # Test 1: GET request (allowed for anyone)
    req_get = Request({"type": "http", "method": "GET", "url": "http://testserver/api/v1/agents", "headers": []})
    res = await middleware.dispatch(req_get, call_next)
    import json
    body = json.loads(res.body.decode())
    assert body.get("status") == "ok"
    assert res.status_code == 200
    
    # Test 2: POST request by Observer (blocked)
    # We mock verify_token and DB query to return an observer user
    with patch("backend.core.observer_middleware.verify_token") as mock_verify:
        mock_verify.return_value = {"user_id": "observer-1"}
        
        with patch("backend.core.observer_middleware.SessionLocal") as mock_db_ctx:
            mock_db = MagicMock()
            mock_db_ctx.return_value.__enter__.return_value = mock_db
            
            mock_user = User(id="observer-1", role=ROLE_OBSERVER, is_admin=False)
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = mock_user
            mock_db.query.return_value = mock_query

            req_post = Request({
                "type": "http", 
                "method": "POST", 
                "url": "http://testserver/api/v1/agents", 
                "headers": [(b"authorization", b"Bearer token")]
            })
            
            res = await middleware.dispatch(req_post, call_next)
            assert res.status_code == 403
            
            body = json.loads(res.body.decode())
            assert "Observer role is read-only" in body["detail"]
