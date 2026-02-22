"""Security validation for code execution.

Multi-layer validation:
  1. Regex pattern matching for dangerous commands
  2. AST analysis for import whitelist enforcement
  3. Python syntax validation
"""
import ast
import re
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class SecurityCheckResult:
    """Result of security validation."""
    passed: bool
    violations: List[str]
    severity: str  # "none", "low", "medium", "high", "critical"
    recommendation: Optional[str] = None


class ExecutionGuard:
    """
    Validates code before execution in remote sandbox.
    Multi-layer security: AST parsing + pattern matching + import whitelist.
    """

    # Dangerous patterns that are always blocked
    DANGEROUS_PATTERNS = [
        r'rm\s+-rf\s+/',
        r'mkfs\.',
        r'dd\s+if=/dev/zero',
        r'shutdown',
        r'reboot',
        r'os\.system\s*\(',
        r'subprocess\.call\s*\(',
        r'subprocess\.run\s*\(',
        r'eval\s*\(',
        r'exec\s*\(',
        r'__import__\s*\(',
        r'importlib\.',
        r'open\s*\([^)]*["\']w',
        r'file\s*\([^)]*["\']w',
    ]

    # Whitelist of allowed imports (stdlib + common data science)
    ALLOWED_IMPORTS = {
        # Standard library
        'json', 're', 'math', 'random', 'datetime', 'collections', 'itertools',
        'functools', 'statistics', 'decimal', 'fractions', 'typing', 'hashlib',
        'base64', 'string', 'time', 'uuid', 'inspect', 'types', 'dataclasses',
        'enum', 'pathlib', 'csv', 'io', 'warnings', 'contextlib', 'copy',
        'numbers', 'operator', 'pprint', 'textwrap', 'bisect', 'heapq',
        # Data processing (safe, read-only)
        'pandas', 'numpy', 'polars', 'pyarrow',
    }

    # Restricted imports require special approval
    RESTRICTED_IMPORTS = {
        'requests': 'Network access requires explicit whitelist',
        'urllib': 'Network access requires explicit whitelist',
        'http': 'Network access requires explicit whitelist',
        'ftplib': 'Network access requires explicit whitelist',
        'smtplib': 'Email sending requires Head approval',
        'sqlite3': 'Database access requires explicit path whitelist',
        'psycopg2': 'Database access requires explicit credentials',
        'pymongo': 'Database access requires explicit credentials',
    }

    def __init__(self):
        self.violations: List[str] = []

    def validate_code(self, code: str, agent_tier: str = "3xxxx") -> SecurityCheckResult:
        """
        Perform multi-layer security validation on code.

        Args:
            code: Python code to validate
            agent_tier: Agent tier (affects permission level)

        Returns:
            SecurityCheckResult with pass/fail and violations
        """
        self.violations = []

        # Layer 1: Pattern matching for dangerous commands
        self._check_dangerous_patterns(code)

        # Layer 2: AST parsing for import analysis
        self._check_imports_ast(code, agent_tier)

        # Layer 3: Syntax validation
        self._check_syntax(code)

        # Determine severity
        severity = self._calculate_severity()

        return SecurityCheckResult(
            passed=len(self.violations) == 0,
            violations=self.violations.copy(),
            severity=severity,
            recommendation=self._generate_recommendation() if self.violations else None
        )

    def _check_dangerous_patterns(self, code: str):
        """Check for dangerous command patterns using regex."""
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                self.violations.append(
                    f"CRITICAL: Dangerous pattern detected: {pattern}"
                )

    def _check_imports_ast(self, code: str, agent_tier: str):
        """Parse AST to check imports."""
        try:
            tree = ast.parse(code)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self._validate_import(alias.name, agent_tier)

                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    self._validate_import(module, agent_tier)

        except SyntaxError:
            # Will be caught in _check_syntax
            pass

    def _validate_import(self, module: str, agent_tier: str):
        """Validate a single import."""
        # Get top-level module name
        top_module = module.split('.')[0]

        # Check if in allowed list
        if top_module in self.ALLOWED_IMPORTS:
            return

        # Check if restricted
        if top_module in self.RESTRICTED_IMPORTS:
            # Head tier can use restricted imports
            if agent_tier.startswith('0'):
                return
            self.violations.append(
                f"RESTRICTED: Import '{top_module}' requires Head approval. "
                f"{self.RESTRICTED_IMPORTS[top_module]}"
            )
            return

        # Unknown import - block by default
        self.violations.append(
            f"UNKNOWN: Import '{top_module}' is not in the allowed list. "
            f"Allowed imports: {', '.join(sorted(self.ALLOWED_IMPORTS)[:10])}..."
        )

    def _check_syntax(self, code: str):
        """Validate Python syntax."""
        try:
            ast.parse(code)
        except SyntaxError as e:
            self.violations.append(f"SYNTAX ERROR: {e}")

    def _calculate_severity(self) -> str:
        """Calculate overall severity based on violations."""
        if not self.violations:
            return "none"

        critical_count = sum(1 for v in self.violations if v.startswith("CRITICAL"))
        restricted_count = sum(1 for v in self.violations if v.startswith("RESTRICTED"))

        if critical_count > 0:
            return "critical"
        elif restricted_count > 0:
            return "high"
        elif len(self.violations) > 3:
            return "medium"
        else:
            return "low"

    def _generate_recommendation(self) -> str:
        """Generate remediation recommendation."""
        recommendations = []

        if any(v.startswith("CRITICAL") for v in self.violations):
            recommendations.append("Remove all dangerous system commands immediately.")

        if any(v.startswith("RESTRICTED") for v in self.violations):
            recommendations.append(
                "Request Head approval for restricted imports, or use alternative libraries."
            )

        if any("SYNTAX" in v for v in self.violations):
            recommendations.append("Fix syntax errors before submission.")

        return " ".join(recommendations) if recommendations else "Review and fix all violations."


# Global guard instance
execution_guard = ExecutionGuard()
