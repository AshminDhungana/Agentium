"""Verify channel health periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_channel_health_verification() -> list:
    """Verify all channel health beat tasks."""
    results = []

    # 1. health-check-every-5-minutes -> check_channel_health()
    from backend.services.tasks.task_executor import check_channel_health
    results.append(run_task("health-check-every-5-minutes", check_channel_health))

    # 2. cleanup-old-messages-daily -> cleanup_old_channel_messages(days=30)
    from backend.services.tasks.task_executor import cleanup_old_channel_messages
    results.append(run_task("cleanup-old-messages-daily", cleanup_old_channel_messages, days=1))  # Use 1 day for test

    # 3. imap-receiver-check -> start_imap_receivers()
    from backend.services.tasks.task_executor import start_imap_receivers
    results.append(run_task("imap-receiver-check", start_imap_receivers))

    # 4. channel-heartbeat -> send_channel_heartbeat()
    from backend.services.tasks.task_executor import send_channel_heartbeat
    results.append(run_task("channel-heartbeat", send_channel_heartbeat))

    # 5. channel-health-broadcast -> broadcast_channel_health()
    from backend.celery_app import broadcast_channel_health
    results.append(run_task("channel-health-broadcast", broadcast_channel_health))

    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_channel_health_verification()