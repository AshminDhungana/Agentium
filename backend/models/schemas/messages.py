"""
Message schemas for Agentium inter-agent communication.
Strictly typed for the hierarchical governance system.

Section 6.4 – Context Ray Tracing:
  Added `visible_to` (glob audience filter) and `context_scope`
  (FULL/SUMMARY/SCHEMA_ONLY) to enable role-based selective
  information flow across agent tiers.
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field, validator


class AgentMessage(BaseModel):
    """
    Standardized message format for Agentium Message Bus.
    Enforces hierarchical routing and audit trail requirements.
    """
    
    # Message Identity
    message_id: str = Field(default_factory=lambda: f"msg_{datetime.utcnow().timestamp()}_{id(datetime)}")
    correlation_id: Optional[str] = None  # Links message chains
    
    # Routing Information (HIERARCHY ENFORCED)
    sender_id: str = Field(..., description="Agentium ID (0xxxx, 1xxxx, 2xxxx, 3xxxx)")
    recipient_id: str = Field(..., description="Target agent ID or broadcast channel")
    route_direction: Literal["up", "down", "lateral", "broadcast"] = "up"
    
    # Content
    message_type: Literal[
        "intent",             # Initial request
        "delegation",         # Task assignment downward
        "escalation",         # Problem reporting upward
        "vote_proposal",      # Council business
        "vote_cast",          # Democratic process
        "notification",       # Status update
        "knowledge_share",    # Vector DB submission
        "constitution_query", # RAG query
        "idle_task",          # IDLE governance work
        "heartbeat",          # Health check
        "liquidation",        # Agent termination notice
        # --- Section 6.4: Context Ray Tracing ---
        "plan",               # Structured execution plan (Planners → Executors)
        "execution",          # Step output produced by an Executor
        "critique",           # Critic review request (Executor → Critic)
        "critique_result",    # Critic verdict returned to Executor / Council
    ] = "intent"
    
    payload: Dict[str, Any] = Field(default_factory=dict)
    content: str = Field(default="", description="Human-readable message content")
    
    # Context Enrichment (injected by Orchestrator)
    rag_context: Optional[Dict[str, Any]] = Field(default=None, description="Vector DB context")
    constitutional_basis: Optional[List[str]] = Field(default=None, description="Relevant articles")

    # --- Section 6.4: Context Ray Tracing ---
    visible_to: List[str] = Field(
        default_factory=lambda: ["*"],
        description=(
            "Agent ID glob patterns that may see this message. "
            "Default '*' means all agents. Examples: ['2*', '3*'] restricts "
            "to Lead/Task agents; ['40001'] targets a single critic."
        ),
    )
    context_scope: Literal["FULL", "SUMMARY", "SCHEMA_ONLY"] = Field(
        default="FULL",
        description=(
            "How much of the message content recipients receive. "
            "FULL = complete content; SUMMARY = first 200 chars; "
            "SCHEMA_ONLY = metadata/structure only, no content."
        ),
    )
    
    # Metadata
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    ttl: int = Field(default=86400, description="Time-to-live in seconds (24h default)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    hop_count: int = Field(default=0, description="Prevents infinite routing loops")
    max_hops: int = 5
    
    # Audit
    requires_ack: bool = True
    processed: bool = False
    error_count: int = 0
    
    @validator("hop_count")
    def check_max_hops(cls, v):
        if v > 5:
            raise ValueError("Message exceeded max hop count - possible routing loop")
        return v
    
    @validator("sender_id", "recipient_id")
    def validate_agentium_id_format(cls, v):
        """Ensure ID follows 0xxxx – 6xxxx format.

        Valid prefixes:
          0 – Head of Council
          1 – Council Member
          2 – Lead Agent
          3 – Task Agent
          4 – Code Critic   (Section 6.4)
          5 – Output Critic (Section 6.4)
          6 – Plan Critic   (Section 6.4)
        """
        if v == "broadcast":  # Special case for Head broadcasts
            return v
        if len(v) != 5 or not v.isdigit():
            raise ValueError("Agentium ID must be exactly 5 digits")
        prefix = v[0]
        if prefix not in ["0", "1", "2", "3", "4", "5", "6"]:
            raise ValueError("ID must start with 0–6 (0=Head, 1=Council, 2=Lead, 3=Task, 4-6=Critic)")
        return v
    
    def get_tier(self, agent_id: str) -> int:
        """Extract numeric tier from agent ID."""
        if agent_id == "broadcast":
            return -1
        return int(agent_id[0])
    
    def is_hierarchy_valid(self) -> bool:
        """
        Validate routing respects hierarchy:
        - Up: 3->2->1->0 (escalation)
        - Down: 0->1->2->3 (delegation)  
        - Lateral: Same tier (siblings)
        """
        if self.recipient_id == "broadcast":
            return self.get_tier(self.sender_id) == 0  # Only Head can broadcast
        
        sender_tier = self.get_tier(self.sender_id)
        recipient_tier = self.get_tier(self.recipient_id)
        
        if self.route_direction == "up":
            return recipient_tier < sender_tier  # Recipient must be higher tier
        elif self.route_direction == "down":
            return recipient_tier > sender_tier  # Recipient must be lower tier
        elif self.route_direction == "lateral":
            return sender_tier == recipient_tier
        
        return True
    
    def increment_hop(self) -> "AgentMessage":
        """Create copy with incremented hop count."""
        new_msg = self.copy()
        new_msg.hop_count += 1
        return new_msg
    
    def to_redis_stream(self) -> Dict[str, str]:
        """Convert to Redis Stream entry format.

        Section 6.4: `visible_to` is serialised as JSON so the list survives
        the Redis key=value round-trip. `context_scope` is stored as-is.
        """
        return {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "message_type": self.message_type,
            "route_direction": self.route_direction,
            "content": self.content,
            "payload_json": self.payload.__str__(),
            "priority": self.priority,
            "timestamp": self.timestamp.isoformat(),
            "hop_count": str(self.hop_count),
            "correlation_id": self.correlation_id or "",
            # Section 6.4: Context Ray Tracing fields
            "visible_to": json.dumps(self.visible_to),
            "context_scope": self.context_scope,
        }
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class MessageReceipt(BaseModel):
    """Acknowledgment of message delivery."""
    message_id: str
    recipient_id: str
    received_at: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["delivered", "processing", "failed", "rejected"] = "delivered"
    error_message: Optional[str] = None


class RouteResult(BaseModel):
    """Result of a routing operation."""
    success: bool
    message_id: str
    path_taken: List[str] = Field(default_factory=list)  # List of agent IDs traversed
    latency_ms: float = 0.0
    error: Optional[str] = None
    vector_context_injected: bool = False
    constitutional_articles: List[str] = Field(default_factory=list)