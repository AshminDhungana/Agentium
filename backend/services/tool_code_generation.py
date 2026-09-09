"""
Tool Code Generation Service
Extracts natural language -> code generation logic from agent_orchestrator
for reuse by API endpoints and self-improvement workflows.
"""
import re
from typing import Dict, Any, List, Optional
from textwrap import dedent

from sqlalchemy.orm import Session
from backend.services.tool_factory import ToolFactory
from backend.core.llm_client import LLMClient
from backend.models.schemas.tool_creation import ToolParameter


class ToolCodeGenerationService:
    """
    Generates validated Python tool code from natural language descriptions.
    
    Reuses the system prompt and validation logic previously embedded in
    AgentOrchestrator._handle_tool_creation_request().
    """
    
    SYSTEM_PROMPT = (
        "You are the code-generation engine of an autonomous AI agent system. "
        "Write the BODY of a Python method `execute(self, **kwargs)` for a new tool.\n"
        "Rules:\n"
        "- Compute the tool's output and assign it to a variable named `result` "
        "(a dict or JSON-serialisable value).\n"
        "- You MAY call other already-registered tools via "
        "`from backend.core.tool_registry import tool_registry` then "
        "`tool_registry.get_tool_function('<name>')(**inputs)`.\n"
        "- Only use these imports: os, sys, json, re, datetime, math, typing, "
        "requests, pathlib, uuid, random, string, hashlib, time, collections, "
        "itertools, backend.\n"
        "- Do NOT use eval, exec, __import__, open, input, os.system, "
        "subprocess shell calls, or file deletion.\n"
        "Return ONLY Python code (the execute body). No markdown fences, no commentary."
    )
    
    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db
        self.factory = ToolFactory()
        self.llm_client = LLMClient(db=db)
    
    async def generate(
        self,
        description: str,
        agent_id: str,
        tool_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate tool code from natural language description.
        
        Args:
            description: Natural language description of desired tool functionality
            agent_id: Agentium ID of the requesting agent (used for tier context)
            tool_name: Optional explicit tool name; derived from description if omitted
            
        Returns:
            Dict with keys: code_template (str), tool_name (str), parameters (List[ToolParameter])
            
        Raises:
            ValueError: If LLM generation fails or code fails security validation
        """
        # Derive tool name from description if not provided
        if tool_name is None:
            tool_name = self._derive_tool_name(description)
        
        # Get agent for LLM client
        agent = self._get_agent(agent_id)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_id}")
        
        # Generate code via LLM
        try:
            gen = await self.llm_client.generate(
                agent=agent,
                user_message=(
                    f"The agent wants to create a tool named '{tool_name}'.\n"
                    f"Request: {description}\n\n"
                    "Return the execute() body that fulfills this request."
                ),
                system_prompt_override=self.SYSTEM_PROMPT,
            )
            raw_code = (gen or {}).get("content", "") or ""
        except Exception as exc:
            raise ValueError(f"Code generation failed: {exc}")
        
        # Clean up markdown fences if present
        code_template = self._clean_code(raw_code)
        
        if not code_template.strip():
            raise ValueError("Code generation produced empty implementation")
        
        # Validate generated code for security
        validation = self.factory.validate_tool_code(code_template)
        if not validation["valid"]:
            raise ValueError(f"Generated code failed validation: {validation['error']}")
        
        return {
            "code_template": code_template,
            "tool_name": tool_name,
            "parameters": []  # For now, all params via **kwargs
        }
    
    def _derive_tool_name(self, description: str) -> str:
        """Derive a valid tool name from the description."""
        # Take first 50 chars, lowercase, replace non-alphanum with underscore
        name = re.sub(r'[^a-z0-9]+', '_', description.lower()[:50]).strip('_')
        return name or "generated_tool"
    
    def _clean_code(self, raw_code: str) -> str:
        """Remove markdown fences and normalize indentation."""
        # Remove leading ```python or ``` fences
        code = re.sub(r"^```[a-zA-Z0-9]*\n", "", raw_code.strip())
        # Remove trailing ```
        code = re.sub(r"\n```$", "", code.strip())
        return dedent(code).strip()
    
    def _get_agent(self, agent_id: str):
        """Fetch agent from database."""
        from backend.models.entities.agents import Agent
        return self.db.query(Agent).filter(Agent.agentium_id == agent_id).first()