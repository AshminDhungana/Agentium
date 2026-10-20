"""Verify task execution periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_task_execution_verification() -> list:
    results = []

    # 1. handle-task-escalation -> handle_task_escalation()
    from backend.services.tasks.task_executor import handle_task_escalation
    results.append(run_task("handle-task-escalation", handle_task_escalation))

    # 2. chat-history-prune-daily -> chat_prune_task(dry_run=True)
    from backend.services.tasks.task_executor import chat_prune_task
    results.append(run_task("chat-history-prune-daily", chat_prune_task, dry_run=True))

    # 3. sovereign-data-retention -> sovereign_data_retention()
    from backend.services.tasks.task_executor import sovereign_data_retention
    results.append(run_task("sovereign-data-retention", sovereign_data_retention))

    # 4. auto-scale-check -> auto_scale_check()
    from backend.services.tasks.task_executor import auto_scale_check
    results.append(run_task("auto-scale-check", auto_scale_check))

    # 5. auto-escalation-timer -> check_escalation_timeouts()
    from backend.services.tasks.task_executor import check_escalation_timeouts
    results.append(run_task("auto-escalation-timer", check_escalation_timeouts))

    # 6. dependency-graph-processor -> process_dependency_graph()
    from backend.services.tasks.task_executor import process_dependency_graph
    results.append(run_task("dependency-graph-processor", process_dependency_graph))

    # 7. scheduled-task-dispatcher -> dispatch_due_scheduled_tasks()
    from backend.services.tasks.scheduled_task_dispatcher import dispatch_due_scheduled_tasks
    results.append(run_task("scheduled-task-dispatcher", dispatch_due_scheduled_tasks))

    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_task_execution_verification()