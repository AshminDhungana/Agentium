"""Verify Celery task results are stored in Redis backend."""
import time
import json
import sys
import os

def verify_redis_results() -> dict:
    """Verify task results are stored in Redis with correct TTL."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

    from verification_utils import get_redis_client, get_celery_app

    redis_client = get_redis_client()
    celery_app = get_celery_app()

    results = {
        "redis_connected": False,
        "noop_task_result_stored": False,
        "result_structure_valid": False,
        "ttl_correct": False,
        "ignore_result_respected": False,
        "cleanup_done": False,
        "details": {}
    }

    try:
        # Test Redis connection
        redis_client.ping()
        results["redis_connected"] = True
    except Exception as e:
        return {"status": "fail", "error": f"Redis connection failed: {e}", **results}

    # Test 1: Submit noop task (has result)
    try:
        noop_task = celery_app.tasks.get('agentium.tasks.task_executor.execute_task_async_noop')
        if not noop_task:
            return {"status": "fail", "error": "noop task not registered", **results}

        async_result = noop_task.apply_async()
        task_id = async_result.id

        # Wait for result
        result_value = async_result.get(timeout=10)
        results["details"]["noop_result"] = result_value

        # Check Redis for result key
        result_key = f"celery-task-meta-{task_id}"
        stored = redis_client.get(result_key)
        if stored:
            results["noop_task_result_stored"] = True
            try:
                parsed = json.loads(stored)
                if parsed.get("result", {}).get("noop") is True:
                    results["result_structure_valid"] = True
            except json.JSONDecodeError:
                pass

            # Check TTL
            ttl = redis_client.ttl(result_key)
            results["details"]["ttl_seconds"] = ttl
            if 3000 <= ttl <= 3600:  # ~1 hour with some margin
                results["ttl_correct"] = True

            # Cleanup
            redis_client.delete(result_key)
            results["cleanup_done"] = True
        else:
            results["details"]["error"] = "Result key not found in Redis"

    except Exception as e:
        results["details"]["noop_test_error"] = str(e)

    # Test 2: Verify ignore_result=True tasks don't store results
    try:
        reindex_task = celery_app.tasks.get('agentium.tasks.reindex_knowledge.weekly_reindex_task')
        if reindex_task:
            async_result = reindex_task.apply_async()
            task_id = async_result.id

            # Wait briefly
            async_result.get(timeout=30, propagate=False)

            result_key = f"celery-task-meta-{task_id}"
            stored = redis_client.get(result_key)
            if stored is None:
                results["ignore_result_respected"] = True
            else:
                results["details"]["ignore_result_violation"] = f"Key exists: {result_key}"
                redis_client.delete(result_key)
    except Exception as e:
        results["details"]["ignore_result_test_error"] = str(e)

    # Overall status
    required = [
        results["redis_connected"],
        results["noop_task_result_stored"],
        results["result_structure_valid"],
    ]
    if all(required):
        results["status"] = "pass"
    elif results["redis_connected"]:
        results["status"] = "warn"
    else:
        results["status"] = "fail"

    return results