import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import redis.asyncio as aioredis

from backend.api.schemas.examples import ErrorResponseExample, SuccessResponseExample
from backend.core.auth import get_current_user
from backend.core.exceptions import ForbiddenError, InternalServerError
from backend.models.database import get_db
from backend.models.entities.critics import CritiqueReview, CriticVerdict
from backend.services.autonomous_learning import get_learning_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/improvements", tags=["Continuous Improvement"])

redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

@router.get(
    "/impact",
    summary="Get learning impact",
    description="Learning Impact Tracker: read success_rate_delta and other stats.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        500: {"description": "Internal Server Error", "model": ErrorResponseExample},
    },
)
async def get_learning_impact(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Learning Impact Tracker: derives success_rate_delta and history from CritiqueReviews
    and learning metrics from AutonomousLearningEngine and ChromaDB.
    """
    try:
        engine = get_learning_engine()
        engine_stats = engine.get_learning_stats()

        total_reviews_processed = int(engine_stats.get("total_reviews_processed", 0))
        tools_generated = int(engine_stats.get("best_practices_extracted", 0))
        anti_patterns_warned = int(engine_stats.get("anti_patterns_extracted", 0))

        # Query CritiqueReviews from the database
        now = datetime.utcnow()
        cutoff = now - timedelta(days=14)
        reviews = (
            db.query(CritiqueReview)
            .filter(CritiqueReview.reviewed_at >= cutoff)
            .order_by(CritiqueReview.reviewed_at.asc())
            .all()
        )

        db_processed_count = (
            db.query(CritiqueReview)
            .filter(CritiqueReview.learning_extracted == 1)
            .count()
        )
        total_reviews_processed = max(total_reviews_processed, db_processed_count)

        # Check vector store for extracted pattern counts if available
        try:
            from backend.core.vector_store import get_vector_store
            vs = get_vector_store()
            coll = vs.get_collection("task_patterns")
            res = coll.get(include=["metadatas"])
            if res and res.get("metadatas"):
                bp_count = sum(1 for m in res["metadatas"] if m and m.get("type") == "best_practice")
                ap_count = sum(1 for m in res["metadatas"] if m and m.get("type") == "anti_pattern")
                tools_generated = max(tools_generated, bp_count)
                anti_patterns_warned = max(anti_patterns_warned, ap_count)
        except Exception as vs_err:
            logger.debug(f"Vector store check skipped in get_learning_impact: {vs_err}")

        # Check Redis if available (optional metrics enrichment)
        try:
            r = await aioredis.from_url(redis_url, decode_responses=True)
            r_tools = await r.hget("agentium:learning:impact", "tools_generated")
            if r_tools is not None:
                tools_generated = max(tools_generated, int(r_tools))
            r_anti = await r.hget("agentium:learning:impact", "anti_patterns_warned")
            if r_anti is not None:
                anti_patterns_warned = max(anti_patterns_warned, int(r_anti))
            await r.close()
        except Exception:
            pass

        # Calculate history for the last 7 days
        today = now.date()
        daily_stats: Dict[str, Dict[str, int]] = {}
        for r in reviews:
            dt = r.reviewed_at or r.created_at
            if not dt:
                continue
            d_str = dt.date().isoformat()
            if d_str not in daily_stats:
                daily_stats[d_str] = {"total": 0, "passed": 0}
            daily_stats[d_str]["total"] += 1
            if r.verdict == CriticVerdict.PASS:
                daily_stats[d_str]["passed"] += 1

        history: List[Dict[str, Any]] = []
        for i in range(6, -1, -1):
            d_str = (today - timedelta(days=i)).isoformat()
            stat = daily_stats.get(d_str)
            if stat and stat["total"] > 0:
                rate = round((stat["passed"] / stat["total"]) * 100.0, 1)
            else:
                rate = 0.0
            history.append({"date": d_str, "success_rate": rate})

        # Calculate success_rate_delta comparing last 7 days vs previous 7 days
        curr_cutoff = now - timedelta(days=7)
        curr_reviews = [r for r in reviews if (r.reviewed_at or r.created_at) >= curr_cutoff]
        prev_reviews = [r for r in reviews if (r.reviewed_at or r.created_at) < curr_cutoff]

        curr_rate = (
            (sum(1 for r in curr_reviews if r.verdict == CriticVerdict.PASS) / len(curr_reviews)) * 100.0
            if curr_reviews else 0.0
        )
        prev_rate = (
            (sum(1 for r in prev_reviews if r.verdict == CriticVerdict.PASS) / len(prev_reviews)) * 100.0
            if prev_reviews else 0.0
        )

        if prev_reviews and curr_reviews:
            success_rate_delta = round(curr_rate - prev_rate, 1)
        elif curr_reviews:
            success_rate_delta = round(curr_rate, 1)
        else:
            success_rate_delta = 0.0

        return {
            "success_rate_delta": float(success_rate_delta),
            "tools_generated": int(tools_generated),
            "anti_patterns_warned": int(anti_patterns_warned),
            "total_reviews_processed": int(total_reviews_processed),
            "history": history,
        }
    except Exception as e:
        logger.error(f"Error retrieving learning impact: {e}")
        raise InternalServerError(error=f"Failed to fetch learning impact: {str(e)}", code="LEARNING_IMPACT_ERROR")

@router.get(
    "/patterns",
    summary="Get patterns",
    description="Get best practices and anti-patterns from the system.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        500: {"description": "Internal Server Error", "model": ErrorResponseExample},
    },
)
async def get_patterns(
    current_user: dict = Depends(get_current_user),
):
    """
    Get best practices and anti-patterns extracted and stored in ChromaDB task_patterns.
    """
    patterns: List[Dict[str, Any]] = []
    try:
        from backend.core.vector_store import get_vector_store
        vs = get_vector_store()
        coll = vs.get_collection("task_patterns")
        all_docs = coll.get(include=["documents", "metadatas"])

        if all_docs and all_docs.get("ids"):
            ids = all_docs["ids"]
            docs = all_docs.get("documents") or []
            metas = all_docs.get("metadatas") or []
            for i, doc_id in enumerate(ids):
                meta = metas[i] if i < len(metas) and metas[i] else {}
                content = docs[i] if i < len(docs) and docs[i] else ""
                patterns.append({
                    "id": str(doc_id),
                    "type": str(meta.get("type", "best_practice")),
                    "content": str(content),
                    "confidence": float(meta.get("confidence", 0.8)),
                })
    except Exception as e:
        logger.warning(f"Could not fetch patterns from vector store: {e}")

    return {"patterns": patterns}

@router.post(
    "/consolidate",
    summary="Trigger consolidation",
    description="Trigger model consolidation process.",
    responses={
        200: {"description": "Success", "model": SuccessResponseExample},
        400: {"description": "Bad Request", "model": ErrorResponseExample},
        401: {"description": "Unauthorized", "model": ErrorResponseExample},
        403: {"description": "Forbidden", "model": ErrorResponseExample},
        404: {"description": "Not Found", "model": ErrorResponseExample},
        429: {"description": "Too Many Requests", "model": ErrorResponseExample},
        500: {"description": "Internal Server Error", "model": ErrorResponseExample},
    },
)
async def trigger_consolidation(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Trigger autonomous learning consolidation to extract learnings from recent critique reviews.
    Admin or Sovereign only.
    """
    if not (
        current_user.get("is_admin")
        or current_user.get("role") in ("primary_sovereign", "deputy_sovereign", "admin", "sovereign")
    ):
        raise ForbiddenError(
            error="Admin permissions required to trigger consolidation.",
            code="ADMIN_PERMISSIONS_REQUIRED",
        )

    try:
        engine = get_learning_engine()
        result = engine.analyze_outcomes(db)
        return {"status": "completed", "result": result}
    except Exception as e:
        logger.error(f"Failed during learning consolidation: {e}")
        raise InternalServerError(
            error=f"Consolidation failed: {str(e)}",
            code="CONSOLIDATION_FAILED",
        )

