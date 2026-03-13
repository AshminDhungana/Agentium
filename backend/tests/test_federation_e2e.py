"""
Tests for Phase 11.2 Federation functionality.
Focuses on HMAC JWT signing, knowledge sync, and voting lifecycle.
"""
import pytest
import time
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from backend.models.entities.federation import FederatedInstance, FederatedVote
from backend.services.federation_service import FederationService, _sign_payload, _verify_signature

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
        
        def mock_first():
            if model == FederatedInstance:
                for c in self._cache:
                    if isinstance(c, FederatedInstance):
                        return c
            if model == FederatedVote:
                for c in self._cache:
                    if isinstance(c, FederatedVote):
                        return c
            return None
            
        mock_query.first = mock_first
        return mock_query

def test_hmac_jwt_exchange():
    """Verify HMAC timestamp validity and signature generation/verification"""
    secret = "test_super_secret"
    body = b'{"hello": "world"}'
    ts = int(time.time())
    
    # Sign
    sig = _sign_payload(secret, body, ts)
    
    # Verify good
    assert _verify_signature(secret, body, sig, ts, max_age_seconds=300) is True
    
    # Verify bad body
    assert _verify_signature(secret, b'{"hello": "evil"}', sig, ts, max_age_seconds=300) is False
    
    # Verify bad ts internally
    assert _verify_signature(secret, body, sig, ts-1, max_age_seconds=300) is False
    
    # Verify expiration (age check)
    old_ts = ts - 400
    old_sig = _sign_payload(secret, body, old_ts)
    assert _verify_signature(secret, body, old_sig, old_ts, max_age_seconds=300) is False

def test_federated_voting_lifecycle():
    db = MockDB()
    
    peer = FederatedInstance(id="peer-1", base_url="http://peer1", status="active")
    db.add(peer)
    
    # Create vote
    vote = FederationService.create_federated_vote(
        db=db,
        proposal_id="proposal-1",
        peer_ids=["peer-1"],
        duration_hours=48
    )
    
    assert vote.proposal_id == "proposal-1"
    assert "peer-1" in vote.participating_instances
    assert vote.status == "open"
    assert vote.votes == {}
    
    # Cast vote
    success = FederationService.cast_federated_vote(
        db=db,
        proposal_id="proposal-1",
        peer_id="peer-1",
        decision="PASS"
    )
    
    assert success is True
    assert vote.votes["peer-1"] == "PASS"

@patch("backend.services.federation_service.httpx.get")
def test_sync_constitution_from_peer(mock_get):
    db = MockDB()
    peer = FederatedInstance(id="peer-1", base_url="http://peer1", status="active", name="Peer 1")
    db.add(peer)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "articles": {
            "test_article": {"title": "Test", "content": "Knowledge content"}
        }
    }
    mock_get.return_value = mock_response
    
    with patch("backend.core.vector_store.VectorStore") as MockVS:
        mock_vs_instance = MagicMock()
        mock_col = MagicMock()
        mock_vs_instance.client.get_or_create_collection.return_value = mock_col
        MockVS.return_value = mock_vs_instance
        
        success = FederationService.sync_constitution_from_peer(
            db=db,
            target_peer_id="peer-1",
            my_base_url="http://local",
            my_signing_key="key"
        )
        
        assert success is True
        assert mock_col.upsert.called
        
        # Verify the args passed to upsert
        call_kwargs = mock_col.upsert.call_args[1]
        assert call_kwargs["ids"] == ["peer_peer-1_const_test_article"]
        assert call_kwargs["metadatas"][0]["source"] == "federation"
