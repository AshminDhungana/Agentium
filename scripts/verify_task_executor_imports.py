"""Verify all Celery task functions in task_executor.py are importable and callable."""
import inspect
import sys
import os

def verify_imports() -> dict:
    """Verify all @celery_app.task functions in task_executor module."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

    # Import the module
    try:
        from backend.services.tasks import task_executor
    except ImportError as e:
        return {"status": "fail", "error": f"Module import failed: {e}"}

    # Get celery app to find registered tasks
    from backend.celery_app import celery_app

    # Find all task functions in the module
    task_functions = []
    for name, obj in inspect.getmembers(task_executor, inspect.isfunction):
        if hasattr(obj, '__wrapped__') and 'celery_app.task' in str(obj.__wrapped__):
            task_functions.append((name, obj))
        elif hasattr(obj, 'name') and obj.name.startswith('agentium.tasks.task_executor.'):
            task_functions.append((name, obj))

    # Also check celery_app.tasks registry for our namespace
    registered_tasks = [
        (name, task) for name, task in celery_app.tasks.items()
        if name.startswith('agentium.tasks.task_executor.')
    ]

    results = {
        "module_tasks_found": len(task_functions),
        "registered_tasks_found": len(registered_tasks),
        "tasks": [],
        "import_errors": [],
        "signature_issues": [],
        "callable_results": []
    }

    # Check each registered task
    for task_name, task_obj in registered_tasks:
        task_info = {"name": task_name, "importable": True, "callable": False, "signature_ok": True}

        # Try to get the underlying function
        func = task_obj
        if hasattr(task_obj, '__wrapped__'):
            func = task_obj.__wrapped__
        elif hasattr(task_obj, 'run'):
            func = task_obj.run

        # Check signature
        try:
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            # Beat tasks should have no required args (or all have defaults)
            required_params = [p for p in params if sig.parameters[p].default == inspect.Parameter.empty]
            if required_params and 'self' not in required_params:
                task_info["signature_ok"] = False
                results["signature_issues"].append(f"{task_name}: required params {required_params}")
        except Exception as e:
            task_info["signature_ok"] = False
            results["signature_issues"].append(f"{task_name}: signature inspection failed: {e}")

        # Try dry-run call for non-beat tasks (those with bind=True or explicit args)
        # Skip tasks that clearly need DB/external deps
        skip_dry_run = any(x in task_name for x in [
            'execute_task_async', 'retry_channel_message', 'broadcast_to_channels',
            'handle_task_escalation', 'sovereign_data_retention', 'auto_scale_check',
            'check_stalled_reasoning', 'cleanup_old_channel_messages', 'check_channel_health',
            'start_imap_receivers', 'send_channel_heartbeat', 'process_dependency_graph',
            'detect_crashed_agents', 'self_diagnostic_daily', 'critical_path_guardian',
            'knowledge_consolidation', 'performance_optimization', 'decay_learnings',
            'update_citation_boosts', 'cleanup_citation_edges', 'detect_suspicious_patterns',
            'chat_prune_task', 'generate_auto_tools', 'poll_wait_conditions',
            'poll_execution_conditions', 'log_slow_query_summary_daily'
        ])

        if not skip_dry_run:
            try:
                # Call with no args (beat tasks should work)
                if hasattr(task_obj, 'apply'):
                    # Use apply() for synchronous execution in test
                    result = task_obj.apply(args=(), kwargs={}, throw=True)
                    task_info["callable"] = True
                    task_info["dry_run_result"] = str(result.result)[:100]
                else:
                    task_info["callable"] = "skipped (no apply method)"
            except Exception as e:
                task_info["callable"] = False
                task_info["call_error"] = str(e)[:200]

        results["tasks"].append(task_info)

    # Overall status
    failed_imports = [t for t in results["tasks"] if not t["importable"]]
    failed_callable = [t for t in results["tasks"] if t.get("callable") is False]

    if failed_imports:
        results["status"] = "fail"
    elif failed_callable or results["signature_issues"]:
        results["status"] = "warn"
    else:
        results["status"] = "pass"

    return results