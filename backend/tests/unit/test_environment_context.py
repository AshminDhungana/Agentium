from backend.core.environment_context import (
    AGENT_ENVIRONMENT_CONTEXT,
    ENV_CONTEXT_DOC_ID,
)
from backend.models.entities.constitution import Ethos


def test_context_mentions_host_home_desktop():
    assert "/host_home/Desktop" in AGENT_ENVIRONMENT_CONTEXT


def test_context_states_internet_egress():
    lowered = AGENT_ENVIRONMENT_CONTEXT.lower()
    assert "internet" in lowered
    assert "egress" in lowered


def test_doc_id_is_stable():
    assert ENV_CONTEXT_DOC_ID == "agent_environment_context"


def test_ethos_has_environment_context_column():
    # The column must be a mapped ORM column on the `ethos` table, not just a
    # free-floating Python attribute (which SQLAlchemy instances allow anyway).
    assert "environment_context" in Ethos.__table__.columns

    ethos = Ethos(
        agentium_id="E30001",
        agent_type="task_agent",
        mission_statement="Do tasks.",
        core_values="[]",
        behavioral_rules="[]",
        restrictions="[]",
        capabilities="[]",
        created_by_agentium_id="00001",
        agent_id="00000000-0000-0000-0000-000000000001",
    )
    ethos.environment_context = "you are in docker"
    assert ethos.environment_context == "you are in docker"


from backend.core.environment_context import AGENT_ENVIRONMENT_CONTEXT


def test_to_dict_includes_environment_context():
    ethos = Ethos(
        agentium_id="E30001",
        agent_type="task_agent",
        mission_statement="Do tasks.",
        core_values="[]",
        behavioral_rules="[]",
        restrictions="[]",
        capabilities="[]",
        created_by_agentium_id="00001",
        agent_id="00000000-0000-0000-0000-000000000001",
        environment_context=AGENT_ENVIRONMENT_CONTEXT,
    )
    d = ethos.to_dict()
    assert d["environment_context"] == AGENT_ENVIRONMENT_CONTEXT
    assert "/host_home/Desktop" in d["environment_context"]


def test_compression_payload_includes_and_preserves_context():
    ethos = Ethos(
        agentium_id="E30001",
        agent_type="task_agent",
        mission_statement="Do tasks.",
        core_values="[]",
        behavioral_rules="[]",
        restrictions="[]",
        capabilities="[]",
        created_by_agentium_id="00001",
        agent_id="00000000-0000-0000-0000-000000000001",
        version=1,
        environment_context="grounded",
    )
    payload = ethos.build_compression_payload()
    assert payload["environment_context"] == "grounded"
    # compress() is core-identity-preserving; environment_context must survive.
    ethos.compress()
    assert ethos.environment_context == "grounded"


def test_clear_working_state_preserves_context():
    ethos = Ethos(
        agentium_id="E30001",
        agent_type="task_agent",
        mission_statement="Do tasks.",
        core_values="[]",
        behavioral_rules="[]",
        restrictions="[]",
        capabilities="[]",
        created_by_agentium_id="00001",
        agent_id="00000000-0000-0000-0000-000000000001",
        environment_context="grounded",
    )
    ethos.clear_working_state()
    assert ethos.environment_context == "grounded"
