"""Verify self-healing periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_self_healing_verification() -> list:
    results = []

    # 1. agent-heartbeat -> agent_heartbeat()
    from backend.services.tasks.task_executor import agent_heartbeat
    results.append(run_task("agent-heartbeat", agent_heartbeat))

    # 2. crash-detection -> detect_crashed_agents()
    from backend.services.tasks.task_executor import detect_crashed_agents
    results.append(run_task("crash-detection", detect_crashed_agents))

    # 3. self-diagnostic-daily -> self_diagnostic_daily()
    from backend.services.tasks.task_executor import self_diagnostic_daily
    results.append(run_task("self-diagnostic-daily", self_diagnostic_daily))

    # 4. critical-path-guardian -> critical_path_guardian()
    from backend.services.tasks.task_executor import critical_path_guardian
    results.append(run_task("critical-path-guardian", critical_path_guardian))

    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_self_healing_verification()