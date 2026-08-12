from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Literal
from sqlalchemy.orm import Session


@dataclass
class UncertaintySignal:
    reason: str
    affected_tools: List[str]
    details: Dict[str, Any]
    suggested_question: str
    severity: Literal["low", "medium", "high"]


class UncertaintyDetector:
    """Detects uncertainty signals in tool execution results."""

    # Expected result keys per tool (populated from registry at runtime)
    TOOL_EXPECTED_KEYS: Dict[str, List[str]] = {
        "read_file": ["content"],
        "write_file": ["path", "written"],
        "execute_command": ["stdout", "stderr", "exit_code"],
        "browser_control": ["content", "url"],
        "nodriver_navigate": ["html", "url"],
        "deep_think_tool": ["reasoning", "conclusion"],
    }

    @staticmethod
    def analyze(
        tool_results: List[Dict[str, Any]],
        agent: Any,  # Agent type
        db: Session,
    ) -> Optional[UncertaintySignal]:
        """
        Analyze tool results for uncertainty.

        Returns UncertaintySignal if uncertain, None if all results are clear.
        """
        if not tool_results:
            return None

        # Check if all tools failed (batch-level check for multi-tool batches)
        if len(tool_results) > 1 and all(r.get("status") != "success" for r in tool_results):
            return UncertaintySignal(
                reason="all_tools_failed",
                affected_tools=[r.get("tool_name", "unknown") for r in tool_results],
                details={"errors": [r.get("error") for r in tool_results if r.get("error")]},
                suggested_question=(
                    f"All {len(tool_results)} tools I called failed. "
                    f"The errors were: {[r.get('error') for r in tool_results if r.get('error')]}. "
                    "How should I proceed with this task?"
                ),
                severity="high"
            )

        # Check each result for uncertainty triggers
        for result in tool_results:
            signal = UncertaintyDetector._check_single_result(result)
            if signal:
                return signal

        # Check for conflicting results across tools
        conflict_signal = UncertaintyDetector._check_conflicts(tool_results)
        if conflict_signal:
            return conflict_signal

        return None

    @staticmethod
    def _check_single_result(result: Dict[str, Any]) -> Optional[UncertaintySignal]:
        """Check a single tool result for uncertainty triggers."""
        status = result.get("status")
        tool_name = result.get("tool_name", "unknown")

        # Tool error/timeout/cancelled
        if status in ("error", "timeout", "cancelled"):
            error = result.get("error", "Unknown error")
            return UncertaintySignal(
                reason="tool_error",
                affected_tools=[tool_name],
                details={"status": status, "error": error},
                suggested_question=(
                    f"My execution tool '{tool_name}' returned an error: {error}. "
                    "As my supervisor, what should I do next?"
                ),
                severity="high"
            )

        # Tool succeeded but empty result
        if status == "success":
            result_data = result.get("result")
            if result_data is None or result_data == {}:
                return UncertaintySignal(
                    reason="empty_result",
                    affected_tools=[tool_name],
                    details={"status": status, "result": result_data},
                    suggested_question=(
                        f"Tool '{tool_name}' completed successfully but returned no data (empty result). "
                        "Is this expected for this operation, or should I try a different approach?"
                    ),
                    severity="medium"
                )

            # Missing expected fields
            expected_keys = UncertaintyDetector.TOOL_EXPECTED_KEYS.get(tool_name, [])
            if expected_keys:
                missing = [k for k in expected_keys if k not in result_data]
                if missing:
                    return UncertaintySignal(
                        reason="missing_expected_fields",
                        affected_tools=[tool_name],
                        details={"missing_fields": missing, "result_keys": list(result_data.keys())},
                        suggested_question=(
                            f"Tool '{tool_name}' returned a result but is missing expected fields: {missing}. "
                            "What do these fields represent and how should I obtain them?"
                        ),
                        severity="medium"
                    )

        return None

    @staticmethod
    def _check_conflicts(tool_results: List[Dict[str, Any]]) -> Optional[UncertaintySignal]:
        """Check for conflicting values across tool results."""
        # Build map of key -> (tool_name, value)
        key_map: Dict[str, List[tuple]] = {}
        for result in tool_results:
            if result.get("status") == "success":
                result_data = result.get("result", {})
                tool_name = result.get("tool_name", "unknown")
                for key, value in result_data.items():
                    if key not in key_map:
                        key_map[key] = []
                    key_map[key].append((tool_name, value))

        # Find keys with conflicting values
        for key, entries in key_map.items():
            if len(entries) > 1:
                values = [v for _, v in entries]
                if len(set(str(v) for v in values)) > 1:
                    tool_names = [t for t, _ in entries]
                    return UncertaintySignal(
                        reason="conflicting_results",
                        affected_tools=tool_names,
                        details={
                            "key": key,
                            "values": {t: str(v) for t, v in entries}
                        },
                        suggested_question=(
                            f"Tools {', '.join(tool_names)} returned conflicting values for '{key}': "
                            f"{', '.join(f'{t}={v}' for t, v in entries)}. "
                            "Which source should I trust?"
                        ),
                        severity="low"
                    )
        return None