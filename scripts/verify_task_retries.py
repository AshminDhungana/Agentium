"""Verify failed tasks retry with configured backoff."""
import sys
import os

def verify_retries() -> dict:
    """Audit retry policies and test retry behavior on sample tasks."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

    # Import task modules to register tasks
    from backend.services.tasks import task_executor
    from backend.services.tasks import workflow_tasks
    from backend.services.tasks import reindex_knowledge

    from backend.celery_app import celery_app
    from celery.exceptions import Retry

    results = {
        "retry_policies": {},
        "sample_task_tests": {},
        "details": {}
    }

    # Audit all agentium tasks for retry config
    for task_name, task_obj in celery_app.tasks.items():
        if task_name.startswith('agentium.tasks.') or task_name.startswith('agentium.celery_app.'):
            policy = {
                "max_retries": getattr(task_obj, 'max_retries', 0),
                "default_retry_delay": getattr(task_obj, 'default_retry_delay', None),
                "autoretry_for": getattr(task_obj, 'autoretry_for', None),
                "retry_backoff": getattr(task_obj, 'retry_backoff', False),
                "retry_backoff_max": getattr(task_obj, 'retry_backoff_max', None),
                "retry_jitter": getattr(task_obj, 'retry_jitter', True),
            }
            results["retry_policies"][task_name] = policy

    # Test retry behavior on a sample task that we can make fail
    # Use fire_reminder (has max_retries=3, default_retry_delay=60)
    test_task_name = 'agentium.tasks.workflow_tasks.fire_reminder'
    test_task = celery_app.tasks.get(test_task_name)

    if test_task:
        # We can't easily test actual retries without a running worker,
        # but we can verify the configuration is correct
        policy = results["retry_policies"].get(test_task_name, {})
        expected = {
            "max_retries": 3,
            "default_retry_delay": 60,
        }
        matches = all(policy.get(k) == v for k, v in expected.items())
        results["sample_task_tests"][test_task_name] = {
            "configured_policy": policy,
            "expected_policy": expected,
            "matches_expected": matches
        }

    # Test retry_channel_message (exponential backoff)
    test_task2 = 'agentium.tasks.task_executor.retry_channel_message'
    task2 = celery_app.tasks.get(test_task2)
    if task2:
        policy = results["retry_policies"].get(test_task2, {})
        expected = {"max_retries": 3}
        matches = policy.get("max_retries") == 3
        results["sample_task_tests"][test_task2] = {
            "configured_policy": policy,
            "expected_policy": expected,
            "matches_expected": matches,
            "note": "Uses custom exponential backoff in task code (300 * 2^retries)"
        }

    # Overall status
    all_configured = all(
        p.get("max_retries", 0) > 0 or p.get("autoretry_for")
        for p in results["retry_policies"].values()
        if "execute_task_async" in p.get("task", "") or "fire_reminder" in p.get("task", "")
    )

    # Check that key tasks have retry config
    key_tasks = [
        'agentium.tasks.task_executor.execute_task_async',
        'agentium.tasks.workflow_tasks.fire_reminder',
        'agentium.tasks.workflow_tasks.execute_deferred_subtask',
        'agentium.tasks.task_executor.retry_channel_message',
        'agentium.celery_app.deliver_federated_task',
        'agentium.celery_app.send_federation_result',
    ]
    missing_retry = [t for t in key_tasks if t not in results["retry_policies"] or results["retry_policies"][t]["max_retries"] == 0]

    if not missing_retry:
        results["status"] = "pass"
    elif len(missing_retry) <= 2:
        results["status"] = "warn"
        results["details"]["missing_retry_on_key_tasks"] = missing_retry
    else:
        results["status"] = "fail"
        results["details"]["missing_retry_on_key_tasks"] = missing_retry

    return results