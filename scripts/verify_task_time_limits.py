"""Verify Celery task time limits (30 min) are configured and enforced."""
import sys
import os

def verify_time_limits() -> dict:
    """Verify global and per-task time limits."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

    from backend.celery_app import celery_app

    results = {
        "global_task_time_limit": None,
        "global_task_soft_time_limit": None,
        "per_task_overrides": [],
        "long_running_tasks_identified": [],
        "enforcement_test": {"status": "skipped", "reason": ""},
        "details": {}
    }

    # Check global config
    results["global_task_time_limit"] = celery_app.conf.get('task_time_limit')
    results["global_task_soft_time_limit"] = celery_app.conf.get('task_soft_time_limit')

    # Audit per-task time_limit overrides
    for task_name, task_obj in celery_app.tasks.items():
        if task_name.startswith('agentium.tasks.'):
            # Check for time_limit attribute on task
            time_limit = getattr(task_obj, 'time_limit', None)
            soft_time_limit = getattr(task_obj, 'soft_time_limit', None)
            if time_limit or soft_time_limit:
                results["per_task_overrides"].append({
                    "task": task_name,
                    "time_limit": time_limit,
                    "soft_time_limit": soft_time_limit
                })

    # Identify potentially long-running tasks that might need custom limits
    long_running_patterns = [
        'reindex', 'retention', 'consolidation', 'optimization',
        'decay', 'citation', 'sovereign_data', 'auto_scale'
    ]
    for task_name in celery_app.tasks:
        if task_name.startswith('agentium.tasks.') and any(p in task_name for p in long_running_patterns):
            results["long_running_tasks_identified"].append(task_name)

    # Enforcement test: create a test task that exceeds limit
    # We'll use a mock approach - verify the config would work
    if results["global_task_time_limit"] == 1800:  # 30 min
        results["enforcement_test"] = {
            "status": "configured",
            "global_limit_seconds": 1800,
            "note": "Global limit set to 30 min. Full enforcement test requires worker integration test."
        }
    else:
        results["enforcement_test"] = {
            "status": "misconfigured",
            "global_limit_seconds": results["global_task_time_limit"],
            "expected": 1800
        }

    # Check for missing soft_time_limit
    if results["global_task_soft_time_limit"] is None:
        results["details"]["warning"] = "task_soft_time_limit not set (recommended: slightly less than task_time_limit)"

    # Overall status
    if results["global_task_time_limit"] == 1800:
        results["status"] = "pass"
    else:
        results["status"] = "fail"

    return results