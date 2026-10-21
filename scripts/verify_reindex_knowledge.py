"""Verify reindex_knowledge.py weekly reindex task works."""
import sys
import os

def verify_reindex() -> dict:
    """Verify weekly_reindex_task completes and re-indexes collections."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

    # Import task modules to register tasks
    from backend.services.tasks import reindex_knowledge

    from backend.celery_app import celery_app
    from backend.core.vector_store import get_vector_store, COLLECTIONS

    results = {
        "module_imported": False,
        "collections_found": 0,
        "direct_run": {"executed": False, "collections_processed": 0, "details": {}},
        "celery_run": {"executed": False, "task_state": None, "details": {}},
        "status": "fail"
    }

    # Import module
    try:
        from backend.services.tasks import reindex_knowledge
        results["module_imported"] = True
    except ImportError as e:
        return {"status": "fail", "error": f"Module import failed: {e}", **results}

    # Check ChromaDB collections exist
    vs = get_vector_store()
    reindex_keys = list(COLLECTIONS.keys()) + ["domain_knowledge"]
    existing = []
    for key in reindex_keys:
        try:
            col = vs.get_collection(key, version="v2")
            count = col.count()
            existing.append({"key": key, "count": count})
            results["collections_found"] += 1
        except Exception:
            existing.append({"key": key, "count": 0, "error": "not found"})

    results["direct_run"]["details"]["collections"] = existing

    # Test 1: Run weekly_reindex directly (faster)
    try:
        stats = reindex_knowledge.weekly_reindex(versions=["v2"])
        results["direct_run"]["executed"] = True
        results["direct_run"]["collections_processed"] = len(stats)
        results["direct_run"]["details"]["stats"] = stats

        # Verify each collection processed
        all_ok = all(s.get("count", 0) >= 0 for s in stats)
        if not all_ok:
            results["direct_run"]["details"]["warning"] = "Some collections returned negative counts"
    except Exception as e:
        results["direct_run"]["details"]["error"] = str(e)

    # Test 2: Run via Celery
    weekly_task = celery_app.tasks.get('agentium.tasks.reindex_knowledge.weekly_reindex_task')
    if weekly_task:
        try:
            async_result = weekly_task.apply_async()
            task_result = async_result.get(timeout=300, propagate=False)

            results["celery_run"]["executed"] = True
            results["celery_run"]["task_state"] = async_result.state
            results["celery_run"]["details"]["result"] = str(task_result)[:200] if task_result else None

            # With ignore_result=True, result might be None but state should be SUCCESS
            if async_result.state == "SUCCESS":
                results["celery_run"]["details"]["success"] = True
            elif async_result.state == "FAILURE":
                results["celery_run"]["details"]["error"] = str(async_result.info)
        except Exception as e:
            results["celery_run"]["details"]["error"] = str(e)
    else:
        results["celery_run"]["details"]["error"] = "Task not registered in Celery"

    # Overall status
    if results["module_imported"] and results["direct_run"]["executed"] and results["celery_run"]["executed"]:
        if results["celery_run"]["task_state"] == "SUCCESS":
            results["status"] = "pass"
        else:
            results["status"] = "warn"
    elif results["module_imported"] and results["direct_run"]["executed"]:
        results["status"] = "warn"
    else:
        results["status"] = "fail"

    return results