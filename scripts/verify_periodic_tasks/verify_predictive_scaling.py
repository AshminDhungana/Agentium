"""Verify predictive scaling periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_predictive_scaling_verification() -> list:
    results = []

    # 1. load-metrics-snapshot -> metrics_snapshot()
    from backend.services.tasks.task_executor import metrics_snapshot
    results.append(run_task("load-metrics-snapshot", metrics_snapshot))

    # 2. predictive-scaling-check -> predictive_scale()
    from backend.services.tasks.task_executor import predictive_scale
    results.append(run_task("predictive-scaling-check", predictive_scale))

    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_predictive_scaling_verification()