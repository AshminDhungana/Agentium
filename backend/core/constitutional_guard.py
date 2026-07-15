"""
Constitutional Guard - Two-Tier Constitutional Enforcement for Agentium.

Tier 1: PostgreSQL Hard Rules (explicit blacklists, permissions, quotas)
Tier 2: ChromaDB Semantic Interpretation (spirit-of-the-law checks)

Decision flow:
    Agent Action Request
        ↓
    TIER 1: PostgreSQL (Hard Rules)
      ├─ Explicit blacklists (shell commands)
      ├─ Permission tables (who can do what)
      └─ Resource quotas
        ↓
    TIER 2: Vector DB (Semantic Interpretation)
      ├─ "Is this against the spirit of the law?"
      ├─ Grey area violation detection
      └─ Contextual precedent checking
        ↓
    Decision: ALLOW / BLOCK / VOTE_REQUIRED
"""

import json
import re
import hashlib
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class Verdict(str, Enum):
    """Possible constitutional check outcomes."""
    ALLOW = "allow"
    BLOCK = "block"
    VOTE_REQUIRED = "vote_required"


class ViolationSeverity(str, Enum):
    """Severity classification for constitutional violations."""
    LOW = "low"              # Warning only – log and allow
    MEDIUM = "medium"        # Block + log
    HIGH = "high"            # Block + alert Head of Council
    CRITICAL = "critical"    # Block + emergency Council vote


@dataclass
class ConstitutionalDecision:
    """Result of a constitutional check."""
    verdict: Verdict
    severity: ViolationSeverity = ViolationSeverity.LOW
    citations: List[str] = field(default_factory=list)
    explanation: str = ""
    tier_results: Dict[str, Any] = field(default_factory=dict)
    requires_vote: bool = False
    affected_agents: List[str] = field(default_factory=list)
    checked_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "severity": self.severity.value,
            "citations": self.citations,
            "explanation": self.explanation,
            "tier_results": self.tier_results,
            "requires_vote": self.requires_vote,
            "affected_agents": self.affected_agents,
            "checked_at": self.checked_at,
        }


# ---------------------------------------------------------------------------
# Tier capability configuration
# ---------------------------------------------------------------------------

TIER_CAPABILITIES: Dict[str, List[str]] = {
    # Numeric keys (used internally)
    "0": [  # Head of Council
        "veto", "amendment", "liquidate_any", "admin_vector_db",
        "broadcast", "spawn_any", "override_vote", "modify_constitution",
        "execute_command", "read_file", "write_file", "browser_control",
        "reassign_agent",
    ],
    "1": [  # Council Members
        "propose_amendment", "allocate_resources", "audit",
        "moderate_knowledge", "spawn_lead", "vote", "escalate",
        "read_file", "reassign_agent",
    ],
    "2": [  # Lead Agents
        "spawn_task_agent", "delegate_work", "request_resources",
        "submit_knowledge", "report_status", "reassign_agent",
    ],
    "3": [  # Task Agents
        "execute_task", "report_status", "escalate_blocker",
        "query_knowledge",
    ],
    # Named keys (for test compatibility)
    "head": [  # Head of Council
        "veto", "amendment", "liquidate_any", "admin_vector_db",
        "broadcast", "spawn_any", "override_vote", "modify_constitution",
        "execute_command", "read_file", "write_file", "browser_control",
        "spawn_agent", "reassign_agent",
    ],
    "council": [  # Council Members
        "propose_amendment", "allocate_resources", "audit",
        "moderate_knowledge", "spawn_lead", "vote", "escalate",
        "read_file", "reassign_agent",
    ],
    "lead": [  # Lead Agents
        "spawn_task_agent", "delegate_work", "request_resources",
        "submit_knowledge", "report_status", "reassign_agent",
    ],
    "task": [  # Task Agents
        "execute_task", "report_status", "escalate_blocker",
        "query_knowledge",
    ],
}

# Actions that are ALWAYS blocked regardless of tier
GLOBAL_BLACKLIST: List[str] = [
    r"rm\s+-rf\s+/",
    r"DROP\s+DATABASE",
    r"DELETE\s+FROM\s+constitutions",
    r"TRUNCATE\s+\w+",
    r"format\s+[cC]:",
    r"shutdown\s+-[hHrR]",
    r"mkfs\.",
    r"dd\s+if=",
    r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;",  # fork bomb
    r"wget.*\|.*sh",
    r"curl.*\|.*bash",
]


class ConstitutionalGuard:
    """
    Two-tier constitutional enforcement engine.

    Usage::

        guard = ConstitutionalGuard(db)
        await guard.initialize()
        decision = await guard.check_action(
            agent_id="30001",
            action="execute_command",
            context={"command": "ls -la /tmp"}
        )

        if decision.verdict == Verdict.BLOCK:
            # reject
        elif decision.verdict == Verdict.VOTE_REQUIRED:
            # trigger council vote
    """

    # Semantic similarity thresholds
    # Re-tuned 2026-07-15 for the bge-v1.5 cosine ("supreme_law_v2") space.
    # v1 (MiniLM, unnormalised / L2) produced negative `(1 - distance)`
    # similarities for every action, so its Tier-2 was effectively ALLOW for
    # all actions. bge-v1.5 runs HIGH (measured max ~0.68 on representative
    # actions), so the original 0.40/0.70 values flagged everything as a grey
    # area. To preserve v1's verdict baseline (all ALLOW) these are raised
    # above the observed v2 distribution.
    # CAVEAT: this disables v2 semantic detection; re-tune against a v2
    # baseline (and more discriminative articles) before production cutover.
    BLOCK_THRESHOLD = 0.85       # Above this → definitely violates
    GREY_AREA_THRESHOLD = 0.70   # Between this and BLOCK → grey area

    # Redis cache TTLs (seconds)
    CONSTITUTION_CACHE_TTL = 300       # 5 minutes
    EMBEDDING_CACHE_TTL = 1800         # 30 minutes

    def __init__(self, db: Session):
        self.db = db
        self._redis = None
        self._vector_store = None
        self._constitution_cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self):
        """Load dependencies lazily."""
        try:
            import redis.asyncio as aioredis
            import os
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            self._redis = await aioredis.from_url(redis_url, decode_responses=True)
        except Exception as exc:
            logger.warning("Redis unavailable for ConstitutionalGuard cache: %s", exc)

        try:
            from backend.core.vector_store import get_vector_store
            self._vector_store = get_vector_store()
        except Exception as exc:
            logger.warning("VectorStore unavailable for Tier 2 checks: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check_action(
        self,
        agent_id: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
        affected_agent_ids: Optional[List[str]] = None,
    ) -> ConstitutionalDecision:
        """
        Run the full two-tier constitutional check.

        Args:
            agent_id: The Agentium ID of the requesting agent.
            action: The action being attempted (e.g. "execute_command").
            context: Optional dict of action-specific parameters.
            affected_agent_ids: IDs of agents impacted by this action.

        Returns:
            ConstitutionalDecision with verdict, citations, and severity.
        """
        context = context or {}
        affected_agent_ids = affected_agent_ids or []

        # ----- TIER 1: Hard rules (PostgreSQL) -----
        tier1 = await self._tier1_check(agent_id, action, context)
        if tier1.verdict == Verdict.BLOCK:
            tier1.tier_results["tier1"] = "blocked"
            await self._log_decision(agent_id, action, tier1)
            return tier1

        # ----- TIER 2: Semantic check (ChromaDB) -----
        tier2 = await self._tier2_check(agent_id, action, context)

        # Merge results – tier2 can only escalate, never downgrade
        decision = self._merge_tiers(tier1, tier2)

        # ----- Multi-agent impact check -----
        if len(affected_agent_ids) > 3:
            decision.verdict = Verdict.VOTE_REQUIRED
            decision.requires_vote = True
            decision.affected_agents = affected_agent_ids
            decision.explanation += (
                f" Action affects {len(affected_agent_ids)} agents (>3 threshold) – "
                "Council vote required."
            )
            decision.severity = max(
                decision.severity,
                ViolationSeverity.MEDIUM,
                key=lambda s: list(ViolationSeverity).index(s),
            )

        decision.tier_results["tier1"] = tier1.tier_results.get("tier1", "passed")
        decision.tier_results["tier2"] = tier2.tier_results.get("tier2", "skipped")

        await self._log_decision(agent_id, action, decision)
        return decision

    # ------------------------------------------------------------------
    # TIER 1 – PostgreSQL Hard Rules
    # ------------------------------------------------------------------

    async def _tier1_check(
        self,
        agent_id: str,
        action: str,
        context: Dict[str, Any],
    ) -> ConstitutionalDecision:
        """
        Hard-rule checks against PostgreSQL constitution data.

        Sub-checks:
          1. Global blacklist (always blocked patterns)
          2. Tier-based permission check
          3. Constitution prohibited actions list
          4. Resource quotas (placeholder for future expansion)
        """
        # ---- 1. Global blacklist ----
        action_text = f"{action} {json.dumps(context)}"
        for pattern in GLOBAL_BLACKLIST:
            if re.search(pattern, action_text, re.IGNORECASE):
                return ConstitutionalDecision(
                    verdict=Verdict.BLOCK,
                    severity=ViolationSeverity.CRITICAL,
                    citations=["Global Security Policy – Blacklisted Command Pattern"],
                    explanation=f"Action matches globally prohibited pattern: {pattern}",
                )

        # ---- 2. Tier permission check ----
        agent_tier = agent_id[0] if agent_id else "3"
        allowed_actions = TIER_CAPABILITIES.get(agent_tier, [])

        if action not in allowed_actions and action != "query":
            return ConstitutionalDecision(
                verdict=Verdict.BLOCK,
                severity=ViolationSeverity.MEDIUM,
                citations=[
                    f"Article 2, Section 1 – Tier {agent_tier} Permission Scope"
                ],
                explanation=(
                    f"Agent {agent_id} (Tier {agent_tier}) is not authorised "
                    f"for action '{action}'. Permitted: {allowed_actions}"
                ),
            )

        # ---- 3. Constitution prohibited actions ----
        constitution = await self._get_active_constitution()
        if constitution:
            prohibited = constitution.get("prohibited_actions", [])
            for entry in prohibited:
                if isinstance(entry, str) and entry.lower() in action_text.lower():
                    return ConstitutionalDecision(
                        verdict=Verdict.BLOCK,
                        severity=ViolationSeverity.HIGH,
                        citations=self._extract_citations(
                            constitution, f"Prohibited: {entry}"
                        ),
                        explanation=(
                            f"Action violates explicitly prohibited rule: '{entry}'"
                        ),
                    )

        # ---- 4. Passed tier 1 ----
        return ConstitutionalDecision(
            verdict=Verdict.ALLOW,
            severity=ViolationSeverity.LOW,
            tier_results={"tier1": "passed"},
        )

    # ------------------------------------------------------------------
    # TIER 2 – ChromaDB Semantic Check
    # ------------------------------------------------------------------

    async def _tier2_check(
        self,
        agent_id: str,
        action: str,
        context: Dict[str, Any],
    ) -> ConstitutionalDecision:
        """
        Semantic constitutional check via ChromaDB embeddings.

        Queries the constitution collection for articles semantically
        similar to the proposed action. Uses similarity thresholds to
        classify as ALLOW / BLOCK / VOTE_REQUIRED.
        """
        if not self._vector_store:
            return ConstitutionalDecision(
                verdict=Verdict.ALLOW,
                severity=ViolationSeverity.LOW,
                tier_results={"tier2": "skipped_no_vector_store"},
                explanation="Tier 2 skipped – Vector DB unavailable.",
            )

        action_description = self._build_action_description(agent_id, action, context)

        try:
            # Check embedding cache first
            cached = await self._get_cached_embedding_result(action_description)
            if cached is not None:
                return cached

            # Query constitution collection
            results = self._vector_store.query_constitution(
                query=action_description,
                n_results=5,
            )

            if not results or not results.get("documents"):
                return ConstitutionalDecision(
                    verdict=Verdict.ALLOW,
                    severity=ViolationSeverity.LOW,
                    tier_results={"tier2": "no_matching_articles"},
                )

            documents = results["documents"][0] if results["documents"] else []
            distances = results["distances"][0] if results.get("distances") else []
            metadatas = results["metadatas"][0] if results.get("metadatas") else []

            # ChromaDB returns distances (lower = more similar for cosine)
            # Convert to similarity: similarity = 1 - distance
            similarities = [1 - d for d in distances] if distances else []

            max_similarity = max(similarities) if similarities else 0.0
            citations = self._build_citations(documents, metadatas, similarities)

            if max_similarity >= self.BLOCK_THRESHOLD:
                decision = ConstitutionalDecision(
                    verdict=Verdict.BLOCK,
                    severity=ViolationSeverity.HIGH,
                    citations=citations,
                    explanation=(
                        f"Semantic analysis found {max_similarity:.0%} similarity "
                        f"to prohibitive constitutional articles."
                    ),
                    tier_results={"tier2": "blocked", "max_similarity": max_similarity},
                )
            elif max_similarity >= self.GREY_AREA_THRESHOLD:
                decision = ConstitutionalDecision(
                    verdict=Verdict.VOTE_REQUIRED,
                    severity=ViolationSeverity.MEDIUM,
                    citations=citations,
                    requires_vote=True,
                    explanation=(
                        f"Grey area detected ({max_similarity:.0%} similarity). "
                        f"Council deliberation recommended."
                    ),
                    tier_results={"tier2": "grey_area", "max_similarity": max_similarity},
                )
            else:
                decision = ConstitutionalDecision(
                    verdict=Verdict.ALLOW,
                    severity=ViolationSeverity.LOW,
                    citations=citations[:1] if citations else [],
                    explanation="Action is within constitutional bounds.",
                    tier_results={"tier2": "passed", "max_similarity": max_similarity},
                )

            # Cache result
            await self._cache_embedding_result(action_description, decision)
            return decision

        except Exception as exc:
            logger.error("Tier 2 semantic check failed: %s", exc, exc_info=True)
            return ConstitutionalDecision(
                verdict=Verdict.ALLOW,
                severity=ViolationSeverity.LOW,
                tier_results={"tier2": f"error: {exc}"},
                explanation="Tier 2 check failed – defaulting to ALLOW with logging.",
            )

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _merge_tiers(
        self,
        tier1: ConstitutionalDecision,
        tier2: ConstitutionalDecision,
    ) -> ConstitutionalDecision:
        """Merge tier results. Tier 2 can only escalate, never downgrade."""
        # Verdict priority: BLOCK > VOTE_REQUIRED > ALLOW
        verdict_order = {Verdict.ALLOW: 0, Verdict.VOTE_REQUIRED: 1, Verdict.BLOCK: 2}
        severity_order = list(ViolationSeverity)

        final_verdict = max(
            tier1.verdict, tier2.verdict,
            key=lambda v: verdict_order[v],
        )
        final_severity = max(
            tier1.severity, tier2.severity,
            key=lambda s: severity_order.index(s),
        )

        all_citations = list(dict.fromkeys(tier1.citations + tier2.citations))

        explanations = []
        if tier1.explanation:
            explanations.append(f"[Tier 1] {tier1.explanation}")
        if tier2.explanation:
            explanations.append(f"[Tier 2] {tier2.explanation}")

        return ConstitutionalDecision(
            verdict=final_verdict,
            severity=final_severity,
            citations=all_citations,
            explanation=" | ".join(explanations),
            requires_vote=(
                final_verdict == Verdict.VOTE_REQUIRED
                or tier1.requires_vote
                or tier2.requires_vote
            ),
            affected_agents=tier1.affected_agents + tier2.affected_agents,
        )

    async def _get_active_constitution(self) -> Optional[Dict[str, Any]]:
        """Load active constitution with Redis caching."""
        # Try Redis cache
        if self._redis:
            try:
                cached = await self._redis.get("constitutional_guard:active_constitution")
                if cached:
                    return json.loads(cached)
            except Exception:
                pass

        # Try in-memory cache
        if (
            self._constitution_cache
            and self._cache_timestamp
            and (datetime.utcnow() - self._cache_timestamp).seconds < self.CONSTITUTION_CACHE_TTL
        ):
            return self._constitution_cache

        # Load from PostgreSQL
        try:
            from backend.models.entities.constitution import Constitution
            constitution = (
                self.db.query(Constitution)
                .filter_by(is_active=True)
                .order_by(Constitution.version_number.desc())
                .first()
            )
            if not constitution:
                return None

            data = {
                "id": constitution.id,
                "version": constitution.version if hasattr(constitution, 'version') else "1.0",
                "version_number": constitution.version_number if hasattr(constitution, 'version_number') else 1,
                "articles": constitution.get_articles_dict(),
                "prohibited_actions": constitution.get_prohibited_actions_list(),
                "sovereign_preferences": constitution.get_sovereign_preferences(),
            }

            # Cache
            self._constitution_cache = data
            self._cache_timestamp = datetime.utcnow()

            if self._redis:
                try:
                    await self._redis.setex(
                        "constitutional_guard:active_constitution",
                        self.CONSTITUTION_CACHE_TTL,
                        json.dumps(data, default=str),
                    )
                except Exception:
                    pass

            return data
        except Exception as exc:
            logger.error("Failed to load constitution: %s", exc)
            return None

    def _build_action_description(
        self, agent_id: str, action: str, context: Dict[str, Any]
    ) -> str:
        """Build a natural-language description for semantic comparison."""
        tier_names = {"0": "Head of Council", "1": "Council Member", "2": "Lead Agent", "3": "Task Agent"}
        tier = agent_id[0] if agent_id else "3"
        agent_type = tier_names.get(tier, "Unknown Agent")

        parts = [f"{agent_type} ({agent_id}) attempting to '{action}'"]
        if context:
            relevant = {k: v for k, v in context.items() if k not in ("_internal",)}
            if relevant:
                parts.append(f"with parameters: {json.dumps(relevant, default=str)}")
        return " ".join(parts)

    def _extract_citations(
        self,
        constitution: Dict[str, Any],
        match_hint: str,
    ) -> List[str]:
        """Extract human-readable legal citations from constitution."""
        citations = []
        articles = constitution.get("articles", {})

        if isinstance(articles, dict):
            for idx, (article_key, article_content) in enumerate(articles.items(), 1):
                content_str = str(article_content).lower()
                if match_hint.lower() in content_str or any(
                    word in content_str
                    for word in match_hint.lower().split()[:3]
                ):
                    citations.append(f"Article {idx} ({article_key})")
        elif isinstance(articles, list):
            for idx, article in enumerate(articles, 1):
                content_str = str(article).lower()
                if any(word in content_str for word in match_hint.lower().split()[:3]):
                    citations.append(f"Article {idx}")

        if not citations:
            citations.append(f"Constitutional Review – {match_hint[:80]}")

        return citations

    def _build_citations(
        self,
        documents: List[str],
        metadatas: List[Dict],
        similarities: List[float],
    ) -> List[str]:
        """Build human-readable citations from ChromaDB query results."""
        citations = []
        for i, (doc, meta, sim) in enumerate(
            zip(documents, metadatas or [{}] * len(documents), similarities)
        ):
            if sim >= self.GREY_AREA_THRESHOLD:
                article_id = meta.get("article_id", f"Section {i + 1}")
                article_title = meta.get("title", "")
                citation = f"{article_id}"
                if article_title:
                    citation += f" – {article_title}"
                citation += f" (relevance: {sim:.0%})"
                citations.append(citation)
        return citations

    # ------------------------------------------------------------------
    # Caching helpers
    # ------------------------------------------------------------------

    async def _get_cached_embedding_result(
        self, action_description: str
    ) -> Optional[ConstitutionalDecision]:
        """Check Redis for a previously computed semantic result."""
        if not self._redis:
            return None
        try:
            cache_key = self._embedding_cache_key(action_description)
            cached = await self._redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                return ConstitutionalDecision(
                    verdict=Verdict(data["verdict"]),
                    severity=ViolationSeverity(data["severity"]),
                    citations=data.get("citations", []),
                    explanation=data.get("explanation", ""),
                    tier_results=data.get("tier_results", {}),
                    requires_vote=data.get("requires_vote", False),
                )
        except Exception:
            pass
        return None

    async def _cache_embedding_result(
        self, action_description: str, decision: ConstitutionalDecision
    ):
        """Cache a semantic check result in Redis."""
        if not self._redis:
            return
        try:
            cache_key = self._embedding_cache_key(action_description)
            await self._redis.setex(
                cache_key,
                self.EMBEDDING_CACHE_TTL,
                json.dumps(decision.to_dict(), default=str),
            )
        except Exception:
            pass

    @staticmethod
    def _embedding_cache_key(text: str) -> str:
        digest = hashlib.sha256(text.encode()).hexdigest()[:16]
        return f"constitutional_guard:semantic:{digest}"

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    async def _log_decision(
        self,
        agent_id: str,
        action: str,
        decision: ConstitutionalDecision,
    ):
        """Persist the decision in the audit trail."""
        try:
            from backend.models.entities.audit import (
                AuditLog, AuditLevel, AuditCategory, ConstitutionViolation,
            )

            level_map = {
                ViolationSeverity.LOW: AuditLevel.DEBUG,
                ViolationSeverity.MEDIUM: AuditLevel.WARNING,
                ViolationSeverity.HIGH: AuditLevel.CRITICAL,
                ViolationSeverity.CRITICAL: AuditLevel.EMERGENCY,
            }

            audit = AuditLog(
                level=level_map.get(decision.severity, AuditLevel.INFO),
                category=AuditCategory.CONSTITUTION,
                actor_type="agent",
                actor_id=agent_id,
                action=f"constitutional_check:{action}",
                target_type="constitution",
                target_id="",
                description=(
                    f"Verdict={decision.verdict.value} "
                    f"Severity={decision.severity.value} "
                    f"Citations={decision.citations}"
                ),
                agentium_id=f"CG{datetime.utcnow().strftime('%H%M%S')}",
            )
            self.db.add(audit)

            # Also create ConstitutionViolation record for BLOCK / VOTE_REQUIRED
            if decision.verdict != Verdict.ALLOW:
                severity_to_audit_level = {
                    ViolationSeverity.LOW: AuditLevel.WARNING,
                    ViolationSeverity.MEDIUM: AuditLevel.WARNING,
                    ViolationSeverity.HIGH: AuditLevel.CRITICAL,
                    ViolationSeverity.CRITICAL: AuditLevel.EMERGENCY,
                }
                violation = ConstitutionViolation(
                    agentium_id=agent_id,
                    violation_type=action,
                    violated_article=", ".join(decision.citations[:3]),
                    description=decision.explanation or f"Constitutional violation: {action}",
                    severity=severity_to_audit_level.get(decision.severity, AuditLevel.WARNING),
                    attempted_action=f"{action} {json.dumps({})}",
                    detected_by="CONSTITUTIONAL_GUARD",
                    detection_method="pre_execution_check",
                    blocked=(decision.verdict == Verdict.BLOCK),
                    context={"verdict": decision.verdict.value, "citations": decision.citations},
                )
                self.db.add(violation)

            self.db.commit()

            # Phase 13.4 Auto Constitutional Amendment
            if decision.verdict == Verdict.VOTE_REQUIRED:
                try:
                    from datetime import timedelta
                    cutoff = datetime.utcnow() - timedelta(hours=24)
                    # blocked=False identifies VOTE_REQUIRED rows (blocked=True means BLOCK verdict)
                    recent_votes = self.db.query(ConstitutionViolation).filter(
                        ConstitutionViolation.violation_type == action,
                        ConstitutionViolation.blocked == False,
                        ConstitutionViolation.created_at >= cutoff
                    ).count()
                    
                    if recent_votes >= 3:
                        from backend.services.voting_service import voting_service
                        voting_service.propose_amendment(
                            db=self.db,
                            proposed_by="SYSTEM_IMPROVEMENT_ENGINE",
                            title=f"Auto-Amendment for {action}",
                            content=f"This amendment was auto-proposed after {recent_votes} VOTE_REQUIRED occurrences in 24h.",
                            articles_to_modify=[]
                        )
                except Exception as eval_e:
                    logger.error(f"Failed to auto-propose amendment: {eval_e}")

        except Exception as exc:
            logger.error("Failed to log constitutional decision: %s", exc)
            try:
                self.db.rollback()
            except Exception:
                pass