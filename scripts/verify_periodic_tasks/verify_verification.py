"""Verify verification periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_verification_tasks_verification() -> list:
    results = []

    # 1. verify-agents-every-5-minutes -> verify_agents_task()
    from backend.services.tasks.verification_tasks import verify_agents_task
    results.append(run_task("verify-agents-every-5-minutes", verify_agents_task))

    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_verification_tasks_verification()