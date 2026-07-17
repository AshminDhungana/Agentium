"""
Message Bus for Agentium - Redis-backed hierarchical routing.
Enforces: Task(3xxxx) -> Lead(2xxxx) -> Council(1xxxx) -> Head(0xxxx)

"""

import os
import json
import asyncio
import fnmatch
import logging
import redis.asyncio as redis
from typing import Optional, Dict, Any, List, Callable, Set
from datetime import datetime
from dataclasses import dataclass
from contextlib import asynccontextmanager

from backend.models.schemas.messages import AgentMessage, MessageReceipt, RouteResult
from backend.core.vector_store import vector_store, get_vector_store

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limiting per agent tier."""
    HEAD: int = 100     # 0xxxx - Unlimited practically
    COUNCIL: int = 20   # 1xxxx - 20 msg/sec
    LEAD: int = 10      # 2xxxx - 10 msg/sec
    TASK: int = 5       # 3xxxx - 5 msg/sec


class HierarchyValidator:
    """
    Validates agent routing according to Agentium constitution.
    Prevents unauthorized lateral movement and skipping levels.
    """
    
    TIER_MAP = {
        '0': 0,  # Head
        '1': 1,  # Council
        '2': 2,  # Lead
        '3': 3,  # Task
        '4': 4,  # Code Critic    (Section 6.4)
        '5': 5,  # Output Critic  (Section 6.4)
        '6': 6,  # Plan Critic    (Section 6.4)
    }
    
    @classmethod
    def get_tier(cls, agent_id: str) -> int:
        """Extract tier from agentium_id (first digit)."""
        if agent_id == "broadcast":
            return -1
        if len(agent_id) < 5:
            raise ValueError(f"Invalid agent ID format: {agent_id}")
        prefix = agent_id[0]
        return cls.TIER_MAP.get(prefix, -1)
    
    @classmethod
    def can_route(cls, from_id: str, to_id: str, direction: str) -> bool:
        """
        Check if message can flow between agents.
        
        Rules:
        - UP: Can only go to immediate parent tier
        - DOWN: Can go to any child tier  
        - LATERAL: Same tier only
        - BROADCAST: Head only
        """
        if to_id == "broadcast":
            return from_id == "00001"  # Only Head can broadcast
        
        from_tier = cls.get_tier(from_id)
        to_tier = cls.get_tier(to_id)
        
        if direction == "up":
            # Can only escalate one level at a time (unless Head override)
            if from_tier == 3:  # Task -> Lead only
                return to_tier == 2
            elif from_tier == 2:  # Lead -> Council only
                return to_tier == 1
            elif from_tier == 1:  # Council -> Head only
                return to_tier == 0
            elif from_tier == 0:   # Head can message other Heads (but not practical in system)
                return to_tier == 0
        elif direction == "down":
            # Can delegate to immediate children
            if from_tier == 0:  # Head -> Council
                return to_tier == 1
            elif from_tier == 1:  # Council -> Lead
                return to_tier == 2
            elif from_tier == 2:  # Lead -> Task
                return to_tier == 3
        elif direction == "lateral":
            return from_tier == to_tier
        
        return False
    
    @classmethod
    def get_parent_tier_id(cls, agent_id: str) -> str:
        """Get the expected parent tier for an agent."""
        tier = cls.get_tier(agent_id)
        prefix_map = {3: "2", 2: "1", 1: "0"}
        if tier in prefix_map:
            return f"{prefix_map[tier]}xxxx"
        return "00000"

# ═══════════════════════════════════════════════════════════
# CRITIC ROUTING NOTE
# ═══════════════════════════════════════════════════════════
#
# Critic agents (tiers 4, 5, 6 — Code/Output/Plan critics) are
# INTENTIONALLY excluded from the standard HierarchyValidator
# routing rules.  They operate OUTSIDE the democratic chain:
#
#   • Critics do NOT route messages through the hierarchy.
#   • Critic visibility is governed solely by ContextRayTracer:
#     - They can only see message types: execution, critique,
#       critique_result, notification, heartbeat.
#   • Critic verdicts (PASS/REJECT/ESCALATE) are recorded via
#     AuditLog, not via the MessageBus routing pipeline.
#   • Sibling isolation applies: one critic CANNOT see another
#     critic's review output unless explicitly allowed via
#     visible_to patterns.
#
# This design ensures orthogonal failure modes — a compromised
# planning layer cannot influence critic judgement.
# ═══════════════════════════════════════════════════════════


class ContextRayTracer:
    """
    Section 6.4 – Selective Information Flow.

    Stateless helper that determines which messages an agent may see
    based on its *role* (Planner / Executor / Critic) and per-message
    ``visible_to`` patterns.  Sibling isolation is enforced by checking
    that the consuming agent matches at least one ``visible_to`` glob.

    Usage::

        tracer = ContextRayTracer()
        visible = tracer.filter_messages(all_msgs, "30001")
    """

    # ── Role constants ──────────────────────────────────────────────
    ROLE_PLANNER = "PLANNER"
    ROLE_EXECUTOR = "EXECUTOR"
    ROLE_CRITIC = "CRITIC"

    # ── Message-type allow-lists per role ────────────────────────────
    ROLE_VISIBILITY: Dict[str, Set[str]] = {
        ROLE_PLANNER: {
            "intent", "vote_proposal", "vote_cast",
            "constitution_query", "escalation", "notification",
            "liquidation", "knowledge_share", "heartbeat",
            "plan", "idle_task", "delegation",
            "wait_resolved",   # Phase 16: planners need visibility of resumed tasks
        },
        ROLE_EXECUTOR: {
            "delegation", "plan", "execution",
            "escalation", "notification", "heartbeat",
            "idle_task",
            "wait_resolved",   # Phase 16: executors resume work on this event
        },
        ROLE_CRITIC: {
            "execution", "critique", "critique_result",
            "notification", "heartbeat", "delegation",
            "wait_resolved",   # Phase 16: critics may re-evaluate after wait resolution
        },
    }

    # Prefix → role mapping
    _PREFIX_ROLE: Dict[str, str] = {
        '0': ROLE_PLANNER,
        '1': ROLE_PLANNER,
        '2': ROLE_EXECUTOR,
        '3': ROLE_EXECUTOR,
        '4': ROLE_CRITIC,
        '5': ROLE_CRITIC,
        '6': ROLE_CRITIC,
    }

    # ── Public API ──────────────────────────────────────────────────

    @classmethod
    def get_agent_role(cls, agent_id: str) -> str:
        """Map an agentium ID to its role category.

        Returns one of ROLE_PLANNER, ROLE_EXECUTOR, ROLE_CRITIC.
        """
        if not agent_id or agent_id == "broadcast":
            return cls.ROLE_PLANNER  # broadcast is Head-only
        return cls._PREFIX_ROLE.get(agent_id[0], cls.ROLE_EXECUTOR)

    @classmethod
    def is_visible_to(cls, message: AgentMessage, agent_id: str) -> bool:
        """Decide whether *agent_id* is allowed to see *message*.

        Two independent checks must BOTH pass:
        1. The message's ``visible_to`` patterns include the agent.
        2. The message's ``message_type`` is in the agent role's allow-list.
        """
        # 1. visible_to glob check
        patterns = message.visible_to or ["*"]
        glob_match = any(
            fnmatch.fnmatch(agent_id, pat) for pat in patterns
        )
        if not glob_match:
            return False

        # 2. Role-based message-type check
        role = cls.get_agent_role(agent_id)
        allowed_types = cls.ROLE_VISIBILITY.get(role, set())
        return message.message_type in allowed_types

    @classmethod
    def filter_messages(
        cls,
        messages: List[AgentMessage],
        agent_id: str,
    ) -> List[AgentMessage]:
        """Return only the messages that *agent_id* is permitted to see.

        Each surviving message also has its ``context_scope`` applied via
        :meth:`apply_scope`.
        """
        visible: List[AgentMessage] = []
        for msg in messages:
            if cls.is_visible_to(msg, agent_id):
                visible.append(cls.apply_scope(msg, msg.context_scope))

        total = len(messages)
        kept = len(visible)
        if total > 0 and kept < total:
            logger.debug(
                f"[ContextRayTracer] Agent {agent_id}: "
                f"{kept}/{total} messages visible"
            )
        return visible

    @classmethod
    def apply_scope(
        cls,
        message: AgentMessage,
        scope: str,
    ) -> AgentMessage:
        """Return a (potentially) reduced copy of *message* based on *scope*.

        * ``FULL``        – original message, unchanged.
        * ``SUMMARY``     – content truncated to 200 characters.
        * ``SCHEMA_ONLY`` – content cleared; only metadata/structure kept.
        """
        if scope == "FULL":
            return message

        scoped = message.model_copy()
        if scope == "SUMMARY":
            if len(scoped.content) > 200:
                scoped.content = scoped.content[:200] + "…"
        elif scope == "SCHEMA_ONLY":
            scoped.content = ""
            scoped.payload = {
                k: type(v).__name__
                for k, v in (message.payload or {}).items()
            }
        return scoped

    @classmethod
    def build_context(
        cls,
        messages: List[AgentMessage],
        agent_id: str,
    ) -> List[AgentMessage]:
        """High-level convenience: filter + scope in one call.

        Identical to :meth:`filter_messages` (scope is applied inside
        ``filter_messages`` already), provided for semantic clarity.
        """
        return cls.filter_messages(messages, agent_id)


class MessageBus:
    """
    Redis-backed message bus for Agentium.
    Supports Streams (persistent) and Pub/Sub (real-time).
    """
    
    def __init__(self):
        """Init."""

        self._redis: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._subscribers: Dict[str, Set[Callable]] = {}
        self._rate_limits: RateLimitConfig = RateLimitConfig()
        self._last_message_time: Dict[str, float] = {}
        self._running = False
    
    async def connect(self, redis_url: Optional[str] = None):
        """Initialize Redis connection."""
        url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0")
        self._redis = await redis.from_url(url, decode_responses=True)
        self._pubsub = self._redis.pubsub()
        self._running = True
        logger.info(f"MessageBus connected to {url}")
    
    async def disconnect(self):
        """Cleanup Redis connections."""
        self._running = False
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()
    
    def _get_rate_limit(self, agent_id: str) -> int:
        """Get rate limit for agent tier."""
        tier = agent_id[0] if agent_id else "3"
        limiter = {
            '0': self._rate_limits.HEAD,
            '1': self._rate_limits.COUNCIL,
            '2': self._rate_limits.LEAD,
            '3': self._rate_limits.TASK,
        }
        return limiter.get(tier, 5)
    
    async def _check_rate_limit(self, agent_id: str) -> bool:
        """Check if agent has exceeded rate limit."""
        now = datetime.utcnow().timestamp()
        last_time = self._last_message_time.get(agent_id, 0)
        limit = self._get_rate_limit(agent_id)
        
        if now - last_time < (1.0 / limit):
            return False
        
        self._last_message_time[agent_id] = now
        return True
    
    async def publish(self, message: AgentMessage, persistent: bool = True) -> RouteResult:
        """
        Publish message to recipient.
        Persistent messages use Redis Streams, ephemeral use Pub/Sub.
        """
        start_time = datetime.utcnow().timestamp()
        
        # Validation
        if not HierarchyValidator.can_route(
            message.sender_id, 
            message.recipient_id, 
            message.route_direction
        ):
            return RouteResult(
                success=False,
                message_id=message.message_id,
                error=f"Hierarchy violation: {message.sender_id} cannot {message.route_direction} to {message.recipient_id}",
                latency_ms=(datetime.utcnow().timestamp() - start_time) * 1000
            )
        
        # Rate limiting
        if not await self._check_rate_limit(message.sender_id):
            return RouteResult(
                success=False,
                message_id=message.message_id,
                error=f"Rate limit exceeded for agent {message.sender_id}",
                latency_ms=(datetime.utcnow().timestamp() - start_time) * 1000
            )
        
        try:
            if persistent:
                return await self._publish_stream(message)
            else:
                return await self._publish_pubsub(message)
        except Exception as e:
            return RouteResult(
                success=False,
                message_id=message.message_id,
                error=str(e),
                latency_ms=(datetime.utcnow().timestamp() - start_time) * 1000
            )
    
    async def _publish_stream(self, message: AgentMessage) -> RouteResult:
        """Publish to Redis Stream for guaranteed delivery."""
        stream_key = f"agent:{message.recipient_id}:inbox"
        
        entry = message.to_redis_stream()
        msg_id = await self._redis.xadd(
            stream_key,
            entry,
            maxlen=1000,  # Keep last 1000 messages per inbox
            approximate=True
        )
        
        # Also publish for real-time notification
        await self._redis.publish(
            f"channel:{message.recipient_id}",
            json.dumps({"message_id": message.message_id, "type": message.message_type})
        )
        
        return RouteResult(
            success=True,
            message_id=message.message_id,
            path_taken=[message.sender_id, message.recipient_id],
            latency_ms=0.0  # Calculated by caller
        )
    
    async def _publish_pubsub(self, message: AgentMessage) -> RouteResult:
        """Publish via Pub/Sub for ephemeral messages."""
        channel = f"channel:{message.recipient_id}"
        await self._redis.publish(channel, message.json())
        return RouteResult(success=True, message_id=message.message_id, path_taken=[message.sender_id])
    
    async def route_up(self, message: AgentMessage, auto_find_parent: bool = True) -> RouteResult:
        """
        Route message up the hierarchy (escalation).
        Task -> Lead -> Council -> Head
        """
        if auto_find_parent and HierarchyValidator.get_tier(message.sender_id) > 0:
            # Find actual parent from database
            parent_id = await self._get_parent_id(message.sender_id)
            if parent_id:
                message.recipient_id = parent_id
        
        message.route_direction = "up"
        
        # Inject constitutional context for escalations
        if message.message_type in ["escalation", "violation"]:
            context = await self._enrich_context(message)
            message.rag_context = context
        
        return await self.publish(message)
    
    async def route_down(self, message: AgentMessage) -> RouteResult:
        """
        Route message down the hierarchy (delegation).
        Head -> Council -> Lead -> Task
        """
        if not message.recipient_id:
            return RouteResult(
                success=False,
                message_id=message.message_id,
                error=f"route_down requires a recipient, got {message.recipient_id!r}",
            )
        message.route_direction = "down"
        return await self.publish(message)
    
    async def broadcast_from_head(self, message: AgentMessage) -> List[RouteResult]:
        """
        Broadcast to all agents (Head 0xxxx only).
        Returns list of results for each recipient.
        """
        if message.sender_id != "00001":
            return [RouteResult(
                success=False,
                message_id=message.message_id,
                error="Only Head of Council (00001) can broadcast"
            )]
        
        results = []
        from backend.models.entities.agents import Agent, AgentType
        active_agents = self.db.query(Agent).filter(
            Agent.status == "active",
            Agent.agent_type != AgentType.HEAD_OF_COUNCIL
        ).all()

        for agent in active_agents:
            msg_copy = message.copy()
            msg_copy.recipient_id = agent.agentium_id
            result = await self.publish(msg_copy)
            results.append(result)
        
        return results
    
    async def subscribe(self, agent_id: str, callback: Callable[[AgentMessage], Any]):
        """
        Subscribe agent to incoming messages.
        Sets up both Stream consumer and Pub/Sub listener.
        """
        if agent_id not in self._subscribers:
            self._subscribers[agent_id] = set()
        self._subscribers[agent_id].add(callback)
        
        # Subscribe to Pub/Sub channel
        await self._pubsub.subscribe(f"channel:{agent_id}")
        
        # Start listening
        asyncio.create_task(self._listen_pubsub(agent_id, callback))
    
    async def _listen_pubsub(self, agent_id: str, callback: Callable):
        """Background task to listen for Pub/Sub messages."""
        try:
            async for message in self._pubsub.listen():
                if message['type'] == 'message':
                    data = json.loads(message['data'])
                    # Only notify, actual message fetched from Stream
                    if data.get('type') == 'notification':
                        await callback(AgentMessage(**data))
        except Exception as e:
            logger.error(f"Pub/Sub listen error for {agent_id}: {e}")
    
    async def consume_stream(
        self,
        agent_id: str,
        count: int = 1,
        apply_ray_tracing: bool = True,
    ) -> List[AgentMessage]:
        """
        Consume messages from agent's inbox (non-blocking).
        Used for polling pattern or batch processing.

        Section 6.4: When *apply_ray_tracing* is ``True`` (default),
        the returned list is filtered through :class:`ContextRayTracer`
        so that only messages the agent's role is permitted to see are
        included, and each message's ``context_scope`` is applied.
        """
        stream_key = f"agent:{agent_id}:inbox"
        group_name = f"group:{agent_id}"
        
        try:
            # Try to read new messages
            messages = await self._redis.xread(
                {stream_key: '>'},  # Read from last point
                count=count,
                block=1000
            )
            
            results = []
            if messages:
                for stream, entries in messages:
                    for msg_id, fields in entries:
                        # Convert back to AgentMessage
                        msg_data = dict(fields)
                        msg_data['message_id'] = msg_data.get('message_id', msg_id)
                        
                        # ── DLQ Threshold Check ──
                        fail_key = f"message:fails:{msg_id}"
                        fails = int(await self._redis.get(fail_key) or 0)
                        if fails > 3:
                            # Route to Dead-Letter Queue
                            await self._redis.xadd("agent:dlq:stream", fields)
                            await self._redis.xdel(stream_key, msg_id)
                            await self._redis.delete(fail_key)
                            logger.info(f"[DLQ] Moved message {msg_id} to DLQ stream after {fails} failures.")
                            continue

                        # Deserialise visible_to from JSON string
                        if 'visible_to' in msg_data and isinstance(msg_data['visible_to'], str):
                            try:
                                msg_data['visible_to'] = json.loads(msg_data['visible_to'])
                            except (json.JSONDecodeError, TypeError):
                                msg_data['visible_to'] = ['*']
                        results.append(AgentMessage(**msg_data))

            # Section 6.4: apply role-based context filtering
            if apply_ray_tracing and results:
                results = ContextRayTracer.filter_messages(results, agent_id)

            return results
        except Exception as e:
            logger.error(f"Stream consume error: {e}")
            return []
    
    async def acknowledge(self, receipt: MessageReceipt):
        """Acknowledge message processing."""
        # Store in processed set
        key = f"agent:{receipt.recipient_id}:processed"
        await self._redis.sadd(key, receipt.message_id)
        await self._redis.expire(key, 86400)  # Keep 24h

    async def record_failure(self, message_id: str) -> int:
        """Record processing failure for a message. Returns current fail count."""
        fail_key = f"message:fails:{message_id}"
        fails = await self._redis.incr(fail_key)
        await self._redis.expire(fail_key, 86400)  # Keep track for 24h
        return fails

    async def replay_dlq(self, count: int = 100) -> int:
        """
        Replay messages from the DLQ back to their original recipient streams.
        Useful for admin recovery after fixing a systemic parsing error.
        """
        stream_key = "agent:dlq:stream"
        try:
            messages = await self._redis.xread({stream_key: '0-0'}, count=count)
        except Exception:
            return 0
            
        replayed = 0
        if messages:
            for stream, entries in messages:
                for msg_id, fields in entries:
                    msg_data = dict(fields)
                    recipient_id = msg_data.get(b'recipient_id') or msg_data.get('recipient_id')
                    
                    if isinstance(recipient_id, bytes):
                        recipient_id = recipient_id.decode('utf-8')
                        
                    if recipient_id:
                        # Re-publish to the original recipient's inbox
                        await self._redis.xadd(f"agent:{recipient_id}:inbox", fields)
                        # Remove from DLQ
                        await self._redis.xdel(stream_key, msg_id)
                        replayed += 1
                        
        return replayed
    
    async def _get_parent_id(self, agent_id: str) -> Optional[str]:
        """
        Query database to find parent agent.
        """
        try:
            return await asyncio.to_thread(self._get_parent_id_sync, agent_id)
        except Exception as e:
            logger.error(f"Parent lookup error for {agent_id}: {e}")
            return self._get_pattern_parent(agent_id)

    def _get_parent_id_sync(self, agent_id: str) -> Optional[str]:
        """Synchronous implementation of parent lookup."""
        from backend.models.database import get_db_context
        from backend.models.entities.agents import Agent
        from sqlalchemy import select

        try:
            with get_db_context() as session:
                # Find the agent
                result = session.execute(
                    select(Agent).where(Agent.agentium_id == agent_id)
                )
                agent = result.scalars().first()
                
                if not agent or not agent.parent_id:
                    return None
                
                # Find the parent
                parent_result = session.execute(
                    select(Agent).where(Agent.id == agent.parent_id)
                )
                parent = parent_result.scalars().first()
                
                if parent:
                    return parent.agentium_id
        except ImportError:
            pass
        except Exception as e:
            logger.error(f"Sync parent lookup error: {e}")
            
        return None

    def _get_pattern_parent(self, agent_id: str) -> str:
        """Fallback to pattern-based parent ID."""
        return HierarchyValidator.get_parent_tier_id(agent_id)
    
    async def _enrich_context(self, message: AgentMessage) -> Optional[Dict[str, Any]]:
        """Enrich message with Vector DB context for escalations."""
        try:
            store = get_vector_store()
            # Query constitution for relevant articles
            constitution_results = store.query_constitution(
                query=message.content,
                n_results=3
            )
            
            # Get hierarchical context based on sender tier
            tier_map = {
                '0': 'head', '1': 'council', '2': 'lead', '3': 'task',
                '4': 'critic', '5': 'critic', '6': 'critic',
            }
            agent_type = tier_map.get(message.sender_id[0], 'task')
            
            context = store.query_hierarchical_context(
                agent_type=agent_type,
                task_description=message.content,
                n_results=5
            )
            
            return {
                'constitution': constitution_results,
                'hierarchical_context': context,
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Context enrichment error: {e}")
            return None
    
    async def health_check(self) -> Dict[str, Any]:
        """Check message bus health."""
        try:
            info = await self._redis.info('server')
            return {
                'status': 'healthy',
                'redis_version': info.get('redis_version'),
                'connected_clients': info.get('connected_clients'),
                'used_memory_human': info.get('used_memory_human')
            }
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}


# Global instance
message_bus = MessageBus()


async def get_message_bus() -> MessageBus:
    """Get initialized message bus."""
    if message_bus._redis is None:
        await message_bus.connect()
    return message_bus