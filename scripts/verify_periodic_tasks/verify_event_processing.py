"""Verify event processing periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_event_processing_verification() -> list:
    results = []

    # 1. threshold-event-check -> threshold_event_check()
    from backend.services.tasks.task_executor import threshold_event_check
    results.append(run_task("threshold-event-check", threshold_event_check))

    # 2. external-api-poll -> external_api_poll()
    from backend.services.tasks.task_executor import external_api_poll
    results.append(run_task("external-api-poll", external_api_poll))

    # 3. schedule-trigger-check -> schedule_trigger_check()
    from backend.services.tasks.task_executor import schedule_trigger_check
    results.append(run_task("schedule-trigger-check", schedule_trigger_check))

    # 4. poll-wait-conditions -> poll_wait_conditions()
    from backend.services.tasks.task_executor import poll_wait_conditions
    results.append(run_task("poll-wait-conditions", poll_wait_conditions))

    # 5. poll-execution-conditions -> poll_execution_conditions()
    from backend.services.tasks.task_executor import poll_execution_conditions
    results.append(run_task("poll-execution-conditions", poll_execution_conditions))

    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_event_processing_verification()