"""
Context Window Management for Agentium.
Monitors token usage and triggers reincarnation when context approaches limits.
"""

from typing import Dict, Optional, List, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ContextWindowStatus:
    """Current context window state."""
    agent_id: str
    current_tokens: int
    max_tokens: int
    usage_percentage: float
    warning_threshold: float  # e.g., 0.8 (80%)
    critical_threshold: float  # e.g., 0.95 (95%)
    session_messages: int
    is_critical: bool
    is_warning: bool


class ContextWindowManager:
    """
    Manages LLM context windows across agents.
    Triggers reincarnation when context approaches limits.
    """
    
    # Thresholds for reincarnation
    WARNING_THRESHOLD = 0.75  # 75% - start preparing
    CRITICAL_THRESHOLD = 0.90  # 90% - must reincarnate
    ABSOLUTE_MAX = 0.95  # 95% - hard stop
    
    # Token limits by model (approximate)
    MODEL_LIMITS = {
        "gpt-4": 8192,
        "gpt-4-turbo": 128000,
        "gpt-3.5-turbo": 4096,
        "claude-3-opus": 200000,
        "claude-3-sonnet": 20000,
        "kimi-2.5-7b": 8192,
        "kimi-2.5": 32000,
        "default": 4096
    }
    
    def __init__(self):
        """Init."""

        self.agent_contexts: Dict[str, Dict] = {}
    
    def register_agent(self, agent_id: str, model_name: str, initial_tokens: int = 0):
        """Register agent for context tracking."""
        max_tokens = self.MODEL_LIMITS.get(model_name, self.MODEL_LIMITS["default"])
        
        self.agent_contexts[agent_id] = {
            "model": model_name,
            "max_tokens": max_tokens,
            "current_tokens": initial_tokens,
            "message_count": 0,
            "incarnation": 1,  # Track reincarnations
            "accumulated_wisdom": []  # Summaries from past lives
        }
    
    def update_usage(self, agent_id: str, tokens_used: int, messages_added: int = 1):
        """Record token usage from a conversation turn."""
        if agent_id not in self.agent_contexts:
            return None
        
        ctx = self.agent_contexts[agent_id]
        ctx["current_tokens"] += tokens_used
        ctx["message_count"] += messages_added
        
        return self.check_status(agent_id)
    
    def check_status(self, agent_id: str) -> ContextWindowStatus:
        """Check current context window status."""
        if agent_id not in self.agent_contexts:
            return None
        
        ctx = self.agent_contexts[agent_id]
        current = ctx["current_tokens"]
        max_tok = ctx["max_tokens"]
        percentage = current / max_tok
        
        return ContextWindowStatus(
            agent_id=agent_id,
            current_tokens=current,
            max_tokens=max_tok,
            usage_percentage=percentage,
            warning_threshold=self.WARNING_THRESHOLD,
            critical_threshold=self.CRITICAL_THRESHOLD,
            session_messages=ctx["message_count"],
            is_critical=percentage >= self.CRITICAL_THRESHOLD,
            is_warning=percentage >= self.WARNING_THRESHOLD
        )
    
    def should_reincarnate(self, agent_id: str) -> bool:
        """Check if agent needs reincarnation due to context limits."""
        status = self.check_status(agent_id)
        if not status:
            return False
        return status.is_critical
    
    def prepare_for_reincarnation(self, agent_id: str) -> Dict[str, Any]:
        """
        Prepare context data for reincarnation.
        Returns accumulated wisdom and current state.
        """
        if agent_id not in self.agent_contexts:
            return {}
        
        ctx = self.agent_contexts[agent_id]
        
        return {
            "incarnation_number": ctx["incarnation"],
            "total_tokens_processed": ctx["current_tokens"],
            "total_messages": ctx["message_count"],
            "accumulated_wisdom": ctx["accumulated_wisdom"],
            "model": ctx["model"]
        }
    
    def transfer_to_successor(self, old_id: str, new_id: str):
        """Transfer accumulated wisdom to reincarnated agent."""
        if old_id not in self.agent_contexts:
            return
        
        old_ctx = self.agent_contexts[old_id]
        
        # Register new agent with inherited wisdom
        self.agent_contexts[new_id] = {
            "model": old_ctx["model"],
            "max_tokens": old_ctx["max_tokens"],
            "current_tokens": 0,  # Fresh context
            "message_count": 0,
            "incarnation": old_ctx["incarnation"] + 1,
            "accumulated_wisdom": old_ctx["accumulated_wisdom"].copy()
        }
        
        # Clean up old agent context (but keep wisdom in DB via ethos)
        del self.agent_contexts[old_id]
    
    def add_wisdom(self, agent_id: str, summary: str, topics: List[str]):
        """Add summarized wisdom to accumulated knowledge."""
        if agent_id not in self.agent_contexts:
            return
        
        wisdom_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "incarnation": self.agent_contexts[agent_id]["incarnation"],
            "summary": summary,
            "topics": topics,
            "token_count": len(summary.split())  # Approximate
        }
        
        self.agent_contexts[agent_id]["accumulated_wisdom"].append(wisdom_entry)
    
    def get_stats(self, agent_id: str) -> Dict:
        """Get context statistics for agent."""
        if agent_id not in self.agent_contexts:
            return {}
        
        ctx = self.agent_contexts[agent_id]
        return {
            "current_tokens": ctx["current_tokens"],
            "max_tokens": ctx["max_tokens"],
            "usage_percent": (ctx["current_tokens"] / ctx["max_tokens"]) * 100,
            "incarnation": ctx["incarnation"],
            "wisdom_entries": len(ctx["accumulated_wisdom"]),
            "total_wisdom_tokens": sum(w["token_count"] for w in ctx["accumulated_wisdom"])
        }


# Singleton instance
context_manager = ContextWindowManager()