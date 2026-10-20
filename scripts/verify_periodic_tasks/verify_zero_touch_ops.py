"""Verify zero-touch operations periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_zero_touch_ops_verification() -> list:
    results = []

    # 1. anomaly-detection -> anomaly_detection()
    from backend.services.tasks.task_executor import anomaly_detection
    results.append(run_task("anomaly-detection", anomaly_detection))

    # 2. sla-monitor -> sla_monitor()
    from backend.services.tasks.task_executor import sla_monitor
    results.append(run_task("sla-monitor", sla_monitor))

    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_zero_touch_ops_verification()