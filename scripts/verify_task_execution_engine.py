#!/usr/bin/env python
"""Master runner for 20.3 Task Execution Engine verifications."""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from verification_utils import run_verification, aggregate_results, print_json_result, exit_from_summary

# Import individual verification functions
from verify_task_executor_imports import verify_imports
# from verify_task_results_redis import verify_redis_results
# from verify_task_time_limits import verify_time_limits
# from verify_task_retries import verify_retries
# from verify_workflow_tasks import verify_workflow_tasks
# from verify_reindex_knowledge import verify_reindex

VERIFICATIONS = {
    "20.3.1": ("task_executor imports", verify_imports),
    # "20.3.2": ("task results in Redis", verify_redis_results),
    # "20.3.3": ("task time limits", verify_time_limits),
    # "20.3.4": ("task retries with backoff", verify_retries),
    # "20.3.5": ("workflow tasks execution", verify_workflow_tasks),
    # "20.3.6": ("reindex knowledge task", verify_reindex),
}

def main():
    parser = argparse.ArgumentParser(description="Run 20.3 Task Execution Engine verifications")
    parser.add_argument("--item", help="Run specific item (e.g., 20.3.1)")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    if args.item:
        if args.item not in VERIFICATIONS:
            print(f"Unknown item: {args.item}", file=sys.stderr)
            sys.exit(1)
        items_to_run = {args.item: VERIFICATIONS[args.item]}
    else:
        items_to_run = VERIFICATIONS

    results = []
    for item, (name, verify_fn) in items_to_run.items():
        if not args.json:
            print(f"Running {item}: {name}...")
        result = run_verification(item, verify_fn)
        results.append(result)
        if not args.json:
            status = result["status"].upper()
            print(f"  {status} ({result['duration_ms']}ms)")

    aggregated = aggregate_results(results)
    print_json_result(aggregated)
    exit_from_summary(aggregated["summary"])

if __name__ == "__main__":
    main()