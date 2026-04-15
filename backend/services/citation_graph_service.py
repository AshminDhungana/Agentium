"""
Phase 16.3: Cross-Document Citation Graph Service.

Records citation edges during RAG retrieval and provides BFS graph
traversal, citation frequency computation, and boost calculation.
"""

import logging
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.entities.citation_edge import CitationEdge

logger = logging.getLogger(__name__)


class CitationGraphService:
    """Manages the cross-document citation graph stored in PostgreSQL."""

    # ------------------------------------------------------------------
    # Write — record citation events
    # ------------------------------------------------------------------

    @staticmethod
    def record_citation(
        db: Session,
        source_doc_id: str,
        cited_by_doc_id: str,
        task_id: Optional[str] = None,
        collection_key: str = "",
        relevance_score: float = 0.0,
    ) -> CitationEdge:
        """Record a single citation edge."""
        edge = CitationEdge(
            id=str(uuid.uuid4()),
            source_doc_id=source_doc_id,
            cited_by_doc_id=cited_by_doc_id,
            task_id=task_id,
            collection_key=collection_key,
            relevance_score=relevance_score,
            created_at=datetime.utcnow(),
        )
        db.add(edge)
        return edge

    @staticmethod
    def record_retrieval_citations(
        db: Session,
        query_context_id: str,
        retrieved_doc_ids: List[str],
        task_id: Optional[str] = None,
        collection_key: str = "",
        relevance_scores: Optional[List[float]] = None,
    ) -> int:
        """
        Record citation edges from a RAG retrieval batch.

        Args:
            query_context_id: An identifier for the query context
                (e.g. the agent's agentium_id or a hash of the query).
            retrieved_doc_ids: ChromaDB document IDs returned by the query.
            task_id: Optional task UUID this retrieval is associated with.
            collection_key: Which ChromaDB collection was queried.
            relevance_scores: Relevance (1 - distance) for each retrieved doc.

        Returns:
            The number of edges recorded.
        """
        if not retrieved_doc_ids:
            return 0

        scores = relevance_scores or [0.0] * len(retrieved_doc_ids)
        now = datetime.utcnow()
        count = 0

        for i, doc_id in enumerate(retrieved_doc_ids):
            if doc_id == query_context_id:
                continue  # skip self-citations
            edge = CitationEdge(
                id=str(uuid.uuid4()),
                source_doc_id=doc_id,
                cited_by_doc_id=query_context_id,
                task_id=task_id,
                collection_key=collection_key,
                relevance_score=scores[i] if i < len(scores) else 0.0,
                created_at=now,
            )
            db.add(edge)
            count += 1

        try:
            db.flush()
        except Exception:
            logger.debug(
                "Phase 16.3: flush failed for citation edges; "
                "they will be committed with the enclosing transaction."
            )

        return count

    # ------------------------------------------------------------------
    # Read — graph traversal
    # ------------------------------------------------------------------

    @staticmethod
    def get_citation_graph(
        db: Session,
        root_doc_id: str,
        depth: int = 2,
    ) -> Dict[str, Any]:
        """
        BFS-traverse the citation graph from *root_doc_id* up to
        *depth* hops.  Returns ``{ nodes, edges, stats }``.
        """
        depth = max(1, min(depth, 5))  # clamp

        visited_nodes: Dict[str, Dict[str, Any]] = {}
        visited_edges: List[Dict[str, Any]] = []
        edge_set: set = set()
        queue: deque = deque()
        queue.append((root_doc_id, 0))
        visited_nodes[root_doc_id] = {
            "id": root_doc_id,
            "depth": 0,
        }

        while queue:
            current_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue

            # Find neighbours: edges where current is source OR cited_by
            outgoing = (
                db.query(
                    CitationEdge.source_doc_id,
                    CitationEdge.cited_by_doc_id,
                    CitationEdge.collection_key,
                    func.count(CitationEdge.id).label("cite_count"),
                    func.max(CitationEdge.created_at).label("last_cited"),
                )
                .filter(
                    (CitationEdge.source_doc_id == current_id)
                    | (CitationEdge.cited_by_doc_id == current_id)
                )
                .group_by(
                    CitationEdge.source_doc_id,
                    CitationEdge.cited_by_doc_id,
                    CitationEdge.collection_key,
                )
                .all()
            )

            for row in outgoing:
                src = row.source_doc_id
                tgt = row.cited_by_doc_id
                edge_key = (src, tgt)

                # Record the edge
                if edge_key not in edge_set:
                    edge_set.add(edge_key)
                    visited_edges.append({
                        "source": src,
                        "target": tgt,
                        "collection_key": row.collection_key,
                        "citation_count": row.cite_count,
                        "last_cited_at": (
                            row.last_cited.isoformat()
                            if row.last_cited
                            else None
                        ),
                    })

                # Determine neighbour
                neighbour = tgt if src == current_id else src
                if neighbour not in visited_nodes:
                    visited_nodes[neighbour] = {
                        "id": neighbour,
                        "depth": current_depth + 1,
                    }
                    queue.append((neighbour, current_depth + 1))

        # Enrich nodes with citation counts
        all_node_ids = list(visited_nodes.keys())
        freq = CitationGraphService.get_citation_frequency(db, all_node_ids)
        for node_id, node_data in visited_nodes.items():
            node_data["citation_count"] = freq.get(node_id, 0)

        return {
            "nodes": list(visited_nodes.values()),
            "edges": visited_edges,
            "stats": {
                "node_count": len(visited_nodes),
                "edge_count": len(visited_edges),
                "traversal_depth": depth,
            },
        }

    # ------------------------------------------------------------------
    # Read — citation frequency
    # ------------------------------------------------------------------

    @staticmethod
    def get_citation_frequency(
        db: Session,
        doc_ids: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """
        Return citation counts for documents.

        If *doc_ids* is provided, only count those documents.
        Otherwise, return top 100 most-cited documents.
        """
        q = db.query(
            CitationEdge.source_doc_id,
            func.count(CitationEdge.id).label("cite_count"),
        ).group_by(CitationEdge.source_doc_id)

        if doc_ids:
            q = q.filter(CitationEdge.source_doc_id.in_(doc_ids))
        else:
            q = q.order_by(func.count(CitationEdge.id).desc()).limit(100)

        return {row.source_doc_id: row.cite_count for row in q.all()}

    @staticmethod
    def get_top_cited(
        db: Session,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Return the top N most-cited documents with their stats."""
        rows = (
            db.query(
                CitationEdge.source_doc_id,
                CitationEdge.collection_key,
                func.count(CitationEdge.id).label("cite_count"),
                func.max(CitationEdge.created_at).label("last_cited"),
                func.avg(CitationEdge.relevance_score).label("avg_relevance"),
            )
            .group_by(
                CitationEdge.source_doc_id,
                CitationEdge.collection_key,
            )
            .order_by(func.count(CitationEdge.id).desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "doc_id": row.source_doc_id,
                "collection_key": row.collection_key,
                "citation_count": row.cite_count,
                "last_cited_at": (
                    row.last_cited.isoformat() if row.last_cited else None
                ),
                "avg_relevance": (
                    round(row.avg_relevance, 4)
                    if row.avg_relevance is not None
                    else 0.0
                ),
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Boost computation
    # ------------------------------------------------------------------

    @staticmethod
    def compute_citation_boost(
        db: Session,
        doc_ids: List[str],
        max_boost: float = 1.3,
        boost_per_citation: float = 0.05,
    ) -> Dict[str, float]:
        """
        Compute citation_boost multiplier for each doc.

        Formula: min(max_boost, 1.0 + boost_per_citation * citation_count)
        """
        freq = CitationGraphService.get_citation_frequency(db, doc_ids)
        return {
            doc_id: min(max_boost, 1.0 + boost_per_citation * count)
            for doc_id, count in freq.items()
        }

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    @staticmethod
    def cleanup_old_edges(
        db: Session,
        retention_days: int = 90,
    ) -> int:
        """Delete citation edges older than *retention_days*."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        count = (
            db.query(CitationEdge)
            .filter(CitationEdge.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        logger.info(
            "Phase 16.3: cleaned up %d citation edges older than %d days",
            count,
            retention_days,
        )
        return count


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------
_citation_graph_service: Optional[CitationGraphService] = None


def get_citation_graph_service() -> CitationGraphService:
    """Return the singleton CitationGraphService."""
    global _citation_graph_service
    if _citation_graph_service is None:
        _citation_graph_service = CitationGraphService()
    return _citation_graph_service
