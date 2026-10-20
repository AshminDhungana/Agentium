"""Verify constitution & governance periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_constitution_governance_verification() -> list:
    results = []

    # 1. constitution-daily-review -> daily_constitution_review()
    from backend.services.tasks.task_executor import daily_constitution_review
    results.append(run_task("constitution-daily-review", daily_constitution_review))

    # 2. weekly-knowledge-reindex -> weekly_reindex_task()
    from backend.services.tasks.reindex_knowledge import weekly_reindex_task
    results.append(run_task("weekly-knowledge-reindex", weekly_reindex_task))

    # 3. idle-task-processor -> process_idle_tasks()
    from backend.services.tasks.task_executor import process_idle_tasks
    results.append(run_task("idle-task-processor", process_idle_tasks))

    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_constitution_governance_verification()