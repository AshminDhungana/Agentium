"""
Agent-callable MCP server registration tools.
Invoked by agents through ToolCreationService.execute_tool, which injects
`agent_id` into the function signature.
"""
from typing import Any, Dict, Optional

from backend.models.database import SessionLocal
from backend.services.mcp_governance import MCPGovernanceService


async def add_mcp_server(
    name: str,
    description: str,
    server_url: str,
    tier: str,
    agent_id: str,
    constitutional_article: Optional[str] = None,
) -> Dict[str, Any]:
    """Propose a new MCP server, auto-discover its capabilities, and open a Council vote."""
    db = SessionLocal()
    try:
        svc = MCPGovernanceService(db)
        return await svc.propose_mcp_server_with_vote(
            name=name,
            description=description,
            server_url=server_url,
            tier=tier,
            proposed_by=agent_id,
            constitutional_article=constitutional_article,
        )
    finally:
        db.close()


def vote_on_mcp_server(
    tool_id: str,
    vote: str,
    agent_id: str,
) -> Dict[str, Any]:
    """Cast a Council vote on a pending MCP server proposal."""
    db = SessionLocal()
    try:
        svc = MCPGovernanceService(db)
        return svc.vote_on_mcp_proposal(tool_id, agent_id, vote)
    finally:
        db.close()
