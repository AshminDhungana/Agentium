"""Verify MCP periodic tasks."""
from scripts.verify_periodic_tasks.common import run_task, print_results_table, print_summary

def run_mcp_verification() -> list:
    results = []

    # 1. mcp-stats-broadcast -> broadcast_mcp_stats()
    from backend.celery_app import broadcast_mcp_stats
    results.append(run_task("mcp-stats-broadcast", broadcast_mcp_stats))

    # 2. provider-metrics-broadcast -> broadcast_provider_metrics()
    from backend.celery_app import broadcast_provider_metrics
    results.append(run_task("provider-metrics-broadcast", broadcast_provider_metrics))

    print_results_table(results)
    print_summary(results)
    return results

if __name__ == "__main__":
    run_mcp_verification()