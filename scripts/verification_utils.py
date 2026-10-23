"""Shared utilities for 20.3 verification scripts."""
import json
import sys
import time
import os
from typing import Dict, Any, List, Optional
from contextlib import contextmanager
from datetime import datetime

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def get_redis_client():
    """Get Redis client from celery_app config."""
    import redis
    from backend.celery_app import celery_app
    backend_url = celery_app.conf.result_backend or 'redis://redis:6379/0'
    return redis.from_url(backend_url, decode_responses=True)

def get_celery_app():
    """Get configured celery app."""
    from backend.celery_app import celery_app
    return celery_app

@contextmanager
def temp_db_session():
    """Create temporary DB session for test data."""
    from backend.services.tasks.task_executor import get_task_db
    with get_task_db() as db:
        yield db

def run_verification(item: str, verify_fn) -> Dict[str, Any]:
    """Run a verification function and return standardized result."""
    start = time.perf_counter()
    try:
        details = verify_fn()
        status = details.get("status", "pass")
        return {
            "item": item,
            "status": status,
            "duration_ms": int((time.perf_counter() - start) * 1000),
            "details": details
        }
    except Exception as e:
        return {
            "item": item,
            "status": "fail",
            "duration_ms": int((time.perf_counter() - start) * 1000),
            "details": {"error": str(e), "status": "fail"}
        }

def aggregate_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate multiple verification results."""
    summary = {"total": len(results), "passed": 0, "failed": 0, "warnings": 0}
    for r in results:
        if r["status"] == "pass":
            summary["passed"] += 1
        elif r["status"] == "fail":
            summary["failed"] += 1
        elif r["status"] == "warn":
            summary["warnings"] += 1
    return {
        "summary": summary,
        "items": results,
        "timestamp": datetime.utcnow().isoformat()
    }

def print_json_result(result: Dict[str, Any]):
    """Print result as JSON to stdout."""
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")

def exit_from_summary(summary: Dict[str, Any]):
    """Exit with appropriate code based on summary."""
    sys.exit(0 if summary["failed"] == 0 else 1)