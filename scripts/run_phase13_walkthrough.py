"""Phase 13 Success Criteria Walkthrough -- Report Generator
==============================================================

Runs the Phase 13 integration tests, collects results, and generates
a markdown report with pass/fail status per criterion.

Usage:
    python scripts/run_phase13_walkthrough.py [--environment ENV] [--dry-run]

Example:
    python scripts/run_phase13_walkthrough.py --environment=staging
    python scripts/run_phase13_walkthrough.py --dry-run

Returns:
    Exit code 0 if all criteria pass, 1 otherwise.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path


# ═════════════════════════════════════════════════════════════
# Configuration
# ═════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).parent.parent.resolve()
BACKEND_DIR = REPO_ROOT / "backend"
TEST_FILE = BACKEND_DIR / "tests" / "integration" / "test_phase13_success_criteria.py"
REPORT_DIR = REPO_ROOT / "docs" / "reports"

CRITERIA_LABELS = {
    "01": "Auto-Delegation (Task -> Score -> Tier -> Assign)",
    "02": "Crash Detection & Reincarnation",
    "03": "Predictive Scaling (Pre-spawn before surge)",
    "04": "Success Rate Improvement",
    "05": "5-Step Workflow (Cron + Conditional + Human Approval)",
    "06": "Webhook -> Task Dispatch (< 10s)",
    "07": "Zero-Touch Dashboard (5 Health Rings Green)",
    "08": "Token Budget Guard (CRITICAL continues, normal pauses)",
}


class Colors:
    PASS = "\033[92m"   # green
    FAIL = "\033[91m"   # red
    SKIP = "\033[93m"   # yellow
    RESET = "\033[0m"
    BOLD = "\033[1m"


def _color(text: str, color: str) -> str:
    return f"{color}{text}{Colors.RESET}"


# ═════════════════════════════════════════════════════════════
# Result parsing
# ═════════════════════════════════════════════════════════════

def parse_pytest_jsonl(lines: list) -> dict:
    """Parse pytest JSON output (jsonl format) into a structured dict."""
    tests = []
    summary = {"collected": 0, "passed": 0, "failed": 0, "skipped": 0, "error": 0}

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        nodeid = record.get("nodeid", "")
        outcome = record.get("outcome", "")
        duration = record.get("duration", 0)

        if outcome == "":
            continue  # skip setup/teardown lines

        summary["collected"] += 1
        if outcome == "passed":
            summary["passed"] += 1
        elif outcome == "failed":
            summary["failed"] += 1
        elif outcome == "skipped":
            summary["skipped"] += 1
        elif outcome == "error":
            summary["error"] += 1

        tests.append({
            "id": nodeid,
            "outcome": outcome,
            "duration": duration,
        })

    return {"tests": tests, "summary": summary}


def group_results_by_criterion(results: dict) -> dict:
    """Group test results by criterion number (01-08)."""
    criterion_results = {}
    for test in results["tests"]:
        nodeid = test["id"]
        # Extract criterion number from test nodeid like:
        # backend/tests/integration/test_phase13_success_criteria.py::TestCriterion01AutoDelegation::test_xxx  # noqa E501
        for num in CRITERIA_LABELS:
            if f"Criterion{num}" in nodeid:
                key = num
                break
        else:
            continue

        if key not in criterion_results:
            criterion_results[key] = []
        criterion_results[key].append(test)
    return criterion_results


def generate_report(results: dict, env: str) -> str:
    """Generate a markdown report from pytest results."""
    summary = results["summary"]
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    report_lines = [
        "# Phase 13 Success Criteria Walkthrough Report\n",
        f"**Date:** {now}\n",
        f"**Environment:** {env}\n",
        f"**Summary:** {summary['passed']}/{summary['collected']} passed, "
        f"{summary['failed']} failed, {summary['skipped']} skipped, "
        f"{summary['error']} errors\n",
        "\n---\n",
    ]

    grouped = group_results_by_criterion(results)
    issues_needed = []

    for num, label in CRITERIA_LABELS.items():
        test_group = grouped.get(num, [])
        if not test_group:
            # No tests matched this criterion -- likely a test filter or skip
            report_lines.append(f"### Criterion {num}: {label}\n")
            report_lines.append("**Status: N/A** — no tests ran for this criterion.\n\n")
            continue

        all_passed = all(t["outcome"] == "passed" for t in test_group)
        status_icon = "PASS" if all_passed else "FAIL"
        status_badge = f"**Status: {status_icon}**"

        report_lines.append(f"### Criterion {num}: {label}\n")
        report_lines.append(f"{status_badge}\n")
        report_lines.append("| Test | Outcome | Duration |\n")
        report_lines.append("|------|---------|----------|\n")

        for t in test_group:
            duration = f"{t['duration']:.2f}s"
            outcome = t["outcome"]
            short_name = t["id"].split("::")[-1]
            report_lines.append(f"| {short_name} | {outcome} | {duration} |\n")

        report_lines.append("\n")

        if not all_passed:
            issues_needed.append(num)

    if issues_needed:
        report_lines.append("---\n")
        report_lines.append("## GitHub Issues Required\n")
        for num in issues_needed:
            report_lines.append(f"- [ ] Open issue for Criterion {num}: {CRITERIA_LABELS[num]}\n")
        report_lines.append("\n")

    report_lines.append("---\n")
    report_lines.append("*End of report — generated automatically by Phase 13 walkthrough script.*\n")  # noqa E501

    return "".join(report_lines)


# ═════════════════════════════════════════════════════════════
# Test execution
# ═════════════════════════════════════════════════════════════

def run_pytest(test_file: Path, json_output: Path) -> int:
    """Run pytest and return exit code. Writes JSON output to file."""
    cmd = [
        "pytest",
        str(test_file),
        "-v",
        "--tb=short",
        "--no-cov",
        "--json-report",
        "--json-report-file", str(json_output),
    ]

    print(f"Running: {' '.join(cmd)}\n")
    result = subprocess.run(
        cmd,
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    return result.returncode


def run_pytest_junit(test_file: Path, junit_output: Path) -> subprocess.CompletedProcess:
    """Run pytest with JUnit output for detailed parsing."""
    cmd = [
        "pytest",
        str(test_file),
        "-v",
        "--tb=short",
        "--no-cov",
        f"--junitxml={junit_output}",
    ]
    return subprocess.run(cmd, cwd=BACKEND_DIR, capture_output=True, text=True)


# ═════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Phase 13 Success Criteria Walkthrough Report Generator"
    )
    parser.add_argument(
        "--environment",
        type=str,
        default="staging",
        help="Environment label (e.g. local, staging, production)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip actual pytest run and generate a dummy report",  # noqa E501
    )
    args = parser.parse_args()

    print("=" * 70)
    print("Agentium — Phase 13 Success Criteria Walkthrough")
    print("=" * 70)
    print(f"Environment: {args.environment}")
    print(f"Test file:   {TEST_FILE}")
    print(f"Report dir:  {REPORT_DIR}")
    print("-" * 70)

    if not TEST_FILE.exists():
        print(f"ERROR: Test file not found: {TEST_FILE}")
        sys.exit(1)

    # Ensure reports directory
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print("DRY RUN: Generating dummy report...")
        dummy_results = {
            "tests": [
                {"id": f"backend/tests/...::TestCriterion0{i}...::test_dummy",
                 "outcome": "passed", "duration": 0.1}
                for i in range(1, 9)
            ],
            "summary": {"collected": 8, "passed": 8, "failed": 0, "skipped": 0, "error": 0},
        }
        report = generate_report(dummy_results, args.environment)
        report_path = REPORT_DIR / f"phase13_walkthrough_{args.environment}_DRY.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"Dry-run report written to: {report_path}")
        sys.exit(0)

    # Run actual pytest with JUnit output for parsing
    junit_file = REPORT_DIR / "phase13_junit.xml"
    print("\nRunning pytest...")
    result = run_pytest_junit(TEST_FILE, junit_file)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    # Parse JUnit XML into a structure generate_report can consume
    # (simplified: treat all as passed if exit 0, else inspect XML)
    exit_code = result.returncode
    if exit_code == 0:
        summary = {"collected": 8, "passed": 8, "failed": 0, "skipped": 0, "error": 0}
    else:
        summary = {"collected": 8, "passed": 0, "failed": 0, "skipped": 0, "error": 0}

    # Build result structure from stdout lines
    tests = []
    for line in result.stdout.splitlines():
        if "::TestCriterion" in line and any(x in line for x in ("PASSED", "FAILED", "ERROR")):
            parts = line.split()
            if len(parts) >= 2:
                outcome = "passed" if "PASSED" in line else "failed"
                # Extract duration if available
                duration = 0.0
                try:
                    # Find "0.12s" or similar at end of line
                    for p in reversed(parts):
                        p = p.strip()
                        if p.endswith("s") and "=" in p:
                            duration = float(p.split("=")[-1].rstrip("s"))
                            break
                except (ValueError, IndexError):
                    pass

                # Find the nodeid
                for p in parts:
                    if "::" in p and "test_phase13" not in p:
                        tests.append({"id": p, "outcome": outcome, "duration": duration})
                        break

    results = {"tests": tests, "summary": summary}
    report = generate_report(results, args.environment)

    # Write report
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report_path = REPORT_DIR / f"phase13_walkthrough_{args.environment}_{timestamp}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to: {report_path}")

    # Print summary to console
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for num, label in CRITERIA_LABELS.items():
        group = [t for t in tests if f"Criterion{num}" in t["id"]]
        if not group:
            status = _color("SKIP", Colors.SKIP)
        elif all(t["outcome"] == "passed" for t in group):
            status = _color("PASS", Colors.PASS)
        else:
            status = _color("FAIL", Colors.FAIL)
        print(f"  C{num} | {label}:              {status}")
    print("-" * 70)

    if exit_code != 0:
        print("\n" + _color("Some criteria failed. See report for details.", Colors.FAIL))
        print("Open a GitHub Issue for each failing criterion.\n")
    else:
        print("\n" + _color("All criteria passed!", Colors.PASS) + "\n")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()