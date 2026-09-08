#!/usr/bin/env python
"""
Quick verification runner for all tools in Section 8.2.
Run with: python tools/verify_tools.py
"""
import sys
import subprocess
import os
from pathlib import Path


def run_pytest_test(test_file: str, verbose: bool = False) -> tuple[bool, str]:
    """Run a single pytest test file and return (success, output)."""
    cmd = [
        sys.executable, "-m", "pytest",
        test_file,
        "-v" if verbose else "-q",
        "--no-cov",
        "--tb=short"
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=Path(__file__).parent.parent
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


def main():
    # Test files for the 13 previously untested tools
    test_files = [
        "tests/unit/test_web_search_tool.py",
        "tests/unit/test_text_editor_tool.py",
        "tests/unit/test_browser_tool.py",
        "tests/unit/test_nodriver_tool.py",
        "tests/unit/test_deep_think_tool.py",
        "tests/unit/test_code_analyzer_tool.py",
        "tests/unit/test_data_transform_tool.py",
        "tests/unit/test_embedding_tool.py",
        "tests/unit/test_http_api_tool.py",
        "tests/unit/test_desktop_tool.py",
        "tests/unit/test_host_os_tool.py",
        "tests/unit/test_skill_creator_tool.py",
        "tests/unit/test_user_preference_tool.py",
        "tests/unit/test_mcp_agent_tools.py",
    ]

    # Also run existing tests to make sure nothing broke
    existing_test_files = [
        "tests/unit/test_web_fetch_tool.py",
        "tests/unit/test_web_crawler_tool.py",
        "tests/unit/test_file_system_tool.py",
        "tests/unit/test_code_execution_tool.py",
        "tests/unit/test_git_tool_tiers.py",
        "tests/unit/test_vector_db_tool.py",
        "tests/unit/test_task_management_tool.py",
        "tests/unit/test_tool_search_tool.py",
        "tests/unit/test_clarification_tool.py",
        "tests/unit/test_remote_exec_tool.py",
        "tests/unit/test_tool_creator_tool.py",
        "tests/integration/test_ethos_tool_unit.py",
        "tests/integration/test_governance_tools_e2e.py",
    ]

    all_files = test_files + existing_test_files

    print("=" * 70)
    print("Agentium Tool Verification - Section 8.2")
    print("=" * 70)
    print(f"Testing {len(test_files)} new test files + {len(existing_test_files)} existing")
    print()

    results = []
    passed = 0
    failed = 0

    for test_file in all_files:
        full_path = Path(__file__).parent.parent / test_file
        if not full_path.exists():
            print(f"  SKIP: {test_file} (not found)")
            results.append((test_file, False, "File not found"))
            failed += 1
            continue

        print(f"  Running: {test_file} ... ", end="", flush=True)
        success, output = run_pytest_test(test_file)

        if success:
            print("PASS")
            passed += 1
        else:
            print("FAIL")
            failed += 1
            # Print last few lines of output for debugging
            lines = output.strip().split('\n')
            for line in lines[-5:]:
                print(f"    {line}")

        results.append((test_file, success, output))

    print()
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {len(all_files)} test files")
    print("=" * 70)

    # Summary by tool
    print("\nTool Verification Status:")
    print("-" * 70)

    tool_map = {
        "web_search_tool": "test_web_search_tool.py",
        "web_fetch_tool": "test_web_fetch_tool.py",
        "web_crawler_tool": "test_web_crawler_tool.py",
        "file_tool": "test_file_system_tool.py",
        "text_editor_tool": "test_text_editor_tool.py",
        "code_execution_tool": "test_code_execution_tool.py",
        "git_tool": "test_git_tool_tiers.py",
        "browser_tool": "test_browser_tool.py",
        "nodriver_tool": "test_nodriver_tool.py",
        "deep_think_tool": "test_deep_think_tool.py",
        "code_analyzer_tool": "test_code_analyzer_tool.py",
        "data_transform_tool": "test_data_transform_tool.py",
        "embedding_tool": "test_embedding_tool.py",
        "vector_db_tool": "test_vector_db_tool.py",
        "http_api_tool": "test_http_api_tool.py",
        "desktop_tool": "test_desktop_tool.py",
        "host_os_tool": "test_host_os_tool.py",
        "task_management_tool": "test_task_management_tool.py",
        "tool_search_tool": "test_tool_search_tool.py",
        "skill_creator_tool": "test_skill_creator_tool.py",
        "tool_creator_tool": "test_tool_creator_tool.py",
        "clarification_tool": "test_clarification_tool.py",
        "user_preference_tool": "test_user_preference_tool.py",
        "governance_tool": "test_governance_tools_e2e.py",
        "ethos_tool": "test_ethos_tool_unit.py",
        "remote_exec_tool": "test_remote_exec_tool.py",
        "mcp_agent_tools": "test_mcp_agent_tools.py",
    }

    for tool, test_file in tool_map.items():
        full_path = Path(__file__).parent.parent / test_file
        status = "NOT TESTED"
        if full_path.exists():
            result = next((r for r in results if r[0] == test_file), None)
            if result:
                status = "PASS" if result[1] else "FAIL"
            else:
                status = "NOT RUN"
        print(f"  {tool:30s} : {status}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())