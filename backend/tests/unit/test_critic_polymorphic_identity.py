"""
Regression test for polymorphic identity registration of critic agents.

Root cause (log 1.1): `CriticAgent` declared `polymorphic_identity` only for
`CODE_CRITIC`. Loading an `OUTPUT_CRITIC` or `PLAN_CRITIC` row therefore failed
with a mapper error, 500-ing `/api/v1/agents`, breaking WebSocket connections
and the constitutional patrol loop.

This test guards that all three critic types are registered in the Agent
polymorphic map and can be instantiated.
"""
import pytest

from backend.models.entities.agents import Agent, AgentType, AGENT_TYPE_MAP
from backend.models.entities.critics import (
    CriticAgent,
    CriticType,
    OutputCriticAgent,
    PlanCriticAgent,
)


CRITIC_TYPES = [
    (AgentType.CODE_CRITIC, CriticType.CODE, CriticAgent, "79999"),
    (AgentType.OUTPUT_CRITIC, CriticType.OUTPUT, OutputCriticAgent, "89999"),
    (AgentType.PLAN_CRITIC, CriticType.PLAN, PlanCriticAgent, "99999"),
]


def test_all_critic_types_registered_in_polymorphic_map():
    """Every critic agent_type must resolve to a mapper on the Agent hierarchy."""
    for agent_type, _, _, _ in CRITIC_TYPES:
        assert (
            agent_type in Agent.__mapper__.polymorphic_map
        ), f"{agent_type} is missing from the Agent polymorphic map"


def test_agent_type_map_points_to_distinct_critic_classes():
    """Each critic type maps to its own concrete class (not all to CriticAgent)."""
    assert AGENT_TYPE_MAP[AgentType.CODE_CRITIC] is CriticAgent
    assert AGENT_TYPE_MAP[AgentType.OUTPUT_CRITIC] is OutputCriticAgent
    assert AGENT_TYPE_MAP[AgentType.PLAN_CRITIC] is PlanCriticAgent


def test_all_three_critic_types_instantiate():
    """All three critic types can be instantiated without error."""
    for agent_type, critic_type, cls, agentium_id in CRITIC_TYPES:
        agent = cls(
            agentium_id=agentium_id,
            name=f"{critic_type.value.title()} Critic",
            critic_specialty=critic_type,
        )
        assert agent.agent_type == agent_type
        assert isinstance(agent, CriticAgent)


def test_critic_agent_derives_agent_type_from_specialty():
    """Instantiating CriticAgent with a specialty yields the right agent_type."""
    for agent_type, critic_type, _, agentium_id in CRITIC_TYPES:
        agent = CriticAgent(
            agentium_id=agentium_id,
            name=f"{critic_type.value.title()} Critic",
            critic_specialty=critic_type,
        )
        assert agent.agent_type == agent_type
