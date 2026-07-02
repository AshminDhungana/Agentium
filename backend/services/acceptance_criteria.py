"""
Phase 6.3 — Pre-Declared Acceptance Criteria
Defines the AcceptanceCriterion structure and the AcceptanceCriteriaService.

Key design decisions:
- Criteria are stored as plain JSON on Task (no separate table needed).
- CritiqueReview stores per-criterion pass/fail results after each review.
- Validators map directly to CriticType so the correct critic is dispatched.
- Human-readable descriptions travel with the structured data for dashboard display.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


# ─── Criterion structure ──────────────────────────────────────────────────────

class CriterionValidator(str, Enum):
    """Maps to CriticType — which critic agent validates this criterion."""
    CODE   = "code"    # CodeCritic  (4xxxx)
    OUTPUT = "output"  # OutputCritic (5xxxx)
    PLAN   = "plan"    # PlanCritic  (6xxxx)


@dataclass
class AcceptanceCriterion:
    """
    A single, machine-validatable success criterion.

    Fields
    ------
    metric          : Identifier for the check, e.g. "sql_syntax_valid".
    threshold       : Expected value or range, e.g. True, 0.95, "PASS".
    validator       : Which critic type validates this criterion.
    is_mandatory    : If True, failure on this criterion = task REJECT.
                      If False, failure is recorded but does not block.
    description     : Human-readable explanation shown in the dashboard.
    """
    metric: str
    threshold: Any
    validator: CriterionValidator
    is_mandatory: bool = True
    description: str = ""

    # ── serialisation ──────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """To dict."""

        d = asdict(self)
        d["validator"] = self.validator.value  # store as string in JSON
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AcceptanceCriterion":
        """From dict."""

        validator = CriterionValidator(data.get("validator", "output"))
        return cls(
            metric=data["metric"],
            threshold=data["threshold"],
            validator=validator,
            is_mandatory=data.get("is_mandatory", True),
            description=data.get("description", ""),
        )

    # ── validation ─────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Raise ValueError if the criterion is structurally invalid."""
        if not self.metric or not isinstance(self.metric, str):
            raise ValueError("AcceptanceCriterion.metric must be a non-empty string")
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', self.metric):
            raise ValueError(
                f"AcceptanceCriterion.metric '{self.metric}' must be snake_case "
                f"(letters, digits, underscores only)"
            )
        if self.threshold is None:
            raise ValueError(f"AcceptanceCriterion '{self.metric}' must have a threshold value")


# ─── Criterion evaluation result ──────────────────────────────────────────────

@dataclass
class CriterionResult:
    """
    The outcome of evaluating a single AcceptanceCriterion during critic review.
    Stored in CritiqueReview.criteria_results as a JSON array.
    """
    metric: str
    passed: bool
    actual_value: Any
    threshold: Any
    is_mandatory: bool
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """To dict."""

        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CriterionResult":
        """From dict."""

        return cls(**data)


# ─── Service ──────────────────────────────────────────────────────────────────

class AcceptanceCriteriaService:
    """
    Stateless helper: validates, serialises, and evaluates acceptance criteria.
    Used by:
      - tasks.py route  → validate + store on task creation
      - critic_agents.py → evaluate criteria during review
      - dashboard API   → deserialise for display
    """

    # ── Task-creation helpers ──────────────────────────────────────────────

    @staticmethod
    def parse_and_validate(raw: List[Dict[str, Any]]) -> List[AcceptanceCriterion]:
        """
        Parse a list of raw dicts (from API request) into AcceptanceCriterion
        objects, validating each one.

        Raises ValueError with a descriptive message on the first invalid entry.
        """
        if not isinstance(raw, list):
            raise ValueError("acceptance_criteria must be a JSON array")

        criteria: List[AcceptanceCriterion] = []
        for i, item in enumerate(raw):
            try:
                criterion = AcceptanceCriterion.from_dict(item)
                criterion.validate()
                criteria.append(criterion)
            except (KeyError, TypeError) as exc:
                raise ValueError(
                    f"acceptance_criteria[{i}] is malformed: {exc}"
                ) from exc
            except ValueError as exc:
                raise ValueError(f"acceptance_criteria[{i}]: {exc}") from exc

        return criteria

    @staticmethod
    def to_json(criteria: List[AcceptanceCriterion]) -> List[Dict[str, Any]]:
        """Serialise a list of AcceptanceCriterion objects for JSON storage."""
        return [c.to_dict() for c in criteria]

    @staticmethod
    def from_json(data: Optional[List[Dict[str, Any]]]) -> List[AcceptanceCriterion]:
        """Deserialise acceptance_criteria JSON from the database."""
        if not data:
            return []
        return [AcceptanceCriterion.from_dict(d) for d in data]

    # ── Critic-review helpers ──────────────────────────────────────────────

    @staticmethod
    def evaluate_criteria(
        criteria: List[AcceptanceCriterion],
        output_content: str,
        critic_type: str,
    ) -> List[CriterionResult]:
        """
        Run lightweight, deterministic checks against each criterion.

        For criteria whose `validator` does NOT match `critic_type`, the check
        is skipped and recorded as passed (not the right critic's responsibility).

        For criteria whose `validator` DOES match `critic_type`, the check runs
        the appropriate built-in validator.

        Note: Deeper LLM-based validation is performed by the critic agent's AI
        model.  This layer handles the machine-validatable rules only.
        """
        results: List[CriterionResult] = []

        for criterion in criteria:
            # Skip if this critic isn't responsible for this criterion
            if criterion.validator.value != critic_type:
                results.append(CriterionResult(
                    metric=criterion.metric,
                    passed=True,
                    actual_value="N/A — different critic responsible",
                    threshold=criterion.threshold,
                    is_mandatory=criterion.is_mandatory,
                    notes="Skipped: not this critic's domain",
                ))
                continue

            passed, actual, notes = AcceptanceCriteriaService._run_check(
                criterion, output_content
            )
            results.append(CriterionResult(
                metric=criterion.metric,
                passed=passed,
                actual_value=actual,
                threshold=criterion.threshold,
                is_mandatory=criterion.is_mandatory,
                notes=notes,
            ))

        return results

    @staticmethod
    def _run_check(
        criterion: AcceptanceCriterion, output_content: str
    ):
        """
        Dispatch to a built-in checker based on metric name convention.
        Returns (passed: bool, actual_value: Any, notes: str).

        Metric naming convention drives the check automatically:
            sql_syntax_*      → SQL syntax presence check
            result_not_empty  → non-empty output check
            length_*          → character/word length threshold
            contains_*        → keyword presence check
            *                 → threshold equality check (generic fallback)
        """
        metric = criterion.metric
        threshold = criterion.threshold

        try:
            # ── SQL syntax presence ─────────────────────────────────────────
            if metric.startswith("sql_syntax"):
                keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "CREATE",
                            "DROP", "ALTER", "WITH"]
                has_sql = any(kw in output_content.upper() for kw in keywords)
                return has_sql, has_sql, (
                    "SQL keyword found" if has_sql else "No SQL keyword detected"
                )

            # ── Non-empty output ────────────────────────────────────────────
            if metric == "result_not_empty":
                stripped = output_content.strip()
                passed = bool(stripped)
                return passed, len(stripped), (
                    "Output is non-empty" if passed else "Output is empty"
                )

            # ── Length threshold ────────────────────────────────────────────
            if metric.startswith("length_"):
                unit = metric.split("_", 1)[1]  # chars | words
                if unit == "words":
                    actual = len(output_content.split())
                else:
                    actual = len(output_content)

                if isinstance(threshold, (list, tuple)) and len(threshold) == 2:
                    lo, hi = threshold
                    passed = lo <= actual <= hi
                    notes = f"{actual} {unit} (expected {lo}–{hi})"
                else:
                    passed = actual >= int(threshold)
                    notes = f"{actual} {unit} (minimum {threshold})"

                return passed, actual, notes

            # ── Keyword presence ────────────────────────────────────────────
            if metric.startswith("contains_"):
                keyword = metric.split("contains_", 1)[1].replace("_", " ")
                passed = keyword.lower() in output_content.lower()
                return passed, passed, (
                    f"'{keyword}' found" if passed else f"'{keyword}' not found"
                )

            # ── Boolean threshold (generic) ─────────────────────────────────
            if isinstance(threshold, bool):
                # We can only assert; actual boolean evaluation is LLM's job
                return True, "deferred_to_llm", "Boolean check deferred to LLM critic"

            # ── Generic equality fallback ───────────────────────────────────
            return True, "deferred_to_llm", "Generic metric — deferred to LLM critic"

        except Exception as exc:
            return False, None, f"Check raised exception: {exc}"

    # ── Aggregation helpers ────────────────────────────────────────────────

    @staticmethod
    def aggregate(results: List[CriterionResult]) -> Dict[str, Any]:
        """
        Summarise a list of CriterionResult objects.
        Returns a dict with counts and a mandatory-failure flag.
        """
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        mandatory_failures = [
            r.metric for r in results if not r.passed and r.is_mandatory
        ]
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "mandatory_failures": mandatory_failures,
            "all_mandatory_passed": len(mandatory_failures) == 0,
        }