"""
Authentication Service.
Provides logic for retrieving authenticated agents and verifying hierarchy permissions.
Used by host_access.py and other secure endpoints.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional

from backend.core.auth import verify_token, security
from backend.models.database import get_db
from backend.models.entities.agents import Agent, AgentType

async def get_current_agent(
    token: str,
    db: Session
) -> Optional[Agent]:
    """
    Retrieve the current authenticated agent from JWT token string.
    validates the token and ensures the agent exists and is active.
    """
    if not token:
        return None
    
    # Verify JWT
    payload = verify_token(token)
    if not payload:
        return None
        
    # Extract agentium_id (subject)
    agent_id = payload.get("sub")
    if not agent_id:
        return None
        
    # Lookup agent
    agent = db.query(Agent).filter(Agent.agentium_id == agent_id).first()
    
    if not agent:
        return None
        
    # Check if active
    if agent.status == 'terminated':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent has been terminated"
        )
        
    return agent

def verify_agent_hierarchy(actor: Agent, target: Agent) -> bool:
    """
    Verify if actor has authority over target agent.
    
    Hierarchy Rules:
    1. Head of Council (Tier 0) has authority over EVERYONE.
    2. Agents have authority over themselves.
    3. Parents have authority over their direct children (subordinates).
    4. Creators have authority over agents they spawned (if distinct from parent).
    """
    # Rule 1: Head of Council
    if actor.agent_type == AgentType.HEAD_OF_COUNCIL:
        return True
        
    # Rule 2: Self-access
    if actor.id == target.id:
        return True
        
    # Rule 3: Parent-Child relationship
    # Check if target's parent is the actor
    if target.parent_id == actor.id:
        return True
        
    # Rule 4: Creator relationship (optional, usually same as parent)
    # If we tracked created_by separately and it wasn't the parent, we'd check here.
    # Based on agents.py, 'created_by_agentium_id' might be relevant but mapped to parent usually,
    # but let's check recursive hierarchy if needed? 
    # For now, strict parent-child or Head-of-Council is the standard.
    
    return False