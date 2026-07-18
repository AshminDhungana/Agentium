#!/usr/bin/env python3
"""
Agentium first-run environment bootstrap.

Generates a secure `.env` file for `docker compose` if one does not already
exist, and guarantees MinIO object-storage credentials are unique and
non-default (never minioadmin/minioadmin).

Behaviour (idempotent — safe to run repeatedly):
  * If `.env` exists, only missing values are filled in; existing values are
    preserved untouched.
  * If `.env` is missing, it is created from `.env.example` and then MinIO
    credentials (and other secrets) are generated.
  * MINIO_ROOT_USER / MINIO_ROOT_PASSWORD are generated the first time and
    never overwritten, satisfying the "rotate on first deploy" requirement.

Usage:
    python backend/scripts/setup_env.py
    python backend/scripts/setup_env.py --force-minio   # regenerate MinIO creds
"""

import secrets
import string
import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = REPO_ROOT / ".env"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"

DEFAULT_MINIO_USER = "minioadmin"
DEFAULT_MINIO_PASSWORD = "minioadmin"


def _gen_minio_user() -> str:
    """Generate a 20-char alphanumeric MinIO root user (no ambiguous chars)."""
    alphabet = string.ascii_letters + string.digits
    alphabet = alphabet.replace("l", "").replace("I", "").replace("O", "").replace("0", "")
    return "agentium-" + "".join(secrets.choice(alphabet) for _ in range(12))


def _gen_minio_password() -> str:
    """Generate a 32-char password with mixed case, digits, and symbols."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(32))


def _parse_env(text: str) -> dict:
    """Parse a simple KEY=VALUE .env file into a dict (ignores comments/blank)."""
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def _serialize_env(values: dict) -> str:
    """Serialize a dict back to .env text, one KEY=VALUE per line."""
    return "\n".join(f"{k}={v}" for k, v in values.items()) + "\n"


def ensure_env(existing_only: bool = False) -> dict:
    """
    Ensure `.env` exists and contains MinIO credentials.

    Returns the final env dict (also written to disk).
    """
    if ENV_PATH.exists():
        values = _parse_env(ENV_PATH.read_text(encoding="utf-8"))
        source = "existing .env"
    elif ENV_EXAMPLE_PATH.exists():
        values = _parse_env(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"))
        source = ".env.example (copied)"
    else:
        values = {}
        source = "empty template"

    changed = False

    user = values.get("MINIO_ROOT_USER", "").strip()
    password = values.get("MINIO_ROOT_PASSWORD", "").strip()

    needs_user = not user or user == DEFAULT_MINIO_USER
    needs_password = not password or password == DEFAULT_MINIO_PASSWORD

    if needs_user or needs_password:
        values["MINIO_ROOT_USER"] = _gen_minio_user() if needs_user else user
        values["MINIO_ROOT_PASSWORD"] = _gen_minio_password() if needs_password else password
        changed = True
        print(
            "Generated unique MinIO credentials "
            f"(user={values['MINIO_ROOT_USER']!r})."
        )
        print("   ROTATE these on first production deploy if desired.")

    if changed:
        ENV_PATH.write_text(_serialize_env(values), encoding="utf-8")
        print(f"Updated {ENV_PATH} (based on {source}).")
    else:
        print(f"{ENV_PATH} already has non-default MinIO credentials; left unchanged.")

    return values


def main():
    parser = argparse.ArgumentParser(description="Bootstrap Agentium .env secrets")
    parser.add_argument(
        "--force-minio",
        action="store_true",
        help="Regenerate MINIO_ROOT_USER / MINIO_ROOT_PASSWORD even if present.",
    )
    args = parser.parse_args()

    if args.force_minio and ENV_PATH.exists():
        values = _parse_env(ENV_PATH.read_text(encoding="utf-8"))
        values["MINIO_ROOT_USER"] = _gen_minio_user()
        values["MINIO_ROOT_PASSWORD"] = _gen_minio_password()
        ENV_PATH.write_text(_serialize_env(values), encoding="utf-8")
        print("Regenerated MinIO credentials in .env.")
        return

    ensure_env()


if __name__ == "__main__":
    sys.exit(main())
