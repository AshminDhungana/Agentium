#!/usr/bin/env python3
"""Master runner for all periodic task verifications."""
import json
import sys
from scripts.verify_periodic_tasks.common import print_summary

# Import all category runners
from scripts.verify_periodic_tasks.verify_channel_health import run_channel_health_verification
from scripts.verify_periodic_tasks.verify_constitution_governance import run_constitution_governance_verification
from scripts.verify_periodic_tasks.verify_task_execution import run_task_execution_verification
from scripts.verify_periodic_tasks.verify_self_healing import run_self_healing_verification
from scripts.verify_periodic_tasks.verify_predictive_scaling import run_predictive_scaling_verification
from scripts.verify_periodic_tasks.verify_self_improvement import run_self_improvement_verification
from scripts.verify_periodic_tasks.verify_event_processing import run_event_processing_verification
from scripts.verify_periodic_tasks.verify_zero_touch_ops import run_zero_touch_ops_verification
from scripts.verify_periodic_tasks.verify_federation import run_federation_verification
from scripts.verify_periodic_tasks.verify_mcp import run_mcp_verification
from scripts.verify_periodic_tasks.verify_security import run_security_verification
from scripts.verify_periodic_tasks.verify_verification import run_verification_tasks_verification
from scripts.verify_periodic_tasks.verify_monitoring import run_monitoring_verification

CATEGORY_RUNNERS = [
    ("Channel Health", run_channel_health_verification),
    ("Constitution & Governance", run_constitution_governance_verification),
    ("Task Execution", run_task_execution_verification),
    ("Self-Healing", run_self_healing_verification),
    ("Predictive Scaling", run_predictive_scaling_verification),
    ("Self-Improvement", run_self_improvement_verification),
    ("Event Processing", run_event_processing_verification),
    ("Zero-Touch Operations", run_zero_touch_ops_verification),
    ("Federation", run_federation_verification),
    ("MCP", run_mcp_verification),
    ("Security", run_security_verification),
    ("Verification Tasks", run_verification_tasks_verification),
    ("Monitoring", run_monitoring_verification),
]

def main():
    all_results = []
    category_summaries = {}

    print("=" * 70)
    print("PERIODIC TASKS VERIFICATION - ALL CATEGORIES")
    print("=" * 70)

    for category_name, runner_fn in CATEGORY_RUNNERS:
        print(f"\n{'='*70}")
        print(f"CATEGORY: {category_name}")
        print(f"{'='*70}")

        try:
            results = runner_fn()
            all_results.extend(results)

            # Collect summary
            summary = print_summary(results)
            category_summaries[category_name] = summary
        except Exception as e:
            print(f"CATEGORY {category_name} FAILED TO RUN: {e}")
            import traceback
            traceback.print_exc()
            category_summaries[category_name] = {"error": str(e)}

    # Overall summary
    print(f"\n{'='*70}")
    print("OVERALL SUMMARY")
    print(f"{'='*70}")

    total_passed = sum(s.get("passed", 0) for s in category_summaries.values() if isinstance(s, dict) and "passed" in s)
    total_failed = sum(s.get("failed", 0) for s in category_summaries.values() if isinstance(s, dict) and "failed" in s)
    total_skipped = sum(s.get("skipped", 0) for s in category_summaries.values() if isinstance(s, dict) and "skipped" in s)
    total_tasks = sum(s.get("total", 0) for s in category_summaries.values() if isinstance(s, dict) and "total" in s)

    print(f"Total: {total_passed} passed, {total_failed} failed, {total_skipped} skipped / {total_tasks} tasks")

    # JSON output for CI/automation
    output = {
        "summary": {
            "passed": total_passed,
            "failed": total_failed,
            "skipped": total_skipped,
            "total": total_tasks,
        },
        "categories": category_summaries,
        "tasks": [
            {
                "name": r.name,
                "status": r.status,
                "error": r.error,
                "duration_ms": r.duration_ms,
            }
            for r in all_results
        ],
    }

    with open("verification_results.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults written to verification_results.json")

    # Exit code
    if total_failed > 0:
        print(f"\n[FAIL] VERIFICATION FAILED: {total_failed} task(s) failed")
        sys.exit(1)
    else:
        print(f"\n[PASS] ALL TASKS PASSED")
        sys.exit(0)

if __name__ == "__main__":
    main()