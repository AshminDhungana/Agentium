"""
Phase 16.3: Cross-Document Citation Graph API routes.

Exposes the citation graph for BFS traversal and statistics.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.services.citation_graph_service import get_citation_graph_service

from backend.api.schemas.examples import ErrorResponseExample, SuccessResponseExample, build_responses

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get(
    "/citation-graph",
    summary="Get Citation Graph",
    description="BFS-traverse the cross-document citation graph from *root* up to *depth* hops. Returns ``{ nodes, edges, stats }`` suitable for force-directed graph rendering.",
    responses=build_responses(None),
)
def get_citation_graph(
    root: str = Query(..., description="ChromaDB document ID to start traversal from"),
    depth: int = Query(2, ge=1, le=5, description="BFS traversal depth (1–5)"),
    db: Session = Depends(get_db),
):
    """
    BFS-traverse the cross-document citation graph from *root* up to
    *depth* hops.

    Returns ``{ nodes, edges, stats }`` suitable for force-directed
    graph rendering.
    """
    svc = get_citation_graph_service()
    try:
        result = svc.get_citation_graph(db, root_doc_id=root, depth=depth)
    except Exception as exc:
        raise InternalServerError(error=str(exc), code="STREXC")

    return result


@router.get(
    "/citation-stats",
    summary="Get Citation Stats",
    description="Return the top *limit* most-cited documents with citation counts, average relevance, and last-cited timestamp.",
    responses=build_responses(None),
)
def get_citation_stats(
    limit: int = Query(20, ge=1, le=100, description="Top N most-cited documents"),
    db: Session = Depends(get_db),
):
    """
    Return the top *limit* most-cited documents with citation counts,
    average relevance, and last-cited timestamp.
    """
    svc = get_citation_graph_service()
    try:
        top_cited = svc.get_top_cited(db, limit=limit)
    except Exception as exc:
        raise InternalServerError(error=str(exc), code="STREXC")

    return {
        "top_cited": top_cited,
        "count": len(top_cited),
    }
