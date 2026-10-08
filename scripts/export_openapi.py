"""Export the backend's OpenAPI spec without running a server.

Imports backend.main:app and dumps app.openapi() to sdk/typescript/openapi.json.
Safe to run without docker services: SQLAlchemy engines and redis-py clients
connect lazily, so importing the app does not touch the network.

Usage (from repo root):
    python scripts/export_openapi.py
"""

import json
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Mirror the env vars CI sets for the backend (sdk-smoke-tests.yml) so import
# never fails on a missing setting. setdefault: real values win if present.
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "postgresql://agentium:agentium@localhost:5432/agentium_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")


def main() -> None:
    from backend.main import app

    spec = app.openapi()
    out_path = REPO_ROOT / "sdk" / "typescript" / "openapi.json"
    # No sort_keys: key order must match the live server's /openapi.json
    # (dict insertion order), since openapi-typescript preserves input order
    # and CI diffs its output byte-exactly against the committed file.
    out_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
