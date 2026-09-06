import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import Session
from backend.services.initialization_service import InitializationService
from backend.models.entities.agents import HeadOfCouncil, CouncilMember, LeadAgent, AgentStatus, Agent
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory


class TestVerifyAndRepair:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock(spec=Session)
        # Use a side_effect on query() to return different mock chains for different models
        def query_side_effect(model):
            chain = MagicMock()
            chain.filter_by.return_value.first.side_effect = []
            return chain
        db.query.side_effect = query_side_effect
        return db

    def _setup_query_chain(self, mock_db, model, side_effect_list):
        """Helper to set up side_effect for a specific model's query chain."""
        chain = MagicMock()
        chain.filter_by.return_value.first.side_effect = side_effect_list
        # Accumulate side_effects instead of replacing
        original_side_effect = mock_db.query.side_effect
        def new_query_side_effect(m):
            if m == model:
                return chain
            return original_side_effect(m) if original_side_effect else MagicMock()
        mock_db.query.side_effect = new_query_side_effect
        return chain

    @pytest.fixture
    def init_service(self, mock_db):
        with patch("backend.core.vector_store.get_vector_store"), \
             patch("backend.services.knowledge_service.get_knowledge_service"):
            return InitializationService(db=mock_db)

    @pytest.mark.asyncio
    async def test_verify_and_repair_all_present(self, init_service, mock_db):
        """When all 4 genesis agents exist, return status ok with no recreated."""
        head = MagicMock(spec=HeadOfCouncil)
        head.agentium_id = "00001"
        head.is_active = True
        
        council1 = MagicMock(spec=CouncilMember)
        council1.agentium_id = "10001"
        council1.is_active = True
        
        council2 = MagicMock(spec=CouncilMember)
        council2.agentium_id = "10002"
        council2.is_active = True
        
        lead = MagicMock(spec=LeadAgent)
        lead.agentium_id = "20001"
        lead.is_active = True

        # Set up query chains for each model
        self._setup_query_chain(mock_db, HeadOfCouncil, [head])
        self._setup_query_chain(mock_db, CouncilMember, [council1, council2])
        self._setup_query_chain(mock_db, LeadAgent, [lead])
        self._setup_query_chain(mock_db, Agent, [None, None])  # occupation checks (not reached)

        result = await init_service.verify_and_repair(mock_db)

        assert result["status"] == "ok"
        assert result["checked"] == 4
        assert result["missing"] == []
        assert result["recreated"] == []
        assert result["warnings"] == []
        assert all(d["status"] == "ok" for d in result["details"].values())

    @pytest.mark.asyncio
    async def test_verify_and_repair_missing_council_and_lead(self, init_service, mock_db):
        """When Council 10001 and Lead 20001 missing, they are recreated."""
        head = MagicMock(spec=HeadOfCouncil)
        head.agentium_id = "00001"
        head.is_active = True
        head.id = 1

        council2 = MagicMock(spec=CouncilMember)
        council2.agentium_id = "10002"
        council2.is_active = True

        # HeadOfCouncil: head exists
        # CouncilMember: 10001 missing, 10002 exists
        # LeadAgent: 20001 missing
        # Agent (occupation): 10001 free, 20001 free
        self._setup_query_chain(mock_db, HeadOfCouncil, [head])
        self._setup_query_chain(mock_db, CouncilMember, [None, council2])
        self._setup_query_chain(mock_db, LeadAgent, [None])
        self._setup_query_chain(mock_db, Agent, [None, None])

        new_council = MagicMock(spec=CouncilMember)
        new_council.agentium_id = "10001"
        new_lead = MagicMock(spec=LeadAgent)
        new_lead.agentium_id = "20001"

        init_service._create_council_members = AsyncMock(return_value=[new_council, MagicMock()])
        init_service._create_default_lead = AsyncMock(return_value=new_lead)

        with patch("backend.models.entities.audit.AuditLog.log") as mock_audit_log:
            result = await init_service.verify_and_repair(mock_db)

        assert result["status"] == "repaired"
        assert result["checked"] == 4
        assert set(result["missing"]) == {"10001", "20001"}
        assert set(result["recreated"]) == {"10001", "20001"}
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_verify_and_repair_exact_id_occupied_by_wrong_type(self, init_service, mock_db):
        """When exact ID slot has wrong agent type, use next available + warning."""
        head = MagicMock(spec=HeadOfCouncil)
        head.agentium_id = "00001"
        head.is_active = True
        head.id = 1

        wrong_agent = MagicMock()
        wrong_agent.agentium_id = "10001"
        wrong_agent.agent_type = MagicMock(value="task_agent")
        wrong_agent.is_active = True

        council2 = MagicMock(spec=CouncilMember)
        council2.agentium_id = "10002"
        council2.is_active = True

        lead = MagicMock(spec=LeadAgent)
        lead.agentium_id = "20001"
        lead.is_active = True

        # HeadOfCouncil: head exists
        # CouncilMember: 10001 NOT FOUND (returns None), 10002 exists
        # LeadAgent: 20001 exists
        # Agent (occupation): 10001 occupied by wrong_agent
        self._setup_query_chain(mock_db, HeadOfCouncil, [head])
        self._setup_query_chain(mock_db, CouncilMember, [None, council2])
        self._setup_query_chain(mock_db, LeadAgent, [lead])
        self._setup_query_chain(mock_db, Agent, [wrong_agent])

        new_council = MagicMock(spec=CouncilMember)
        new_council.agentium_id = "10003"
        init_service._create_council_members = AsyncMock(return_value=[new_council, council2])

        with patch("backend.models.entities.audit.AuditLog.log"):
            result = await init_service.verify_and_repair(mock_db, force_exact_ids=True)

        assert result["status"] == "repaired"
        assert "10001" in result["missing"]
        assert "10003" in result["recreated"]
        assert any("occupied by" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_verify_and_repair_head_missing_creates_head(self, init_service, mock_db):
        """When Head 00001 missing, it is recreated first (parent for others)."""
        council1 = MagicMock(spec=CouncilMember)
        council1.agentium_id = "10001"
        council1.is_active = True

        # HeadOfCouncil: missing
        # CouncilMember: 10001 exists, 10002 missing
        # LeadAgent: 20001 missing
        # Agent (occupation): 10002 free, 20001 free (plus extra for safety)
        self._setup_query_chain(mock_db, HeadOfCouncil, [None])
        self._setup_query_chain(mock_db, CouncilMember, [council1, None])
        self._setup_query_chain(mock_db, LeadAgent, [None])
        self._setup_query_chain(mock_db, Agent, [None, None, None, None])

        new_head = MagicMock(spec=HeadOfCouncil)
        new_head.agentium_id = "00001"
        new_head.id = 1
        new_council2 = MagicMock(spec=CouncilMember)
        new_council2.agentium_id = "10002"
        new_lead = MagicMock(spec=LeadAgent)
        new_lead.agentium_id = "20001"

        init_service._create_head_of_council = AsyncMock(return_value=new_head)
        init_service._create_council_members = AsyncMock(return_value=[council1, new_council2])
        init_service._create_default_lead = AsyncMock(return_value=new_lead)

        with patch("backend.models.entities.audit.AuditLog.log"):
            result = await init_service.verify_and_repair(mock_db)

        assert result["status"] == "repaired"
        assert "00001" in result["recreated"]
        assert mock_db.flush.called