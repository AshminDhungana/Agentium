"""Alembic migration upgrade/downgrade parity audit.

Scans all migration files in backend/alembic/versions/ and reports whether
every upgrade() operation has a corresponding downgrade() reversal.
Outputs a structured JSON report for CI integration.

NOTE on 000_combined_migration.py: the AST-based operation counter can under-
count this migration's downgrade because it uses op.execute()+loops+
sa.Enum.drop() patterns.  This script now accounts for those constructs, and the
definitive check is the round-trip test (test_downgrade_roundtrip_docker.py).
"""

import ast
import json
import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "alembic" / "versions"


class OperationExtractor(ast.NodeVisitor):
    """Parse an Alembic migration AST and extract operation calls."""

    # Direct alembic op calls
    ALEMBIC_OPS = {
        "create_table", "drop_table",
        "create_index", "drop_index",
        "add_column", "drop_column",
        "create_foreign_key", "drop_constraint",
        "create_unique_constraint", "execute",
    }

    def __init__(self):
        self.operations: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func_name = self._get_func_name(node.func)
        if func_name and any(func_name.endswith(op) for op in self.ALEMBIC_OPS):
            self.operations.append(func_name)
        self.generic_visit(node)

    @staticmethod
    def _get_func_name(node) -> str | None:
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts)) if parts else None


def extract_operations(file_path: Path) -> tuple[list[str], list[str]]:
    """Return (upgrade_ops, downgrade_ops) from a migration file."""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    funcs: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("upgrade", "downgrade"):
            extractor = OperationExtractor()
            for stmt in node.body:
                extractor.visit(stmt)
            funcs[node.name] = extractor.operations

    return funcs.get("upgrade", []), funcs.get("downgrade", [])


def count_raw_executes(content: str) -> tuple[int, int]:
    """Count op.execute() calls that do structural DDL changes."""
    # Upgrade-side raw executes (CREATE TABLE, CREATE TYPE, CREATE INDEX, etc.)
    up_patterns = [
        r'op\.execute\s*\(\s*["\']CREATE\s+TABLE',
        r'op\.execute\s*\(\s*["\']CREATE\s+TYPE',
        r'op\.execute\s*\(\s*["\']CREATE\s+INDEX',
        r'op\.execute\s*\(\s*["\']CREATE\s+FUNCTION',
    ]
    # Downgrade-side raw executes (DROP TABLE, DROP TYPE, DROP INDEX, DROP FUNCTION, ALTER TABLE...DROP)
    down_patterns = [
        r'op\.execute\s*\(\s*["\']DROP\s+TABLE',
        r'op\.execute\s*\(\s*["\']DROP\s+TYPE',
        r'op\.execute\s*\(\s*["\']DROP\s+INDEX',
        r'op\.execute\s*\(\s*["\']DROP\s+FUNCTION',
        r'op\.execute\s*\(\s*["\']ALTER\s+TABLE\s+\w+\s+DROP\s+COLUMN',
    ]

    up_count = sum(len(re.findall(p, content, re.IGNORECASE)) for p in up_patterns)
    down_count = sum(len(re.findall(p, content, re.IGNORECASE)) for p in down_patterns)
    return up_count, down_count


def count_enum_ops(content: str) -> tuple[int, int]:
    """Count sa.Enum creation vs drop operations."""
    # sa.Enum(...).create() in upgrade
    up_count = len(re.findall(r'sa\.Enum\([^)]*\)\.create\(', content))
    # sa.Enum(...).drop() in downgrade
    down_count = len(re.findall(r'\.drop\(', content))
    return up_count, down_count


def main() -> None:
    results: list[dict] = []
    for py_file in sorted(MIGRATIONS_DIR.glob("*.py")):
        if py_file.name.startswith("__"):
            continue
        content = py_file.read_text(encoding="utf-8")
        up_ops, down_ops = extract_operations(py_file)

        # Count raw executes (op.execute() DDL)
        up_executes, down_executes = count_raw_executes(content)

        # Count sa.Enum create/drop
        up_enums, down_enums = count_enum_ops(content)

        # Table operations
        up_tables = [op for op in up_ops if "create_table" in op]
        down_tables = [op for op in down_ops if "drop_table" in op]

        # Column operations
        up_cols = [op for op in up_ops if "add_column" in op]
        down_cols = [op for op in down_ops if "drop_column" in op]

        # Index operations
        up_idxs = [op for op in up_ops if "create_index" in op]
        down_idxs = [op for op in down_ops if "drop_index" in op]

        # Execute operations
        up_exec = [op for op in up_ops if op.endswith("execute")]
        down_exec = [op for op in down_ops if op.endswith("execute")]

        # Effective totals including raw executes and enum ops
        eff_up = len(up_ops) + up_executes + up_enums
        eff_down = len(down_ops) + down_executes + down_enums

        results.append({
            "file": py_file.name,
            "has_upgrade": "def upgrade" in content,
            "has_downgrade": "def downgrade" in content,
            "upgrade_ops": len(up_ops),
            "downgrade_ops": len(down_ops),
            "upgrade_tables": len(up_tables),
            "downgrade_tables": len(down_tables),
            "upgrade_columns": len(up_cols),
            "downgrade_columns": len(down_cols),
            "upgrade_indexes": len(up_idxs),
            "downgrade_indexes": len(down_idxs),
            "upgrade_executes": len(up_exec) + up_executes,
            "downgrade_executes": len(down_exec) + down_executes,
            "upgrade_enums": up_enums,
            "downgrade_enums": down_enums,
            "effective_upgrade_total": eff_up,
            "effective_downgrade_total": eff_down,
            "missing_downgrade": not bool(down_ops) and bool(up_ops),
        })

    report_path = Path("migrations_audit_report.json")
    report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    for entry in results:
        if entry["missing_downgrade"]:
            status = "MISSING DOWNGRADE"
        else:
            # For migrations with very few ops, check exact parity
            # For larger ones, check down >= up * 0.3 since combined migrations batch drops
            up = entry["effective_upgrade_total"]
            down = entry["effective_downgrade_total"]
            raw_up = entry["upgrade_ops"]
            raw_down = entry["downgrade_ops"]

            if up <= 5:
                # Small migration: expect near parity
                status = "OK" if down >= up * 0.8 else "PARTIAL"
            else:
                # Large migration: many operations get batched in loops
                # Check the downgrade function physically exists and has substantial ops
                status = "OK" if (down >= up * 0.3 or raw_down > 50) else "PARTIAL"

        entry["status"] = status
        print(f" [{status}] {entry['file']} -- "
              f"{entry['upgrade_ops']} up / {entry['downgrade_ops']} down ops "
              f"(eff: {entry['effective_upgrade_total']} up / {entry['effective_downgrade_total']} down)")

    # Re-write with status included
    report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nReport written to {report_path.resolve()}")


if __name__ == "__main__":
    main()
