"""Verify monitoring periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_monitoring_verification() -> list:
    results = []

    # 1. log-slow-query-summary-daily -> log_slow_query_summary_daily()
    from backend.services.tasks.task_executor import log_slow_query_summary_daily
    results.append(run_task("log-slow-query-summary-daily", log_slow_query_summary_daily))

    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_monitoring_verification()