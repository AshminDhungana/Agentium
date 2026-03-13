"""
Fact Checker Service for Agentium — Phase 10.2.

Provides confidence scoring, contradiction detection, and citation
formatting for RAG outputs. Uses the existing VectorStore for
embedding-based similarity comparisons.

Flow:
    LLM Output → split into claims → check each against Vector DB →
    score confidence → detect contradictions → format citations
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.core.vector_store import VectorStore, get_vector_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SourceReference:
    """A cited source backing a claim."""
    url: str = ""
    title: str = ""
    author: str = ""
    collection: str = ""
    doc_id: str = ""
    relevance: float = 0.0


@dataclass
class ContradictionReport:
    """A detected contradiction between a claim and stored knowledge."""
    claim: str
    contradicting_text: str
    source: SourceReference
    similarity: float = 0.0
    explanation: str = ""


@dataclass
class FactCheckResult:
    """Result of checking a single claim against the knowledge base."""
    claim: str
    confidence: float  # 0.0 – 1.0
    sources: List[SourceReference] = field(default_factory=list)
    contradictions: List[ContradictionReport] = field(default_factory=list)
    checked_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def is_supported(self) -> bool:
        return self.confidence >= 0.7

    @property
    def has_contradictions(self) -> bool:
        return len(self.contradictions) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim": self.claim,
            "confidence": round(self.confidence, 3),
            "is_supported": self.is_supported,
            "has_contradictions": self.has_contradictions,
            "sources": [
                {
                    "url": s.url,
                    "title": s.title,
                    "author": s.author,
                    "collection": s.collection,
                    "relevance": round(s.relevance, 3),
                }
                for s in self.sources
            ],
            "contradictions": [
                {
                    "contradicting_text": c.contradicting_text[:200],
                    "similarity": round(c.similarity, 3),
                    "source_url": c.source.url,
                }
                for c in self.contradictions
            ],
            "checked_at": self.checked_at,
        }


# ---------------------------------------------------------------------------
# FactChecker
# ---------------------------------------------------------------------------

class FactChecker:
    """
    Validates LLM outputs against the Agentium knowledge base.

    Usage::

        checker = FactChecker()
        result = checker.check_claim("Python was created by Guido van Rossum")
        print(result.confidence, result.sources)
    """

    # Distance thresholds for ChromaDB (L2 distance — lower is more similar)
    STRONG_SUPPORT_THRESHOLD = 0.3   # Very similar → high confidence
    MODERATE_SUPPORT_THRESHOLD = 0.6 # Somewhat similar → moderate confidence
    CONTRADICTION_THRESHOLD = 0.5    # Close but semantically opposed

    def __init__(self, vector_store: Optional[VectorStore] = None):
        self._vs: VectorStore = vector_store or get_vector_store()

    # ── Core API ──────────────────────────────────────────────────────────

    def check_claim(
        self,
        claim: str,
        context_docs: Optional[List[str]] = None,
        collections: Optional[List[str]] = None,
    ) -> FactCheckResult:
        """
        Check a claim against the knowledge base.

        Args:
            claim: The statement to verify.
            context_docs: Optional list of directly provided context docs
                          to compare against (bypass vector search).
            collections: ChromaDB collection keys to search. Defaults to
                         a broad set of knowledge collections.

        Returns:
            FactCheckResult with confidence, sources, and contradictions.
        """
        if not claim or not claim.strip():
            return FactCheckResult(claim=claim, confidence=0.0)

        sources: List[SourceReference] = []
        contradictions: List[ContradictionReport] = []

        # 1. Score against directly provided context
        if context_docs:
            for doc in context_docs:
                sim = self.score_confidence(claim, doc)
                if sim >= 0.7:
                    sources.append(SourceReference(
                        title="Inline context",
                        relevance=sim,
                        collection="context",
                    ))

        # 2. Search knowledge base collections
        target_collections = collections or [
            "constitution",
            "task_patterns",
            "council_memory",
        ]

        for coll_key in target_collections:
            try:
                coll = self._vs.get_collection(coll_key)
                results = coll.query(query_texts=[claim], n_results=3)

                if not results.get("documents") or not results["documents"][0]:
                    continue

                for i, doc in enumerate(results["documents"][0]):
                    distance = (
                        results["distances"][0][i]
                        if results.get("distances") and results["distances"][0]
                        else 1.0
                    )
                    meta = (
                        results["metadatas"][0][i]
                        if results.get("metadatas") and results["metadatas"][0]
                        else {}
                    )
                    similarity = max(0.0, 1.0 - distance)

                    source_ref = SourceReference(
                        url=meta.get("source_url", ""),
                        title=meta.get("title", ""),
                        author=meta.get("author", ""),
                        collection=coll_key,
                        doc_id=(
                            results["ids"][0][i]
                            if results.get("ids") and results["ids"][0]
                            else ""
                        ),
                        relevance=similarity,
                    )

                    if distance < self.STRONG_SUPPORT_THRESHOLD:
                        sources.append(source_ref)
                    elif distance < self.MODERATE_SUPPORT_THRESHOLD:
                        sources.append(source_ref)

            except (ValueError, Exception) as exc:
                logger.debug(
                    "Could not query collection '%s' for fact-check: %s",
                    coll_key, exc,
                )
                continue

        # 3. Detect contradictions
        contradictions = self.detect_contradictions(claim, target_collections)

        # 4. Calculate overall confidence
        confidence = self._calculate_confidence(claim, sources, contradictions)

        return FactCheckResult(
            claim=claim,
            confidence=confidence,
            sources=sources,
            contradictions=contradictions,
        )

    def score_confidence(self, claim: str, evidence_text: str) -> float:
        """
        Score how well a claim is supported by a specific piece of evidence.

        Uses cosine similarity via the VectorStore's embedding model.
        Returns a float between 0.0 (no support) and 1.0 (perfect match).
        """
        if not claim or not evidence_text:
            return 0.0

        try:
            ef = self._vs._embedding_function
            claim_emb = ef([claim])
            evidence_emb = ef([evidence_text])

            # Cosine similarity
            import numpy as np
            a = np.array(claim_emb[0])
            b = np.array(evidence_emb[0])
            denom = np.linalg.norm(a) * np.linalg.norm(b)
            if denom == 0:
                return 0.0
            return float(np.dot(a, b) / denom)
        except Exception as exc:
            logger.debug("Embedding-based scoring failed: %s", exc)
            # Fallback: simple word overlap (Jaccard)
            claim_words = set(claim.lower().split())
            evidence_words = set(evidence_text.lower().split())
            if not claim_words or not evidence_words:
                return 0.0
            intersection = claim_words & evidence_words
            union = claim_words | evidence_words
            return len(intersection) / len(union)

    def detect_contradictions(
        self,
        claim: str,
        collections: Optional[List[str]] = None,
    ) -> List[ContradictionReport]:
        """
        Search for documents that are semantically close to the claim
        but potentially contradicting it.

        Heuristic: If a document is close (distance < threshold) AND
        contains negation keywords relative to the claim, flag it.
        """
        contradictions: List[ContradictionReport] = []
        target_collections = collections or ["task_patterns", "council_memory"]

        negation_patterns = [
            r"\bnot\b", r"\bnever\b", r"\bno\b", r"\bwithout\b",
            r"\bfails?\b", r"\bincorrect\b", r"\bwrong\b", r"\binvalid\b",
            r"\bprohibit\b", r"\bforbid\b", r"\bban\b",
        ]

        for coll_key in target_collections:
            try:
                coll = self._vs.get_collection(coll_key)
                results = coll.query(query_texts=[claim], n_results=5)

                if not results.get("documents") or not results["documents"][0]:
                    continue

                for i, doc in enumerate(results["documents"][0]):
                    distance = (
                        results["distances"][0][i]
                        if results.get("distances") and results["distances"][0]
                        else 1.0
                    )
                    if distance > self.CONTRADICTION_THRESHOLD:
                        continue

                    # Check if document has negation relative to claim
                    has_negation = any(
                        re.search(pat, doc.lower()) for pat in negation_patterns
                    )
                    claim_has_negation = any(
                        re.search(pat, claim.lower()) for pat in negation_patterns
                    )

                    # Contradiction = one has negation, the other doesn't
                    if has_negation != claim_has_negation:
                        meta = (
                            results["metadatas"][0][i]
                            if results.get("metadatas") and results["metadatas"][0]
                            else {}
                        )
                        contradictions.append(ContradictionReport(
                            claim=claim,
                            contradicting_text=doc,
                            source=SourceReference(
                                url=meta.get("source_url", ""),
                                title=meta.get("title", ""),
                                collection=coll_key,
                            ),
                            similarity=max(0.0, 1.0 - distance),
                        ))

            except (ValueError, Exception) as exc:
                logger.debug(
                    "Contradiction check on '%s' failed: %s", coll_key, exc,
                )

        return contradictions

    # ── Citation Formatting ───────────────────────────────────────────────

    @staticmethod
    def format_citations(sources: List[SourceReference]) -> List[str]:
        """
        Produce inline citation strings in the format [Source: URL].

        If no URL is available, falls back to [Source: collection/doc_id].
        """
        citations: List[str] = []
        for src in sources:
            if src.url:
                citations.append(f"[Source: {src.url}]")
            elif src.title:
                citations.append(f"[Source: {src.title}]")
            elif src.doc_id:
                citations.append(f"[Source: {src.collection}/{src.doc_id}]")
            else:
                citations.append(f"[Source: {src.collection}]")
        return citations

    @staticmethod
    def annotate_text(text: str, sources: List[SourceReference]) -> str:
        """
        Append citation annotations to a block of text.

        Produces: ``<original text> [Source: URL1] [Source: URL2]``
        """
        citations = FactChecker.format_citations(sources)
        if not citations:
            return text
        return f"{text.rstrip()} {' '.join(citations)}"

    # ── Private Helpers ───────────────────────────────────────────────────

    def _calculate_confidence(
        self,
        claim: str,
        sources: List[SourceReference],
        contradictions: List[ContradictionReport],
    ) -> float:
        """Aggregate confidence from source relevance and contradictions."""
        if not sources and not contradictions:
            return 0.0

        # Base confidence from best source
        if sources:
            best_relevance = max(s.relevance for s in sources)
            base = best_relevance
        else:
            base = 0.0

        # Penalise for contradictions
        if contradictions:
            penalty = min(0.4, 0.15 * len(contradictions))
            base = max(0.0, base - penalty)

        return min(1.0, base)

    # ── Cross-Document Citation Graph (Phase 10.2) ────────────────────────

    def build_citation_graph(
        self,
        collections: Optional[List[str]] = None,
    ) -> "CitationGraph":
        """
        Build a citation graph across knowledge collections.

        Scans documents in the specified collections and creates edges
        between documents that are semantically related (distance below
        threshold). Edge types are 'supports' or 'contradicts' based on
        negation heuristics.
        """
        graph = CitationGraph()
        target = collections or ["constitution", "task_patterns", "council_memory"]

        # Collect all documents across collections
        all_docs: List[Dict[str, Any]] = []
        for coll_key in target:
            try:
                coll = self._vs.get_collection(coll_key)
                results = coll.get(include=["documents", "metadatas"])
                if not results or not results.get("ids"):
                    continue
                for i, doc_id in enumerate(results["ids"]):
                    doc_text = (results.get("documents") or [])[i] if results.get("documents") else ""
                    meta = (results.get("metadatas") or [])[i] if results.get("metadatas") else {}
                    graph.add_node(doc_id, {
                        "collection": coll_key,
                        "title": (meta or {}).get("title", ""),
                        "type": (meta or {}).get("type", ""),
                        "text_preview": (doc_text or "")[:100],
                    })
                    all_docs.append({"id": doc_id, "text": doc_text or "", "collection": coll_key})
            except Exception as exc:
                logger.debug("Citation graph: skipping collection '%s': %s", coll_key, exc)

        # Build edges via cross-document similarity
        EDGE_THRESHOLD = 0.6
        for doc_info in all_docs:
            for coll_key in target:
                try:
                    coll = self._vs.get_collection(coll_key)
                    results = coll.query(query_texts=[doc_info["text"][:500]], n_results=3)
                    if not results.get("ids") or not results["ids"][0]:
                        continue
                    for j, related_id in enumerate(results["ids"][0]):
                        if related_id == doc_info["id"]:
                            continue
                        distance = (
                            results["distances"][0][j]
                            if results.get("distances") and results["distances"][0]
                            else 1.0
                        )
                        if distance < EDGE_THRESHOLD:
                            related_text = (
                                results["documents"][0][j]
                                if results.get("documents") and results["documents"][0]
                                else ""
                            )
                            edge_type = self._classify_relationship(doc_info["text"], related_text)
                            graph.add_edge(doc_info["id"], related_id, edge_type, similarity=max(0.0, 1.0 - distance))
                except Exception:
                    continue

        return graph

    def get_citation_graph(self, collections: Optional[List[str]] = None) -> Dict[str, Any]:
        """Return serialisable citation graph data for API responses."""
        return self.build_citation_graph(collections).to_dict()

    @staticmethod
    def _classify_relationship(text_a: str, text_b: str) -> str:
        """Classify relationship as 'supports' or 'contradicts' via negation heuristic."""
        negation_words = {"not", "never", "no", "without", "incorrect", "wrong", "invalid"}
        neg_a = bool(set(text_a.lower().split()) & negation_words)
        neg_b = bool(set(text_b.lower().split()) & negation_words)
        return "contradicts" if neg_a != neg_b else "supports"


# ---------------------------------------------------------------------------
# Cross-Document Citation Graph (Phase 10.2)
# ---------------------------------------------------------------------------

@dataclass
class CitationGraphNode:
    """A node in the citation graph representing a document."""
    doc_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CitationGraphEdge:
    """A directed edge in the citation graph."""
    source_id: str
    target_id: str
    relationship: str  # "supports" or "contradicts"
    similarity: float = 0.0


class CitationGraph:
    """
    In-memory directed graph of cross-document citation relationships.

    Nodes are documents from ChromaDB; edges represent semantic
    relationships (supports/contradicts) discovered via embedding similarity.
    """

    def __init__(self):
        self._nodes: Dict[str, CitationGraphNode] = {}
        self._edges: List[CitationGraphEdge] = []

    def add_node(self, doc_id: str, metadata: Optional[Dict[str, Any]] = None):
        self._nodes[doc_id] = CitationGraphNode(doc_id=doc_id, metadata=metadata or {})

    def add_edge(self, source_id: str, target_id: str, relationship: str = "supports", similarity: float = 0.0):
        for edge in self._edges:
            if edge.source_id == source_id and edge.target_id == target_id:
                return
        self._edges.append(CitationGraphEdge(source_id=source_id, target_id=target_id, relationship=relationship, similarity=similarity))

    def get_related(self, doc_id: str) -> List[Dict[str, Any]]:
        related = []
        for edge in self._edges:
            if edge.source_id == doc_id:
                related.append({"target_id": edge.target_id, "relationship": edge.relationship, "similarity": round(edge.similarity, 3)})
            elif edge.target_id == doc_id:
                related.append({"target_id": edge.source_id, "relationship": f"is_{edge.relationship}_by", "similarity": round(edge.similarity, 3)})
        return related

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [{"id": n.doc_id, "metadata": n.metadata} for n in self._nodes.values()],
            "edges": [{"source": e.source_id, "target": e.target_id, "relationship": e.relationship, "similarity": round(e.similarity, 3)} for e in self._edges],
            "stats": {"node_count": self.node_count, "edge_count": self.edge_count},
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_fact_checker: Optional[FactChecker] = None


def get_fact_checker() -> FactChecker:
    """Return the singleton FactChecker."""
    global _fact_checker
    if _fact_checker is None:
        _fact_checker = FactChecker()
    return _fact_checker
