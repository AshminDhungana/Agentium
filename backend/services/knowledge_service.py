"""
Knowledge Service for Agentium.
RAG pipeline and semantic memory management.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.core.vector_store import VectorStore, get_vector_store
from backend.models.entities.agents import Agent, AgentType
from backend.models.entities.constitution import Constitution, Ethos
from backend.models.entities.task import Task

logger = logging.getLogger(__name__)

# Similarity distance below which an entry is considered a duplicate
_DEFAULT_SIMILARITY_THRESHOLD: float = 0.15


class KnowledgeService:
    """
    Manages RAG (Retrieval Augmented Generation) for all agents.

    Bridges PostgreSQL structured data and ChromaDB semantic data.
    """

    def __init__(self, vector_store: Optional[VectorStore] = None) -> None:
        self.vector_store: VectorStore = vector_store or get_vector_store()

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    def embed_constitution(
        self, db: Session, constitution: Constitution
    ) -> None:
        """
        Vectorise constitution articles for semantic retrieval.

        Called when a new constitution is created or amended.
        """
        articles = constitution.get_articles_dict()

        for article_num, article_data in articles.items():
            content = (
                f"{article_data.get('title', '')}: "
                f"{article_data.get('content', '')}"
            )

            self.vector_store.add_constitution_article(
                article_id=f"{constitution.version}_{article_num}",
                content=content,
                metadata={
                    "version": constitution.version,
                    "version_number": constitution.version_number,
                    "article_number": article_num,
                    "effective_date": (
                        constitution.effective_date.isoformat()
                        if constitution.effective_date
                        else None
                    ),
                    "replaces_version": (
                        constitution.replaces_version.version
                        if constitution.replaces_version
                        else None
                    ),
                },
            )

    def embed_ethos(self, ethos: Ethos) -> None:
        """Vectorise agent ethos for behavioural retrieval."""
        content_parts = [
            f"Mission: {ethos.mission_statement}",
            "Core Values: " + ", ".join(ethos.get_core_values()),
            "Behavioral Rules: " + ", ".join(ethos.get_behavioral_rules()),
            "Restrictions: " + ", ".join(ethos.get_restrictions()),
            "Capabilities: " + ", ".join(ethos.get_capabilities()),
        ]
        # FIX: was "\\n\\n" (literal backslash-n) — corrected to newlines
        full_content = "\n\n".join(content_parts)

        self.vector_store.add_ethos(
            agentium_id=ethos.agentium_id or f"E{ethos.agent_id}",
            ethos_content=full_content,
            agent_type=ethos.agent_type,
            verified_by=ethos.verified_by_agentium_id,
        )

    # ------------------------------------------------------------------
    # Context retrieval
    # ------------------------------------------------------------------

    def get_agent_context(
        self,
        db: Session,
        agent: Agent,
        task_description: Optional[str] = None,
        include_constitution: bool = True,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build RAG context for an agent based on its tier.

        Returns a structured dict ready for LLM prompt injection.
        """
        context: Dict[str, Any] = {
            "agent_tier": agent.agent_type.value,
            "agent_id": agent.agentium_id,
            "retrieval_timestamp": datetime.utcnow().isoformat(),
            "knowledge_segments": [],
        }

        query_text: str = task_description or agent.agent_type.value

        # 1. Constitution grounding (all tiers)
        if include_constitution:
            const_results = self.vector_store.query_constitution(
                query_text, n_results=3
            )
            if const_results["documents"] and const_results["documents"][0]:
                for i, doc in enumerate(const_results["documents"][0]):
                    distance = (
                        const_results["distances"][0][i]
                        if const_results.get("distances")
                        else 0.5
                    )
                    context["knowledge_segments"].append(
                        {
                            "type": "constitution",
                            "content": doc,
                            "relevance": max(0.0, 1.0 - distance),
                            "source": (
                                const_results["metadatas"][0][i]
                                if const_results.get("metadatas")
                                else {}
                            ),
                        }
                    )

        # 2. Agent's own Ethos (from DB object — avoids redundant vector query)
        if agent.ethos:
            context["knowledge_segments"].append(
                {
                    "type": "ethos",
                    "content": {
                        "mission": agent.ethos.mission_statement,
                        "rules": agent.ethos.get_behavioral_rules(),
                        "restrictions": agent.ethos.get_restrictions(),
                    },
                    "relevance": 1.0,
                    "source": {
                        "agentium_id": agent.ethos.agentium_id,
                        "version": agent.ethos.version,
                    },
                }
            )

        # 3. Tier-specific knowledge
        if agent.agent_type == AgentType.COUNCIL_MEMBER:
            council_ctx = self.vector_store.query_knowledge(
                query=task_description or "recent deliberations precedent",
                collection_keys=["council_memory"],
                n_results=3,
            )
            if council_ctx["documents"] and council_ctx["documents"][0]:
                for i, doc in enumerate(council_ctx["documents"][0][:2]):
                    context["knowledge_segments"].append(
                        {
                            "type": "precedent",
                            "content": doc,
                            "relevance": 0.9,
                            "source": (
                                council_ctx["metadatas"][0][i]
                                if council_ctx.get("metadatas")
                                else {}
                            ),
                        }
                    )

        elif agent.agent_type == AgentType.LEAD_AGENT:
            # FIX: use canonical key "task_patterns"
            patterns = self.vector_store.get_collection("task_patterns").query(
                query_texts=[task_description or "team coordination"],
                n_results=3,
            )
            if patterns["documents"] and patterns["documents"][0]:
                for i, doc in enumerate(patterns["documents"][0][:2]):
                    context["knowledge_segments"].append(
                        {
                            "type": "coordination_pattern",
                            "content": doc,
                            "relevance": 0.85,
                            "metadata": (
                                patterns["metadatas"][0][i]
                                if patterns.get("metadatas")
                                else {}
                            ),
                        }
                    )

        elif agent.agent_type == AgentType.TASK_AGENT:
            # FIX: use canonical key "task_patterns"
            patterns = self.vector_store.get_collection("task_patterns").query(
                query_texts=[task_description or "execution best practices"],
                n_results=4,
                where={"type": "execution_pattern"},
            )
            if patterns["documents"] and patterns["documents"][0]:
                for i, doc in enumerate(patterns["documents"][0][:3]):
                    context["knowledge_segments"].append(
                        {
                            "type": "execution_pattern",
                            "content": doc,
                            "relevance": 0.8,
                            "metadata": (
                                patterns["metadatas"][0][i]
                                if patterns.get("metadatas")
                                else {}
                            ),
                        }
                    )

        # 4. Critic Case Law (historical failures to avoid)
        try:
            case_law = self.vector_store.get_collection("critic_case_law").query(
                query_texts=[query_text],
                n_results=2,
            )
            if case_law.get("documents") and case_law["documents"][0]:
                for i, doc in enumerate(case_law["documents"][0]):
                    distance = case_law["distances"][0][i] if case_law.get("distances") else 0.5
                    # Only include highly relevant case law to avoid polluting context
                    if distance < 0.4:  
                        context["knowledge_segments"].append(
                            {
                                "type": "case_law_warning",
                                "content": doc,
                                "relevance": max(0.0, 1.0 - distance),
                                "metadata": (
                                    case_law["metadatas"][0][i]
                                    if case_law.get("metadatas")
                                    else {}
                                ),
                            }
                        )
        except ValueError:
            # Collection may not exist yet on fresh deploy
            pass

        # 5. Sovereign preferences (all tiers)
        try:
            prefs = self.vector_store.get_collection("sovereign_prefs").query(
                query_texts=[query_text],
                n_results=2,
            )
            if prefs.get("documents") and prefs["documents"][0]:
                context["knowledge_segments"].append(
                    {
                        "type": "sovereign_preference",
                        "content": prefs["documents"][0][0],
                        "relevance": 0.95,
                        "source": (
                            prefs["metadatas"][0][0]
                            if prefs.get("metadatas")
                            else {}
                        ),
                    }
                )
        except ValueError:
            pass

        # ── Phase 16.3: Record citation edges for all retrieved segments ──
        # Use record_retrieval_citations() for a single batch flush rather than
        # calling record_citation() N times.  Group by collection_key so the
        # collection field is accurate for every edge.
        try:
            from backend.services.citation_graph_service import get_citation_graph_service
            cg = get_citation_graph_service()

            # Build per-collection buckets: {collection_key: [(doc_id, score), ...]}
            from collections import defaultdict
            buckets: dict = defaultdict(list)
            for seg in context.get("knowledge_segments", []):
                src = seg.get("source") or seg.get("metadata") or {}
                doc_id = (
                    src.get("article_id")
                    or src.get("doc_id")
                    or src.get("agentium_id")
                    or src.get("id")
                    or ""
                )
                if doc_id:
                    coll = seg.get("type", "")
                    buckets[coll].append((str(doc_id), float(seg.get("relevance", 0.0))))

            for coll_key, pairs in buckets.items():
                doc_ids = [p[0] for p in pairs]
                scores  = [p[1] for p in pairs]
                cg.record_retrieval_citations(
                    db=db,
                    query_context_id=agent.agentium_id,
                    retrieved_doc_ids=doc_ids,
                    task_id=task_id,
                    collection_key=coll_key,
                    relevance_scores=scores,
                )
        except Exception as cite_exc:
            logger.debug(
                "Phase 16.3: citation recording skipped: %s", cite_exc
            )

        return context

    # ------------------------------------------------------------------
    # Knowledge storage
    # ------------------------------------------------------------------

    def store_or_revise_knowledge(
        self,
        content: str,
        collection_name: str,
        doc_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        similarity_threshold: float = _DEFAULT_SIMILARITY_THRESHOLD,
    ) -> Dict[str, Any]:
        """
        Store knowledge with duplicate detection (§4 — Revision Over Duplication).

        1. Search the target collection for semantically similar entries.
        2. If a similar entry exists (distance < threshold): revise it in place.
        3. If no match: create a new entry.
        """
        try:
            collection = self.vector_store.get_collection(collection_name)
        except ValueError:
            logger.warning(
                "Unknown collection key '%s'; falling back to execution pattern.",
                collection_name,
            )
            self.vector_store.add_execution_pattern(
                pattern_id=doc_id,
                description=content,
                success_rate=1.0,
                task_type="general",
                tools_used=[],
            )
            return {"action": "created_fallback", "doc_id": doc_id}

        # Step 1: search for semantically similar entries
        # FIX: exception is now logged instead of silently swallowed
        try:
            existing = collection.query(query_texts=[content], n_results=1)

            if (
                existing.get("ids")
                and existing["ids"][0]
                and existing.get("distances")
                and existing["distances"][0]
                and existing["distances"][0][0] < similarity_threshold
            ):
                existing_id: str = existing["ids"][0][0]
                existing_meta: Dict[str, Any] = (
                    existing["metadatas"][0][0]
                    if existing.get("metadatas") and existing["metadatas"][0]
                    else {}
                )

                revision_count = int(existing_meta.get("revision_count", 0)) + 1
                merged_metadata: Dict[str, Any] = {
                    **(metadata or {}),
                    "revised_from": existing_id,
                    "revised_at": datetime.utcnow().isoformat(),
                    "revision_count": revision_count,
                    "previous_distance": existing["distances"][0][0],
                    # Phase 16.2: carry forward decay_score but reset
                    # last_validated_at on revision (content refreshed)
                    "decay_score": float(
                        existing_meta.get("decay_score", 1.0)
                    ),
                    "last_validated_at": datetime.utcnow().isoformat(),
                }

                collection.delete(ids=[existing_id])
                collection.add(
                    documents=[content],
                    metadatas=[merged_metadata],
                    ids=[existing_id],
                )
                return {
                    "action": "revised",
                    "doc_id": existing_id,
                    "revision": revision_count,
                }

        except Exception:
            # FIX: log instead of silently ignoring — fall through to create
            logger.exception(
                "Similarity search failed for collection '%s'; "
                "creating new entry.",
                collection_name,
            )

        # Step 3: no similar entry — create new
        final_metadata: Dict[str, Any] = {
            **(metadata or {}),
            "created_at": datetime.utcnow().isoformat(),
            "revision_count": 0,
            # Phase 16.2: initialise decay fields for new knowledge
            "decay_score": (metadata or {}).get("decay_score", 1.0),
            "last_validated_at": datetime.utcnow().isoformat(),
        }
        collection.add(
            documents=[content],
            metadatas=[final_metadata],
            ids=[doc_id],
        )
        return {"action": "created", "doc_id": doc_id}

    def record_execution_pattern(
        self,
        task: Task,
        agent: Agent,
        result_summary: str,
        success: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Record a successful execution pattern for future RAG.

        Uses ``store_or_revise_knowledge`` to avoid duplicates (§4).
        Only successful executions are stored.
        """
        if not success:
            return None

        pattern_desc = (
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"Result: {result_summary}\n"
            f"Executed by: {agent.agentium_id} ({agent.agent_type.value})"
        )
        doc_id = (
            f"{agent.agentium_id}_{task.id}_"
            f"{datetime.utcnow().strftime('%Y%m%d')}"
        )

        # FIX: use canonical collection key "task_patterns"
        return self.store_or_revise_knowledge(
            content=pattern_desc,
            collection_name="task_patterns",
            doc_id=doc_id,
            metadata={
                "type": "execution_pattern",
                "agent_id": agent.agentium_id,
                "task_type": (
                    task.title.split()[0] if task.title else "general"
                ),
                "success_rate": 1.0,
                # Phase 16.2: initialise decay fields
                "decay_score": 1.0,
                "last_validated_at": datetime.utcnow().isoformat(),
            },
        )

    # ------------------------------------------------------------------
    # Phase 10.2: Citation Integration
    # ------------------------------------------------------------------

    def attach_citations(
        self,
        agent_context: Dict[str, Any],
        text: str,
    ) -> str:
        """
        Run fact-checking on *text* against the knowledge segments in
        *agent_context* and append inline ``[Source: URL]`` annotations.

        This is the bridge between KnowledgeService and FactChecker.
        """
        try:
            from backend.services.fact_checker import get_fact_checker
            checker = get_fact_checker()
        except Exception:
            logger.debug("FactChecker unavailable; returning text without citations")
            return text

        # Gather context docs from the knowledge segments already retrieved
        context_docs = []
        for seg in agent_context.get("knowledge_segments", []):
            content = seg.get("content", "")
            if isinstance(content, dict):
                content = str(content)
            if content:
                context_docs.append(content)

        if not context_docs:
            return text

        result = checker.check_claim(text, context_docs=context_docs)
        return checker.annotate_text(text, result.sources)

    @staticmethod
    def validate_citation_metadata(metadata: Optional[Dict[str, Any]]) -> List[str]:
        """
        Validate that ingested knowledge includes citation fields.

        Returns a list of missing fields (empty list = all present).
        """
        if not metadata:
            return ["source_url", "author", "context"]
        required = ["source_url", "author", "context"]
        return [f for f in required if not metadata.get(f)]

    # ------------------------------------------------------------------
    # Phase 16.2: Validation Boost for Retrieved Learnings
    # ------------------------------------------------------------------

    def boost_retrieved_learnings(
        self,
        doc_ids: List[str],
        collection_key: str = "task_patterns",
    ) -> Dict[str, Any]:
        """
        After a task completes successfully, boost decay_score and
        reset last_validated_at for every knowledge document that was
        retrieved during RAG context building.

        This keeps actively-useful knowledge fresh and prevents it
        from being pruned by the weekly decay task.
        """
        if not doc_ids:
            return {"boosted": 0, "doc_ids": []}

        boosted = 0
        boosted_ids: List[str] = []

        for doc_id in doc_ids:
            try:
                result = self.vector_store.boost_validated_learning(
                    doc_id=doc_id,
                    collection_key=collection_key,
                )
                if result.get("boosted"):
                    boosted += 1
                    boosted_ids.append(doc_id)
            except Exception:
                logger.debug(
                    "boost_retrieved_learnings: skip %s", doc_id
                )

        if boosted > 0:
            logger.info(
                "Phase 16.2: validation-boosted %d knowledge entries",
                boosted,
            )

        return {"boosted": boosted, "doc_ids": boosted_ids}


    # ------------------------------------------------------------------
    # Compliance
    # ------------------------------------------------------------------

    def retroactive_constitution_check(
        self, action_description: str
    ) -> Dict[str, Any]:
        """
        Post-hoc check: did an action comply with the Constitution?

        Note: keyword matching is intentionally simple; replace with an
        LLM-based evaluator for production-grade compliance scoring.
        """
        results = self.vector_store.query_constitution(
            action_description, n_results=2
        )

        prohibited_keywords: List[str] = [
            "violate",
            "ignore",
            "bypass",
            "unauthorized",
        ]
        compliance_notes: List[Dict[str, Any]] = []

        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                triggered = [
                    kw
                    for kw in prohibited_keywords
                    if kw in action_description.lower()
                ]
                compliance_notes.append(
                    {
                        "relevant_article": doc,
                        "compliance_status": (
                            "QUESTIONABLE" if triggered else "LIKELY_COMPLIANT"
                        ),
                        "keywords_triggered": triggered,
                        "distance": (
                            results["distances"][0][i]
                            if results.get("distances")
                            else None
                        ),
                    }
                )

        overall = "unknown"
        if compliance_notes:
            all_compliant = all(
                n["compliance_status"] == "LIKELY_COMPLIANT"
                for n in compliance_notes
            )
            overall = "compliant" if all_compliant else "violation_suspected"

        return {
            "action": action_description,
            "checked_at": datetime.utcnow().isoformat(),
            "constitution_articles_checked": compliance_notes,
            "overall_compliance_estimate": overall,
        }

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def initialize_knowledge_base(self, db: Session) -> Dict[str, Any]:
        """
        Bootstrap vector DB with current Constitution and Ethos.

        Should be called once on system startup after the DB is ready.
        """
        active_const: Optional[Constitution] = (
            db.query(Constitution)
            .filter_by(is_active=True)
            .order_by(Constitution.version_number.desc())
            .first()
        )

        if active_const:
            self.embed_constitution(db, active_const)
            logger.info("Embedded Constitution %s", active_const.version)

        ethos_batch: List[Ethos] = (
            db.query(Ethos).filter_by(is_verified=True).all()
        )
        failed = 0
        for ethos in ethos_batch:
            try:
                self.embed_ethos(ethos)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to embed ethos id=%s", ethos.id)
                failed += 1

        logger.info(
            "Embedded %d/%d agent ethos records (%d failed)",
            len(ethos_batch) - failed,
            len(ethos_batch),
            failed,
        )

        return {
            "constitution_embedded": (
                active_const.version if active_const else None
            ),
            "ethos_total": len(ethos_batch),
            "ethos_embedded": len(ethos_batch) - failed,
            "ethos_failed": failed,
        }


# ---------------------------------------------------------------------------
# Singleton factory — never instantiate KnowledgeService directly
# ---------------------------------------------------------------------------
_knowledge_service: Optional[KnowledgeService] = None


def get_knowledge_service() -> KnowledgeService:
    """Return the singleton KnowledgeService."""
    global _knowledge_service  # noqa: PLW0603
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service