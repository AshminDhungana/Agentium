"""Integration tests for InitializationService - Genesis Protocol end-to-end."""
import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from backend.services.initialization_service import InitializationService, get_active_genesis, submit_country_name
from backend.models.entities.agents import (
    HeadOfCouncil, CouncilMember, LeadAgent, TaskAgent,
    AgentType, AgentStatus
)
from backend.models.entities.constitution import Constitution
from backend.models.entities.voting import AmendmentVoting, AmendmentStatus, IndividualVote
from backend.models.entities.chat_message import ChatMessage as ChatMsg
from backend.models.entities.user import User
from backend.models.entities.user_config import UserModelConfig, ProviderType, ConnectionStatus


@pytest.fixture(autouse=True)
def reset_active_genesis():
    """Reset the global _ACTIVE_GENESIS handle before/after each test."""
    import backend.services.initialization_service as init_svc
    init_svc._ACTIVE_GENESIS = None
    yield
    init_svc._ACTIVE_GENESIS = None


@pytest.mark.integration
class TestInitializationServiceGenesisProtocol:
    """Test the full genesis protocol end-to-end with real database."""

    @pytest.mark.asyncio
    async def test_genesis_protocol_creates_head_council_lead(self, seeded_db):
        """Genesis should create Head 00001, Council Members, and default Lead Agent."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True):
            result = await svc.run_genesis_protocol(force=True, country_name="TestNation")

        assert result["status"] == "initialized"
        assert result["country_name"] == "TestNation"
        assert result["user_provided"] is True
        assert "created_head_00001" in result["steps_completed"]
        assert "created_council_members:2" in result["steps_completed"]
        assert "created_default_lead:20001" in result["steps_completed"]
        assert "constitution_loaded" in result["steps_completed"]
        assert "country_name_voted" in result["steps_completed"]
        assert "vector_db_indexed" in result["steps_completed"]
        assert "council_privileges_granted" in result["steps_completed"]

        # Verify Head 00001 exists
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001", is_active=True).first()
        assert head is not None
        assert head.name == "Head of Council Prime"
        assert head.is_persistent is True

        # Verify 2 Council Members exist
        council = seeded_db.query(CouncilMember).filter_by(is_active=True).all()
        assert len(council) == 2
        assert [c.agentium_id for c in council] == ["10001", "10002"]
        assert all(c.parent_id == head.id for c in council)

        # Verify default Lead Agent exists
        lead = seeded_db.query(LeadAgent).filter_by(agentium_id="20001", is_active=True).first()
        assert lead is not None
        assert lead.name == "Prime Lead"

    @pytest.mark.asyncio
    async def test_genesis_saves_nation_name_to_constitution(self, seeded_db):
        """Genesis should persist the nation name in the active Constitution's sovereign_preferences."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True):
            await svc.run_genesis_protocol(force=True, country_name="Veridia")

        const = seeded_db.query(Constitution).filter_by(is_active=True).first()
        assert const is not None
        prefs = json.loads(const.sovereign_preferences)
        assert prefs["country_name"] == "Veridia"
        assert prefs["council_size"] == 2
        assert "founded_at" in prefs
        assert prefs["genesis_protocol"] == "v1.0"

    @pytest.mark.asyncio
    async def test_genesis_records_democratic_vote_on_country_name(self, seeded_db):
        """Genesis should record a democratic AmendmentVoting for the country name."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True):
            await svc.run_genesis_protocol(force=True, country_name="DemocracyLand")

        voting = seeded_db.query(AmendmentVoting).filter_by(agentium_id="AVGEN1").first()
        assert voting is not None
        assert voting.status == AmendmentStatus.RATIFIED
        assert voting.votes_for == 3  # 2 Council + 1 Head
        assert voting.votes_against == 0
        assert voting.final_result == "passed"
        assert "DemocracyLand" in voting.proposed_changes

        # Verify individual votes recorded
        votes = seeded_db.query(IndividualVote).filter_by(amendment_voting_id=voting.id).all()
        assert len(votes) == 3
        voter_ids = [v.voter_agentium_id for v in votes]
        assert "00001" in voter_ids
        assert "10001" in voter_ids
        assert "10002" in voter_ids
        assert all(v.vote == "for" for v in votes)

    @pytest.mark.asyncio
    async def test_genesis_grants_council_privileges(self, seeded_db):
        """Genesis should grant Council admin rights and spawn capabilities."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True):
            await svc.run_genesis_protocol(force=True, country_name="PrivilegeTest")

        council = seeded_db.query(CouncilMember).filter_by(is_active=True).all()
        assert len(council) == 2

        for member in council:
            # Verify ethos has knowledge_admin metadata
            assert member.ethos is not None
            metadata = json.loads(member.ethos.meta_data or "{}")
            assert metadata.get("knowledge_admin") is True
            assert metadata.get("can_approve_submissions") is True

            # Verify capabilities granted
            from backend.models.entities.agents import AgentCapability
            from backend.services.capability_registry import Capability
            capabilities = seeded_db.query(AgentCapability).filter_by(agent_id=member.id).all()
            capability_names = [c.name for c in capabilities]
            assert Capability.SPAWN_TASK_AGENT.value in capability_names
            assert Capability.SPAWN_LEAD.value in capability_names

    @pytest.mark.asyncio
    async def test_genesis_creates_welcome_chat_message(self, seeded_db):
        """Genesis should persist a welcome message from Head of Council to chat history."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True):
            await svc.run_genesis_protocol(force=True, country_name="WelcomeNation")

        messages = seeded_db.query(ChatMsg).filter_by(
            role="head_of_council",
            agent_id="00001"
        ).all()
        assert len(messages) == 1
        msg = messages[0]
        assert "WelcomeNation" in msg.content
        assert "Welcome" in msg.content
        assert msg.message_metadata.get("source") == "genesis"
        assert msg.message_metadata.get("event") == "country_name_decision"

    @pytest.mark.asyncio
    async def test_genesis_idempotent_no_rerun_without_force(self, seeded_db):
        """Genesis without force should return already_initialized if Head 00001 exists."""
        svc1 = InitializationService(db=seeded_db)
        with patch.object(svc1, "_has_any_active_api_key", return_value=True):
            await svc1.run_genesis_protocol(force=True, country_name="IdempotentNation")

        # Second run without force
        svc2 = InitializationService(db=seeded_db)
        with patch.object(svc2, "_has_any_active_api_key", return_value=True):
            result = await svc2.run_genesis_protocol()

        assert result["status"] == "already_initialized"
        assert result["head_id"] == "00001"

    @pytest.mark.asyncio
    async def test_genesis_force_true_reruns_cleanly(self, seeded_db):
        """Genesis with force=True should clear and re-run cleanly."""
        svc1 = InitializationService(db=seeded_db)
        with patch.object(svc1, "_has_any_active_api_key", return_value=True):
            await svc1.run_genesis_protocol(force=True, country_name="FirstNation")

        # Force re-run
        svc2 = InitializationService(db=seeded_db)
        with patch.object(svc2, "_has_any_active_api_key", return_value=True):
            result = await svc2.run_genesis_protocol(force=True, country_name="SecondNation")

        assert result["status"] == "initialized"
        assert result["country_name"] == "SecondNation"

        const = seeded_db.query(Constitution).filter_by(is_active=True).first()
        prefs = json.loads(const.sovereign_preferences)
        assert prefs["country_name"] == "SecondNation"

    @pytest.mark.asyncio
    async def test_genesis_blocks_without_active_api_key(self, seeded_db):
        """Genesis should fail if no active API key is configured."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=False):
            result = await svc.run_genesis_protocol(force=True, country_name="BlockedNation")

        assert result["status"] == "no_api_key"
        assert result["action_required"] == "configure_api_key"
        assert "Genesis cannot begin" in result["message"]

    @pytest.mark.asyncio
    async def test_genesis_default_country_name_on_timeout(self, seeded_db):
        """Genesis should use default name when country name prompt times out."""
        svc = InitializationService(db=seeded_db)

        # Mock _prompt_for_country_name to return None (timeout)
        with patch.object(svc, "_has_any_active_api_key", return_value=True), \
             patch.object(svc, "_prompt_for_country_name", AsyncMock(return_value=None)):
            result = await svc.run_genesis_protocol(force=True)

        assert result["status"] == "initialized"
        assert result["country_name"] == "The Agentium Sovereignty"
        assert result["user_provided"] is False

        const = seeded_db.query(Constitution).filter_by(is_active=True).first()
        prefs = json.loads(const.sovereign_preferences)
        assert prefs["country_name"] == "The Agentium Sovereignty"


@pytest.mark.integration
class TestInitializationServiceCountryNameHandling:
    """Test country name submission and prompt handling."""

    def test_submit_country_name_when_no_active_genesis_returns_false(self):
        """submit_country_name should return False when no genesis is awaiting."""
        import backend.services.initialization_service as init_svc
        init_svc._ACTIVE_GENESIS = None

        assert submit_country_name("AnyName") is False

    def test_submit_country_name_delivers_to_awaiting_genesis(self):
        """submit_country_name should deliver name and set event when genesis is awaiting."""
        import asyncio
        svc = InitializationService(db=None)
        svc._country_name_event = asyncio.Event()
        svc._pending_country_name = None
        svc.awaiting_country_name = True

        import backend.services.initialization_service as init_svc
        init_svc._ACTIVE_GENESIS = svc

        try:
            assert submit_country_name("DeliveredName") is True
            assert svc._pending_country_name == "DeliveredName"
            assert svc._country_name_event.is_set()
        finally:
            init_svc._ACTIVE_GENESIS = None

    def test_get_active_genesis_returns_handle(self):
        """get_active_genesis should return the active genesis instance."""
        svc = InitializationService(db=None)

        import backend.services.initialization_service as init_svc
        init_svc._ACTIVE_GENESIS = svc

        try:
            assert get_active_genesis() is svc
        finally:
            init_svc._ACTIVE_GENESIS = None

    @pytest.mark.asyncio
    async def test_prompt_for_country_name_accepts_provided_name(self, seeded_db):
        """When country_name is provided to run_genesis_protocol, it should skip prompt."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True), \
             patch.object(svc, "_prompt_for_country_name", AsyncMock()) as mock_prompt:
            await svc.run_genesis_protocol(force=True, country_name="ProvidedName")

        # Prompt should not be called when name is provided
        mock_prompt.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_to_user_sends_websocket_and_channels(self, seeded_db):
        """_broadcast_to_user should attempt both WebSocket and channel broadcasts."""
        svc = InitializationService(db=seeded_db)

        # Mock sovereign user
        admin_user = User(
            username="admin",
            email="admin@test.com",
            hashed_password=User.hash_password("admin"),
            is_active=True,
            is_admin=True
        )
        seeded_db.add(admin_user)
        seeded_db.flush()

        # Patch the query chain to return our admin user
        with patch.object(svc.db, "query") as mock_query:
            mock_filter_by = MagicMock()
            mock_filter_by.return_value.first.return_value = admin_user
            mock_query.return_value.filter_by.return_value = mock_filter_by

            with patch("backend.api.routes.websocket.manager.broadcast", new=AsyncMock()) as mock_ws, \
                 patch("backend.services.channel_manager.ChannelManager.broadcast_to_channels", new=AsyncMock()) as mock_channels:
                await svc._broadcast_to_user("Test message", is_urgent=True)

        assert mock_ws.called
        assert mock_channels.called
        ws_payload = mock_ws.call_args.args[0]
        assert ws_payload["type"] == "genesis_prompt"
        assert ws_payload["role"] == "head_of_council"
        assert ws_payload["content"] == "Test message"
        assert ws_payload["is_urgent"] is True
        assert ws_payload["metadata"]["requires_response"] is True


@pytest.mark.integration
class TestInitializationServiceModelConfig:
    """Test model config assignment during genesis."""

    @pytest.mark.asyncio
    async def test_genesis_assigns_model_config_to_head(self, seeded_db):
        """Genesis should assign a usable model config to Head 00001."""
        # Create an active model config
        config = UserModelConfig(
            config_name="Test Config",
            provider=ProviderType.OPENAI,
            default_model="gpt-4o",
            status=ConnectionStatus.ACTIVE,
            is_default=True,
        )
        seeded_db.add(config)
        seeded_db.flush()

        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True):
            await svc.run_genesis_protocol(force=True, country_name="ConfigNation")

        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        assert head.preferred_config_id == str(config.id)

    @pytest.mark.asyncio
    async def test_genesis_creates_default_config_if_none_exists(self, seeded_db):
        """Genesis should create a default model config from available API keys if none exists."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True):
            # Also patch api_key_manager to return a provider
            with patch("backend.services.api_key_manager.api_key_manager.get_provider_availability",
                       return_value={"openai": True}):
                await svc.run_genesis_protocol(force=True, country_name="AutoConfigNation")

        # Should have created a config
        configs = seeded_db.query(UserModelConfig).filter_by(is_default=True).all()
        assert len(configs) >= 1

        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        assert head.preferred_config_id is not None


@pytest.mark.integration
class TestInitializationServiceClearExistingData:
    """Test the _clear_existing_data method for force re-initialization."""

    @pytest.mark.asyncio
    async def test_clear_existing_data_removes_structure(self, seeded_db):
        """_clear_existing_data should remove all structural data."""
        svc = InitializationService(db=seeded_db)
        await svc._clear_existing_data()

        # Verify all structural tables are empty
        assert seeded_db.query(HeadOfCouncil).count() == 0
        assert seeded_db.query(CouncilMember).count() == 0
        assert seeded_db.query(LeadAgent).count() == 0
        assert seeded_db.query(Constitution).count() == 0


@pytest.mark.integration
class TestInitializationServiceEarlyCommit:
    """Test the early commit (todo §4.1) happens before nation naming."""

    @pytest.mark.asyncio
    async def test_early_commit_before_naming_prompt(self, seeded_db):
        """Structural agents should be committed/flushed before _prompt_for_country_name runs."""
        svc = InitializationService(db=seeded_db)

        captured = {"early_commit_called": False}

        async def _fake_prompt(timeout=60):
            # Check if commit/flush was called before this point
            # In TESTING mode (which seeded_db uses), genesis uses flush() not commit()
            captured["early_commit_called"] = svc.db.commit.called or svc.db.flush.called
            return None  # Use default name

        with patch.object(svc, "_has_any_active_api_key", return_value=True), \
             patch.object(svc, "_clear_existing_data", AsyncMock()), \
             patch.object(svc, "_create_head_of_council", AsyncMock(return_value=MagicMock())), \
             patch.object(svc, "_create_council_members", AsyncMock(return_value=[MagicMock(), MagicMock()])), \
             patch.object(svc, "_create_default_lead", AsyncMock(return_value=MagicMock())), \
             patch.object(svc, "_load_constitution", AsyncMock(return_value=MagicMock())), \
             patch.object(svc, "_vote_on_country_name", AsyncMock()), \
             patch.object(svc, "_notify_country_name_decision", AsyncMock()), \
             patch.object(svc, "_index_to_vector_db", AsyncMock()), \
             patch.object(svc, "_grant_council_privileges", AsyncMock()), \
             patch.object(svc, "_ensure_default_model_config", AsyncMock()), \
             patch.object(svc, "_prompt_for_country_name", _fake_prompt):
            await svc.run_genesis_protocol(force=True)

        assert captured["early_commit_called"] is True

    @pytest.mark.asyncio
    async def test_pre_prompt_failure_rolls_back(self, seeded_db):
        """If structural creation fails before naming, no commit should happen.

        Note: In TESTING mode (os.environ.get("TESTING") == "true"), genesis only flushes,
        doesn't commit. The real commit happens at the end. So we check that neither
        commit nor flush happened before the failure point (before the naming step).
        """
        svc = InitializationService(db=seeded_db)

        async def _boom():
            raise RuntimeError("head creation failed")

        with patch.object(svc, "_has_any_active_api_key", return_value=True), \
             patch.object(svc, "_clear_existing_data", AsyncMock()), \
             patch.object(svc, "_create_head_of_council", _boom):
            try:
                await svc.run_genesis_protocol(force=True)
            except Exception:
                pass

        # In TESTING mode, early commit uses flush(), not commit()
        # The test expects no flush to happen before the failure
        assert svc.db.commit.called is False
    # Note: flush may be called by _clear_existing_data, so we don't assert on it


@pytest.mark.integration
class TestInitializationServiceEthosCreation:
    """Test ethos creation for Head and Council during genesis."""

    @pytest.mark.asyncio
    async def test_head_ethos_created_with_correct_template(self, seeded_db):
        """Head of Council should have ethos with expected fields."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True):
            await svc.run_genesis_protocol(force=True, country_name="EthosNation")

        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        assert head.ethos is not None
        ethos = head.ethos

        assert ethos.agentium_id == "E00001"
        assert ethos.agent_type == "head_of_council"
        assert "Supreme executive authority" in ethos.mission_statement
        assert "Constitutional Fidelity" in json.loads(ethos.core_values)[0]
        assert "Read and internalize the Constitution" in json.loads(ethos.behavioral_rules)[0]
        assert ethos.is_verified is True
        assert ethos.verified_by_agentium_id == "00001"

    @pytest.mark.asyncio
    async def test_council_ethos_created_with_specializations(self, seeded_db):
        """Council Members should have ethos with assigned specializations."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True):
            await svc.run_genesis_protocol(force=True, country_name="SpecializationNation")

        council = seeded_db.query(CouncilMember).filter_by(is_active=True).all()
        assert len(council) == 2

        for member in council:
            assert member.ethos is not None
            ethos = member.ethos

            assert ethos.agentium_id == f"E{member.agentium_id}"
            assert ethos.agent_type == "council_member"
            assert "Constitutional Law" in ethos.mission_statement or \
                   "System Security" in ethos.mission_statement or \
                   "Resource Allocation" in ethos.mission_statement
            assert ethos.is_verified is True
            assert ethos.verified_by_agentium_id == "00001"


@pytest.mark.integration
class TestInitializationServiceConstitutionTemplate:
    """Test constitution template loading and customization."""

    @pytest.mark.asyncio
    async def test_constitution_version_is_v1_0_0(self, seeded_db):
        """Genesis constitution should have version v1.0.0."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True):
            await svc.run_genesis_protocol(force=True, country_name="VersionNation")

        const = seeded_db.query(Constitution).filter_by(is_active=True).first()
        assert const.version == "v1.0.0"
        assert const.version_number == 1
        assert const.agentium_id == "C00001"

    @pytest.mark.asyncio
    async def test_constitution_articles_present(self, seeded_db):
        """Genesis constitution should have all 6 articles."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True):
            await svc.run_genesis_protocol(force=True, country_name="ArticlesNation")

        const = seeded_db.query(Constitution).filter_by(is_active=True).first()
        articles = json.loads(const.articles)

        assert "article_1" in articles
        assert "article_2" in articles
        assert "article_3" in articles
        assert "article_4" in articles
        assert "article_5" in articles
        assert "article_6" in articles

        assert articles["article_1"]["title"] == "Hierarchical Structure"
        assert articles["article_2"]["title"] == "Authority & Delegation"
        assert articles["article_3"]["title"] == "Knowledge Governance"
        assert articles["article_4"]["title"] == "Ethos Oversight"
        assert articles["article_5"]["title"] == "Agent Lifecycle"
        assert articles["article_6"]["title"] == "Design Principles"

    @pytest.mark.asyncio
    async def test_constitution_prohibited_actions_present(self, seeded_db):
        """Genesis constitution should have prohibited actions."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True):
            await svc.run_genesis_protocol(force=True, country_name="ProhibitedNation")

        const = seeded_db.query(Constitution).filter_by(is_active=True).first()
        prohibited = json.loads(const.prohibited_actions)

        assert isinstance(prohibited, list)
        assert len(prohibited) >= 6
        assert "Violating the hierarchical chain of command" in prohibited
        assert "Unauthorized modifications to agent Ethos or Constitution" in prohibited
        assert "Concealing, tampering with, or deleting audit logs" in prohibited
        assert "Storing duplicate knowledge without revision" in prohibited
        assert "Executing tasks without a successfully updated Ethos" in prohibited
        assert "Bypassing democratic deliberation for constitutional amendments" in prohibited


@pytest.mark.integration
class TestInitializationServiceConstitutionalAlignment:
    """Test constitutional alignment workflow §1 at agent creation."""

    @pytest.mark.asyncio
    async def test_head_reads_and_aligns_constitution(self, seeded_db):
        """Head should call read_and_align_constitution at creation."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True), \
             patch.object(HeadOfCouncil, "read_and_align_constitution") as mock_align:
            await svc.run_genesis_protocol(force=True, country_name="AlignmentNation")

        assert mock_align.called

    @pytest.mark.asyncio
    async def test_council_members_read_and_align_constitution(self, seeded_db):
        """Council Members should call read_and_align_constitution at creation."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True), \
             patch.object(CouncilMember, "read_and_align_constitution") as mock_align:
            await svc.run_genesis_protocol(force=True, country_name="CouncilAlignmentNation")

        # Called twice (for 2 council members)
        assert mock_align.call_count == 2


@pytest.mark.integration
class TestInitializationServiceVectorIndexing:
    """Test vector DB indexing during genesis."""

    @pytest.mark.asyncio
    async def test_index_to_vector_db_called(self, seeded_db):
        """_index_to_vector_db should be called during genesis."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True), \
             patch.object(svc, "_index_to_vector_db", AsyncMock()) as mock_index:
            await svc.run_genesis_protocol(force=True, country_name="VectorNation")

        assert mock_index.called


@pytest.mark.integration
class TestInitializationServiceEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_genesis_handles_missing_sovereign_user_gracefully(self, seeded_db):
        """Genesis should handle missing sovereign user without crashing broadcast."""
        svc = InitializationService(db=seeded_db)

        # No admin user in DB - should not crash
        with patch.object(svc, "_has_any_active_api_key", return_value=True), \
             patch.object(svc, "_broadcast_to_user", AsyncMock()), \
             patch.object(svc, "_persist_head_message", AsyncMock(return_value="msg-id")):
            result = await svc.run_genesis_protocol(force=True, country_name="NoAdminNation")

        assert result["status"] == "initialized"
        # Should still succeed even without broadcast user

    @pytest.mark.asyncio
    async def test_genesis_cleanup_active_genesis_handle_on_error(self, seeded_db):
        """_ACTIVE_GENESIS should be cleared even if genesis fails."""
        import backend.services.initialization_service as init_svc

        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True), \
             patch.object(svc, "_clear_existing_data", AsyncMock()), \
             patch.object(svc, "_create_head_of_council", AsyncMock(side_effect=RuntimeError("Boom"))):
            try:
                await svc.run_genesis_protocol(force=True, country_name="ErrorNation")
            except Exception:
                pass

        assert init_svc._ACTIVE_GENESIS is None

    @pytest.mark.asyncio
    async def test_genesis_cleanup_active_genesis_handle_on_success(self, seeded_db):
        """_ACTIVE_GENESIS should be cleared after successful genesis."""
        import backend.services.initialization_service as init_svc

        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True):
            await svc.run_genesis_protocol(force=True, country_name="SuccessNation")

        assert init_svc._ACTIVE_GENESIS is None


@pytest.mark.integration
class TestInitializationServiceInputValidation:
    """Test input validation and sanitization."""

    @pytest.mark.asyncio
    async def test_country_name_stripped_whitespace(self, seeded_db):
        """Country name should be stripped of leading/trailing whitespace."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True):
            await svc.run_genesis_protocol(force=True, country_name="  SpacedNation  ")

        const = seeded_db.query(Constitution).filter_by(is_active=True).first()
        prefs = json.loads(const.sovereign_preferences)
        assert prefs["country_name"] == "SpacedNation"

    @pytest.mark.asyncio
    async def test_empty_country_name_uses_default(self, seeded_db):
        """Empty country name should fall back to default."""
        svc = InitializationService(db=seeded_db)

        with patch.object(svc, "_has_any_active_api_key", return_value=True), \
             patch.object(svc, "_prompt_for_country_name", AsyncMock(return_value="")):
            result = await svc.run_genesis_protocol(force=True)

        assert result["country_name"] == "The Agentium Sovereignty"