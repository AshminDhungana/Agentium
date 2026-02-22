"""
Chat service for Head of Council interactions.
Handles message processing, task creation, context management, and reincarnation.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.models.entities import Agent, HeadOfCouncil, Task, TaskPriority, TaskType
from backend.models.entities.agents import AgentType
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.services.context_manager import context_manager
from backend.services.reincarnation_service import reincarnation_service
from backend.services.clarification_service import clarification_service
from backend.services.model_provider import ModelService


logger = logging.getLogger(__name__)


class ChatService:
    """Service for handling Sovereign ↔ Head of Council chat with reincarnation support."""

    @staticmethod
    async def process_message(head: HeadOfCouncil, message: str, db: Session):
        """
        Process message with context management and potential reincarnation.
        Preserves task state across reincarnations.
        """
        # FIX: Extract config values immediately while session is active
        config = head.get_model_config(db)
        config_id = config.id if config else None
        model_name = config.default_model if config else "default"

        # Register context tracking if not exists
        context_manager.register_agent(
            head.agentium_id,
            model_name
        )

        # Get provider using extracted primitive config_id
        provider = await ModelService.get_provider("sovereign", config_id)
        
        # FIX: Handle case where no model provider is available
        if not provider:
            logger.warning(f"No model provider available for Head {head.agentium_id} (config_id: {config_id})")
            return {
                "content": (
                    "⚠️ **Model Configuration Required**\n\n"
                    "I apologize, Sovereign, but I am currently unable to process your request. "
                    "No AI model provider is configured for my operation.\n\n"
                    "**To resolve this:**\n"
                    "1. Navigate to **Settings → Model Configuration**\n"
                    "2. Add a valid model provider (OpenAI, Anthropic, or local Ollama)\n"
                    "3. Set it as the default for the Head of Council\n"
                    "4. Return to this chat and try again\n\n"
                    "Your command has been noted but cannot be executed until a model is available."
                ),
                "model": "none",
                "error": "no_provider",
                "reincarnated": False,
                "task_created": False,
                "task_id": None
            }

        # Get predecessor context if this agent recently reincarnated
        predecessor_context = reincarnation_service.get_predecessor_context(head, db)

        # Get system prompt and context
        system_prompt = head.get_system_prompt()
        context = await ChatService.get_system_context(db)

        # Build consultation note from predecessor context for reincarnated agents
        consultation_result = None
        if predecessor_context.get("has_predecessor"):
            try:
                consultation_result = clarification_service.consult_supervisor(
                    agent=head,
                    db=db,
                    question="What is my current assignment and status after reincarnation?",
                    context=f"Reincarnated agent. Predecessor: {predecessor_context.get('predecessor_id')}. "
                            f"Incarnation #{predecessor_context.get('incarnation_number', 1)}."
                )
            except Exception as e:
                print(f"⚠️ Consultation failed for {head.agentium_id}: {e}")
                consultation_result = None

        consultation_note = (
            f"\nRecent consultation with parent: {consultation_result['guidance']}"
            if consultation_result
            else ""
        )

        # Inject predecessor wisdom into prompt when available
        predecessor_note = ""
        if predecessor_context.get("has_predecessor") and predecessor_context.get("wisdom_summary"):
            predecessor_note = (
                f"\n\n[Inherited Wisdom from Predecessor {predecessor_context['predecessor_id']}]: "
                f"{predecessor_context['wisdom_summary']}"
            )

        full_prompt = f"""{system_prompt}{predecessor_note}

Current System State:
{context}{consultation_note}

Address the Sovereign respectfully. If they issue a command that requires execution, indicate that you will create a task."""

        # FIX: Handle model generation failures with try/except
        try:
            result = await provider.generate(full_prompt, message)
        except Exception as e:
            logger.error(f"Model generation failed for Head {head.agentium_id}: {str(e)}")
            return {
                "content": (
                    "⚠️ **Model Response Failure**\n\n"
                    "I apologize, Sovereign, but I encountered an error while attempting to generate a response. "
                    f"The model provider reported: `{str(e)[:200]}`\n\n"
                    "**Possible causes:**\n"
                    "- API rate limit exceeded\n"
                    "- Invalid API key or authentication failure\n"
                    "- Model service temporarily unavailable\n"
                    "- Network connectivity issues\n\n"
                    "**Suggested actions:**\n"
                    "1. Check your model provider settings and API keys\n"
                    "2. Verify your internet connection\n"
                    "3. Try again in a moment\n"
                    "4. Consider switching to a backup model provider in Settings\n\n"
                    "Your message has been preserved. Please retry when ready."
                ),
                "model": model_name,
                "error": "generation_failed",
                "error_details": str(e),
                "reincarnated": False,
                "task_created": False,
                "task_id": None
            }

        # Validate result has content
        if not result or not result.get("content"):
            logger.error(f"Empty response from model for Head {head.agentium_id}")
            return {
                "content": (
                    "⚠️ **Empty Model Response**\n\n"
                    "I apologize, Sovereign. The model provider returned an empty response. "
                    "This may indicate a temporary service issue or model overload.\n\n"
                    "Please try again or switch to an alternative model provider."
                ),
                "model": model_name,
                "error": "empty_response",
                "reincarnated": False,
                "task_created": False,
                "task_id": None
            }

        # Update context usage
        tokens_used = result.get("tokens_used", 0)
        context_status = context_manager.update_usage(head.agentium_id, tokens_used)

        # Broadcast response to user's external channels (Unified Inbox)
        # Getting user_id from db session isn't directly passed here typically,
        # but the conversation context should have a linked user. 
        # Alternatively we can broadcast to all admins if we don't have user_id, 
        # but Agentium assumes sovereign = admin. Let's find an active admin.
        from backend.models.entities.user import User
        from backend.services.channel_manager import ChannelManager
        
        # In a multi-tenant system we'd capture the exact user who invoked the chat.
        # For sovereign we just take the first active admin user.
        sovereign_user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        if sovereign_user:
            import asyncio
            asyncio.create_task(
                ChannelManager.broadcast_to_channels(
                    user_id=sovereign_user.id,
                    content=result["content"],
                    db=db,
                    is_silent=True
                )
            )

        # Analyze if we should create a task
        task_info = await ChatService.analyze_for_task(head, message, result["content"], db)

        # Get current task ID if any (for preservation during reincarnation)
        current_task_id = head.current_task_id
        task_progress = None
        if current_task_id:
            current_task = db.query(Task).filter_by(id=current_task_id).first()
            if current_task:
                task_progress = current_task.completion_percentage

        # Check if reincarnation needed (context critical)
        if context_status and context_status.is_critical:
            print(f"🔄 Context critical for {head.agentium_id}, triggering reincarnation...")

            # Get conversation context for summarization
            conversation_context = f"""User: {message}
Agent: {result['content']}
System Context: {context}
Task Created: {task_info.get('created', False)}
Current Task: {current_task_id or 'None'}
Progress: {task_progress or 'N/A'}%"""

            # Execute reincarnation WITH task preservation
            reincarnation_result = await reincarnation_service.check_and_trigger_reincarnation(
                agent=head,
                db=db,
                conversation_context=conversation_context,
                current_task_id=current_task_id,
                task_progress=str(task_progress) if task_progress else None
            )

            if reincarnation_result and reincarnation_result["successor_spawned"]:
                # Continue with successor
                new_head_id = reincarnation_result["successor_id"]
                new_head = db.query(HeadOfCouncil).filter_by(agentium_id=new_head_id).first()

                if new_head:
                    # Get lineage for the new agent
                    lineage_info = clarification_service.get_lineage(new_head, db)

                    response_text = f"""{result["content"]}

[System Notice: I have evolved from {head.agentium_id} to {new_head_id} to serve you with renewed clarity. My context window has been refreshed through reincarnation.]

[Agent Reference: This is incarnation #{reincarnation_result.get('incarnation_number', 1) + 1}. {f"Task {reincarnation_result.get('task_transferred')} transferred to successor." if reincarnation_result.get("task_transferred") else "No active task transferred."}]

[If confused: New agent can consult parent {new_head.parent.agentium_id if new_head.parent else 'None'} or check inherited ethos for predecessor wisdom.]"""

                    return {
                        "content": response_text,
                        "model": result["model"],
                        "reincarnated": True,
                        "old_agent_id": head.agentium_id,
                        "new_agent_id": new_head_id,
                        "incarnation_number": reincarnation_result.get("incarnation_number", 1) + 1,
                        "task_transferred": reincarnation_result.get("task_transferred"),
                        "lineage": lineage_info,
                        "predecessor_context": predecessor_context if predecessor_context.get("has_predecessor") else None,
                        "task_created": task_info.get("created"),
                        "task_id": task_info.get("task_id")
                    }

        return {
            "content": result["content"],
            "model": result["model"],
            "tokens_used": result.get("tokens_used"),
            "latency_ms": result.get("latency_ms"),
            "task_created": task_info.get("created"),
            "task_id": task_info.get("task_id"),
            "reincarnated": False,
            "consultation": consultation_result if consultation_result else None
        }

    @staticmethod
    async def process_confused_agent_query(
        agent: Agent,
        query: str,
        db: Session
    ) -> Dict[str, Any]:
        """
        Handle query from reincarnated agent who is confused about task.
        Consults supervisor and returns guidance.
        """
        # Consult parent/supervisor
        consultation = clarification_service.consult_supervisor(
            agent=agent,
            db=db,
            question=query,
            context="Post-reincarnation confusion"
        )

        # Also get predecessor context
        predecessor = reincarnation_service.get_predecessor_context(agent, db)

        return {
            "consultation": consultation,
            "predecessor_info": predecessor,
            "recommendation": consultation.get("recommendation"),
            "can_escalate": consultation.get("escalation_available"),
            "advice": "Follow parent's guidance or review inherited ethos behavioral rules for [LIFE_X_WISDOM] entries."
        }

    @staticmethod
    async def get_system_context(db: Session) -> str:
        """Get current system state for context."""
        # Count agents by type
        agents = db.query(Agent).all()

        head_count = sum(1 for a in agents if a.agent_type.value == "head_of_council" and a.is_active == True)
        council_count = sum(1 for a in agents if a.agent_type.value == "council_member" and a.is_active == True)
        lead_count = sum(1 for a in agents if a.agent_type.value == "lead_agent" and a.is_active == True)
        task_count = sum(1 for a in agents if a.agent_type.value == "task_agent" and a.is_active == 'Y')

        # Get active tasks
        pending_tasks = db.query(Task).filter(Task.status.in_(["pending", "deliberating", "in_progress"])).count()

        # Get reincarnation stats
        reincarnation_info = ""
        for agent in agents:
            if agent.is_active is True:
                stats = context_manager.get_stats(agent.agentium_id)
                if stats and stats.get('incarnation', 1) > 1:
                    reincarnation_info += f"\n  {agent.agentium_id}: Incarnation {stats['incarnation']}"

        return f"""- Head of Council: {'Active' if head_count > 0 else 'Inactive'}
- Council Members: {council_count} active
- Lead Agents: {lead_count} active
- Task Agents: {task_count} active
- Pending Tasks: {pending_tasks}{reincarnation_info if reincarnation_info else ""}"""

    @staticmethod
    async def analyze_for_task(
        head: HeadOfCouncil,
        prompt: str,
        response: str,
        db: Session
    ) -> Dict[str, Any]:
        """
        Analyze if the message should create a task.
        Looks for execution keywords in both prompt and response.
        """
        execution_keywords = [
            "create", "execute", "run", "analyze", "process", "generate",
            "write", "code", "research", "investigate", "calculate",
            "deploy", "build", "test", "validate"
        ]

        # Check if it seems like a command
        is_command = any(keyword in prompt.lower() for keyword in execution_keywords)

        # Check if Head acknowledged it as a task
        task_acknowledged = any(phrase in response.lower() for phrase in [
            "i shall", "i will", "creating task", "delegating", "assigning",
            "the council will", "lead agents will"
        ])

        if is_command and task_acknowledged:
            # Create a task
            task = Task(
                title=prompt[:100] + "..." if len(prompt) > 100 else prompt,
                description=prompt,
                task_type=TaskType.EXECUTION,
                priority=TaskPriority.NORMAL,
                created_by="sovereign",
                head_of_council_id=head.id,
                requires_deliberation=True
            )

            db.add(task)
            db.commit()

            # Workflow §2: Write plan into Head's Ethos with retry logic
            plan = {
                "objective": prompt[:200],
                "title": task.title,
                "task_id": task.agentium_id,
                "steps": ["deliberation", "delegation", "execution", "review"],
                "created_at": datetime.utcnow().isoformat(),
            }
            try:
                head.update_ethos_with_plan(plan, db, max_retries=3)
                db.commit()
            except RuntimeError as e:
                # Log the failure but don't block task creation
                logger.warning(
                    "Ethos update failed for Head %s during plan write: %s",
                    head.agentium_id, e
                )

            # Use enum comparison instead of string
            council = db.query(Agent).filter(
                Agent.agent_type == AgentType.COUNCIL_MEMBER,
                Agent.is_active == True
            ).all()

            if council:
                task.start_deliberation([c.agentium_id for c in council])
                db.commit()

            return {
                "created": True,
                "task_id": task.agentium_id
            }

        return {"created": False}

    @staticmethod
    async def log_interaction(
        head_agentium_id: str,
        prompt: str,
        response: str,
        config_id: str,
        db: Session
    ):
        """Log chat interaction for audit trail."""
        log = AuditLog.log(
            level=AuditLevel.INFO,
            category=AuditCategory.COMMUNICATION,
            actor_type="agent",
            actor_id=head_agentium_id,
            action="chat_response",
            target_type="conversation",
            target_id=None,
            description="Head of Council responded to Sovereign",
            before_state={"prompt": prompt[:500]},
            after_state={"response": response[:1000]},
            metadata={
                "config_id": config_id,
                "full_prompt_length": len(prompt),
                "full_response_length": len(response)
            }
        )
        db.add(log)
        db.commit()