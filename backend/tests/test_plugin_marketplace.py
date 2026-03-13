"""
Tests for Phase 11.3 Plugin Marketplace functionality.
Focuses on Council approval proposals, sandboxed execution, and revenue ledgers.
"""
import pytest
from unittest.mock import patch, MagicMock

from backend.models.entities.plugin import Plugin, PluginInstallation, PluginRevenueLedger
from backend.services.plugin_marketplace_service import PluginMarketplaceService

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
            if model == Plugin:
                for c in self._cache:
                    if isinstance(c, Plugin): return c
            if model == PluginInstallation:
                for c in self._cache:
                    if isinstance(c, PluginInstallation): return c
            
            return None
            
        mock_query.first = mock_first
        return mock_query

def test_request_council_approval():
    db = MockDB()
    plugin = Plugin(id="plug-1", name="Test Plugin", status="submitted")
    db.add(plugin)
    
    proposal_id = PluginMarketplaceService.request_council_approval(db, "plug-1")
    
    assert proposal_id is not None
    assert proposal_id.startswith("proposal-plugin")
    
    # invalid status
    plugin.status = "published"
    with pytest.raises(Exception):
        PluginMarketplaceService.request_council_approval(db, "plug-1")

@pytest.mark.asyncio
@patch("backend.core.config.settings")
async def test_execute_plugin_sandboxed(mock_settings):
    mock_settings.REMOTE_EXECUTOR_ENABLED = True
    mock_settings.SANDBOX_TIMEOUT_SECONDS = 300
    
    db = MockDB()
    plugin = Plugin(id="plug-1", name="Test Exec")
    install = PluginInstallation(id="inst-1", plugin_id="plug-1", is_active=True)
    db.add(plugin)
    db.add(install)
    
    res = await PluginMarketplaceService.execute_plugin_sandboxed(
        db=db, 
        installation_id="inst-1", 
        input_data={"foo": "bar"}
    )
    
    assert res["status"] == "success"
    assert res["plugin_name"] == "Test Exec"
    assert res["data"]["processed"] is True

def test_record_revenue():
    db = MockDB()
    plugin = Plugin(id="plug-1", name="Monetized Plugin")
    db.add(plugin)
    
    ledger = PluginMarketplaceService.record_revenue(
        db, 
        plugin_id="plug-1", 
        amount=9.99,
        currency="USD",
        notes="Subscription payment"
    )
    
    assert isinstance(ledger, PluginRevenueLedger)
    assert ledger.amount == 9.99
    assert ledger.currency == "USD"
    assert ledger.transaction_type == "purchase"
    
    # Verify it was added to DB
    assert ledger in db._adds
