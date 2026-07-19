from backend.core.environment_context import (
    AGENT_ENVIRONMENT_CONTEXT,
    ENV_CONTEXT_DOC_ID,
)


def test_context_mentions_host_home_desktop():
    assert "/host_home/Desktop" in AGENT_ENVIRONMENT_CONTEXT


def test_context_states_internet_egress():
    lowered = AGENT_ENVIRONMENT_CONTEXT.lower()
    assert "internet" in lowered
    assert "egress" in lowered


def test_doc_id_is_stable():
    assert ENV_CONTEXT_DOC_ID == "agent_environment_context"
