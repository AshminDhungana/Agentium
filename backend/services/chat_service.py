"""
Chat service for Head of Council interactions.
Handles message processing, task creation, context management, and reincarnation.
"""

import logging
import httpx
from datetime import datetime
import asyncio
from typing import Dict, Any, Optional, List, Callable, Awaitable
from sqlalchemy.orm import Session

from backend.models.entities import Agent, HeadOfCouncil, Task, TaskPriority, TaskType, UserModelConfig
from backend.models.entities.agents import AgentType
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.services.context_manager import context_manager
from backend.services.reincarnation_service import reincarnation_service
from backend.services.clarification_service import clarification_service
from backend.services.model_provider import ModelService
from backend.services.media_interceptor import MediaInterceptor
from backend.services.decision_engine import DecisionEngine, DecisionAction
from backend.core.llm_client import LLMClient
from backend.models.entities.user_config import ConnectionStatus
from backend.models.entities.chat_message import ChatMessage as ChatMsg

import uuid
from backend.models.entities.chat_message import ChatMessage as ChatMessageEntity
from backend.services.structured_input_service import render_external_text
from backend.models.schemas.structured_input import StructuredInputCard as _SIC

ws_manager = None

logger = logging.getLogger(__name__)


class ChatService:
    """Service for handling Sovereign ↔ Head of Council chat with reincarnation support."""

    @staticmethod
    def _load_chat_history(
        db: Session,
        user_id: Optional[str],
        max_turns: int = 30,
    ) -> List[Dict[str, str]]:
        """
        Return prior conversation turns as OpenAI-style role/content dicts
        (oldest first) so the model can see the full thread, not just the
        current message.

        Only persists user/assistant turns (sovereign -> user,
        head_of_council -> assistant).  System notices, errors, and reincarnation
        text are skipped to keep the prompt clean.  The most recent ``max_turns``
        messages are kept to bound prompt size.
        """
        if not user_id:
            return []

        rows = (
            db.query(ChatMsg)
            .filter(ChatMsg.user_id == user_id, ChatMsg.is_deleted == "N")
            .filter(ChatMsg.role.in_(["sovereign", "head_of_council"]))
            .order_by(ChatMsg.created_at.asc())
            .all()
        )

        # Keep only the most recent turns to bound prompt size.
        rows = rows[-max_turns:]

        role_map = {"sovereign": "user", "head_of_council": "assistant"}
        history: List[Dict[str, str]] = []
        for r in rows:
            mapped = role_map.get(r.role)
            if mapped and r.content and r.content.strip():
                history.append({"role": mapped, "content": r.content})
        return history

    @staticmethod
    def send_structured_card(card: "_SIC", db: Session, user_id: str) -> dict:
        """Persist an agent-issued structured input card and broadcast it.

        Fire-and-forget: the WS broadcast is scheduled on the running loop so the
        caller (tool or REST endpoint) is not blocked on socket I/O.
        """
        global ws_manager
        msg = ChatMessageEntity(
            id=str(uuid.uuid4()),
            user_id=str(user_id),
            role="head_of_council",
            content=card.title or "Please answer the following:",
            message_type="input_card",
            message_metadata={"card": card.model_dump()},
            created_at=datetime.utcnow(),
            is_deleted="N",
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        try:
            if ws_manager is None:
                from backend.api.routes.websocket import manager as ws_manager
            loop = asyncio.get_event_loop()
            loop.create_task(ws_manager.broadcast({
                "type": "message",
                "role": "head_of_council",
                "message": msg.to_dict(),
                "metadata": {"card": card.model_dump()},
                "external_text": render_external_text(card),
            }))
        except Exception:
            logger.warning("Card broadcast scheduling failed", exc_info=True)
        return msg.to_dict()

    @staticmethod
    async def process_message(head: HeadOfCouncil, message: str, db: Session, extra_metadata: Optional[dict] = None, on_delta: Optional[Callable[[str], Awaitable[None]]] = None, cancel_event: Optional[asyncio.Event] = None):
        """
        Process message with context management and potential reincarnation.
        Preserves task state across reincarnations.
        """
        # FIX: Extract config values immediately while session is active
        config = head.get_model_config(db)
        config_id = config.id if config else None
        model_name = config.default_model if config else "default"

        # ── FALLBACK: Head has no preferred_config_id — use the global default ──
        # This happens on fresh deploys before the agent is assigned a config.
        if not config_id:
            try:
                default_config = (
                    db.query(UserModelConfig)
                    .filter(UserModelConfig.is_default == True)
                    .filter(UserModelConfig.status == ConnectionStatus.ACTIVE)
                    .first()
                )
                if default_config:
                    config_id = str(default_config.id)
                    model_name = default_config.default_model
                    logger.info(
                        f"Head {head.agentium_id} has no preferred_config_id — "
                        f"falling back to default config '{default_config.config_name}' ({config_id})"
                    )
                    # Persist the link so we don't fall back on every request
                    try:
                        head.preferred_config_id = config_id
                        db.commit()
                        logger.info(f"✅ Persisted default model config to Head {head.agentium_id}")
                    except Exception as persist_err:
                        logger.warning(f"Could not persist preferred_config_id to Head: {persist_err}")
                        db.rollback()
            except Exception as fallback_err:
                logger.warning(f"Default config fallback failed for Head {head.agentium_id}: {fallback_err}")
        # ─────────────────────────────────────────────────────────────────────────

        # ── Persist the inbound (user) turn BEFORE any model round-trip ──────────
        # The user's message — including structured card answers carried in
        # extra_metadata["card_response"] — must be recorded even when no model
        # provider is configured.  The old persistence code lived only in the
        # post-LLM block, so a missing provider (CI, headless deploys) silently
        # dropped the inbound message and any attached card answer.
        from backend.models.entities.user import User
        import uuid as _uuid
        sovereign_user = db.query(User).filter_by(is_admin=True, is_active=True).first()

        # ── Build token-efficient chat context (Task 2.1) ─────────────────────
        # Load the compacted history (sliding window + pinned first message) and
        # any rolling summary, BEFORE persisting the current turn so history
        # reflects turns strictly prior to this one.
        from backend.services.chat_context import (
            ChatContextBuilder,
            load_summary,
            format_summary_for_prompt,
            set_chat_request,
            clear_chat_request,
            summarize_history,
        )
        from backend.services.user_preference_service import UserPreferenceService

        window_size = 10
        try:
            pref_svc = UserPreferenceService(db)
            ws = pref_svc.get_value(
                "chat.context_window_size",
                user_id=sovereign_user.id if sovereign_user else None,
            )
            if ws is not None:
                window_size = int(ws)
        except Exception:
            pass

        summary_json = None
        summary_text = ""
        if sovereign_user:
            try:
                summary_json = await load_summary(str(sovereign_user.id))
                if summary_json:
                    summary_text = format_summary_for_prompt(summary_json)
            except Exception:
                summary_json = None

        history = []
        context_compressed = False
        raw_turn_count = 0
        if sovereign_user:
            built = ChatContextBuilder(window_size=window_size).build(
                db, str(sovereign_user.id), summary=summary_json
            )
            history = built["history"]
            context_compressed = built["context_compressed"]
            raw_turn_count = built["raw_turn_count"]

        if sovereign_user:
            try:
                db.add(ChatMsg(
                    id=str(_uuid.uuid4()),
                    user_id=str(sovereign_user.id),
                    role="sovereign",
                    content=message,
                    message_metadata={**{"source": "websocket"}, **(extra_metadata or {})},
                ))
                db.commit()
            except Exception as _persist_err:
                logger.warning(f"ChatMessage (inbound) persist failed (non-fatal): {_persist_err}")
                try:
                    db.rollback()
                except Exception:
                    pass

        # Register context tracking if not exists
        context_manager.register_agent(
            head.agentium_id,
            model_name
        )

        # ── Governance command fast-path ───────────────────────────────────────
        # Explicit provisioning directives are executed deterministically through
        # the service layer and short-circuit the LLM so the Head cannot merely
        # *declare* intent. Actor = Head (the Sovereign's only chat counterpart).
        from backend.services.governance_command_service import GovernanceCommandService
        gov_command = GovernanceCommandService.detect_command(message)
        if gov_command:
            try:
                gov_result = GovernanceCommandService.execute(gov_command, head, db)
                if sovereign_user:
                    try:
                        db.add(ChatMsg(
                            id=str(_uuid.uuid4()),
                            user_id=str(sovereign_user.id),
                            role="head_of_council",
                            content=gov_result["content"],
                            message_metadata={
                                "agent_id": head.agentium_id,
                                "governance_action": gov_result["action"],
                            },
                        ))
                        db.commit()
                    except Exception as _gov_persist_err:
                        logger.warning(f"Governance confirmation persist failed: {_gov_persist_err}")
                return {
                    "content": gov_result["content"],
                    "model": "governance-command",
                    "task_created": gov_result.get("action") == "create_task",
                    "task_id": gov_result.get("task_id"),
                    "agent_spawned": gov_result.get("agentium_id"),
                    "reincarnated": False,
                }
            except Exception as gov_exc:
                logger.error(f"Governance command execution failed: {gov_exc}")
                # Fall through to the normal LLM path on failure.

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
                logger.error(f"⚠️ Consultation failed for {head.agentium_id}: {e}")
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

        summary_block = ""
        if summary_text:
            summary_block = (
                "\n\n[Conversation summary — earlier turns were compressed to "
                "save tokens]\n" + summary_text
            )

        full_prompt = f"""{system_prompt}{predecessor_note}{summary_block}

Current System State:
{context}{consultation_note}

Address the Sovereign respectfully. If they issue a command that requires execution, indicate that you will create a task."""

        # Switch to tool-aware generation so the Head agent can call deep_think
        # and any other registered tool during conversational turns.
        # generate_with_agent_tools() returns the same dict shape as
        # provider.generate() {content, model, tokens_used, latency_ms, …}
        # so all downstream code (reincarnation check, audit log, etc.) is
        # completely unaffected.
        # FIX: Handle model generation failures with try/except
        cache_key = f"chat:{sovereign_user.id}" if sovereign_user else None
        if sovereign_user:
            set_chat_request(user_id=str(sovereign_user.id), db=db)
        try:
            # Phase 19.3 (Task 14): provider failover chain so a throttled/expired
            # Head key rolls over to a sibling key / cross-provider / local Ollama.
            from backend.services.api_key_manager import api_key_manager
            fallback_configs = (
                api_key_manager.get_fallback_config_ids(config_id)
                if config_id
                else []
            )
            llm_client = LLMClient(db=db)
            result = await llm_client.generate_with_tools(
                agent=head,
                user_message=message,
                db=db,
                config_id=config_id,
                fallback_configs=fallback_configs,
                system_prompt_override=full_prompt,
                agent_tier=f"{head.agentium_id[0]}xxxx",
                history=history,
                on_delta=on_delta,
                cancel_event=cancel_event,
                prompt_cache_key=cache_key,
            )
        except Exception as e:
            clear_chat_request()
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
            clear_chat_request()
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

        # ── Attach context-compaction metadata (Task 2.1) ─────────────────────
        from backend.services.chat_context import estimate_tokens

        result["context_compressed"] = context_compressed
        result["raw_turn_count"] = raw_turn_count
        result["estimated_tokens"] = estimate_tokens(history, full_prompt)
        logger.info(
            "Chat context: turns=%s window=%s compressed=%s est_tokens=%s",
            raw_turn_count, window_size, context_compressed, result["estimated_tokens"],
        )
        # Release the per-request chat context used by the full-history tools.
        clear_chat_request()

        # ── Background summarization (Layer 2) ─────────────────────────────────
        # Condense overflow turns into a rolling summary for future turns. Runs
        # fire-and-forget so it never blocks the user-facing response.
        if sovereign_user and raw_turn_count > window_size + 1:
            try:
                import asyncio as _asyncio

                _asyncio.create_task(
                    summarize_history(db, str(sovereign_user.id), config_id)
                )
            except Exception as _summ_err:  # pragma: no cover - best-effort
                logger.debug("Chat summarization schedule failed: %s", _summ_err)

        # Update context usage
        tokens_used = result.get("tokens_used", 0)
        context_status = context_manager.update_usage(head.agentium_id, tokens_used)

        # ── System-Generated Media Interception (Issue #11) ────────────────────
        # Intercept media URLs in LLM response, download & store permanently,
        # rewrite content with storage URLs before persistence + broadcast.
        if sovereign_user:
            try:
                # Reuse a single httpx client for all downloads in this request
                async with httpx.AsyncClient(timeout=MediaInterceptor.DOWNLOAD_TIMEOUT) as http_client:
                    result["content"], media_urls = await MediaInterceptor.intercept_and_store(
                        text=result["content"],
                        user_id=str(sovereign_user.id),
                        db=db,
                        http_client=http_client
                    )
                    # Attach media URLs to result for metadata persistence
                    if media_urls:
                        result["media_urls"] = media_urls
            except Exception as e:
                # Graceful degradation: log but don't block response
                logger.warning(f"[ChatService] Media interception failed (non-fatal): {e}")
        # ────────────────────────────────────────────────────────────────────────

        # Broadcast response to user's external channels (Unified Inbox)
        from backend.services.channel_manager import ChannelManager

        # ── Persist the Head-of-Council turn.  The inbound (user) turn is ──
        #    persisted earlier, before the model round-trip, so it is never lost.
        if sovereign_user:
            try:
                msg_id = str(_uuid.uuid4())
                db.add(ChatMsg(
                    id=msg_id,
                    user_id=str(sovereign_user.id),
                    role="head_of_council",
                    content=result["content"],
                    message_metadata={
                        "agent_id": head.agentium_id,
                        "model": result.get("model", model_name),
                        "media_urls": result.get("media_urls", []),
                    },
                ))
                db.commit()
            except Exception as _persist_err:
                logger.warning(f"ChatMessage (outbound) persist failed (non-fatal): {_persist_err}")
                try:
                    db.rollback()
                except Exception:
                    pass
        # ─────────────────────────────────────────────────────────────────────

        if sovereign_user:
            import asyncio
            asyncio.create_task(
                ChannelManager.broadcast_to_channels(
                    user_id=sovereign_user.id,
                    content=result["content"],
                    db=db,
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
            logger.info(f"🔄 Context critical for {head.agentium_id}, triggering reincarnation...")

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
        Decide whether the message should create a task using the unified
        DecisionEngine instead of keyword/acknowledgment heuristics.
        """
        from backend.services.decision_engine import DecisionEngine, DecisionAction

        decision = await DecisionEngine().decide(head, prompt, db)
        if decision.action is not DecisionAction.CREATE_TASK:
            return {"created": False}

        # Persistence requires a live session; callers without one (e.g.
        # offline decision checks) still receive the decision outcome.
        if db is None:
            return {"created": True}

        task = Task(
            title=prompt[:100] + "..." if len(prompt) > 100 else prompt,
            description=decision.task_brief or prompt,
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            created_by="sovereign",
            head_of_council_id=head.id,
            requires_deliberation=True,
        )
        db.add(task)
        db.commit()

        # Trace this task back to the decision that spawned it.
        task.decision_id = decision.decision_id
        db.commit()

        plan = {
            "objective": (decision.task_brief or prompt)[:200],
            "title": task.title,
            "task_id": task.agentium_id,
            "steps": ["deliberation", "delegation", "execution", "review"],
            "created_at": datetime.utcnow().isoformat(),
        }
        try:
            head.update_ethos_with_plan(plan, db, max_retries=3)
            db.commit()
        except RuntimeError as e:
            logger.warning(
                "Ethos update failed for Head %s during plan write: %s",
                head.agentium_id, e
            )

        council = db.query(Agent).filter(
            Agent.agent_type == AgentType.COUNCIL_MEMBER,
            Agent.is_active == True,
        ).all()
        if council:
            task.start_deliberation([c.agentium_id for c in council])
            db.commit()

        return {"created": True, "task_id": task.agentium_id}

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