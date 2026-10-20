"""Verify security periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_security_verification() -> list:
    results = []

    # 1. suspicious-pattern-detection -> detect_suspicious_patterns()
    from backend.services.tasks.task_executor import detect_suspicious_patterns
    results.append(run_task("suspicious-pattern-detection", detect_suspicious_patterns))

    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_security_verification()