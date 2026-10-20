"""Verify federation periodic tasks (beat schedule only)."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_federation_verification() -> list:
    results = []

    # 1. federation-heartbeat -> federation_heartbeat()
    from backend.celery_app import federation_heartbeat
    results.append(run_task("federation-heartbeat", federation_heartbeat))

    # 2. federation-cleanup-stale -> federation_cleanup_stale()
    from backend.celery_app import federation_cleanup_stale
    results.append(run_task("federation-cleanup-stale", federation_cleanup_stale))

    # Note: deliver_federated_task and send_federation_result are NOT in beat_schedule
    # They are on-demand tasks, not periodic

    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_federation_verification()