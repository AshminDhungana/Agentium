#!/usr/bin/env python3
"""
Docker Compose Windows Path Convention Verification Script

Verifies that all bind mounts, environment variables, and named volumes
use Windows-compatible path conventions under Docker Desktop.

Usage:
    python scripts/verify-docker-windows-paths.py
    python scripts/verify-docker-windows-paths.py --ci  # Exit code 1 on warnings
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


class VerificationResult:
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"

    def __init__(self, status: str, message: str, file: str, location: str):
        self.status = status
        self.message = message
        self.file = file
        self.location = location

    def __str__(self):
        return f"[{self.status}] {self.file}:{self.location} - {self.message}"


class DockerWindowsPathVerifier:
    """Verifies Windows-compatible path conventions in Docker Compose files."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.results: List[VerificationResult] = []
        self.compose_files = [
            "docker-compose.yml",
            "docker-compose.test.yml",
            "docker-compose.remote-executor.yml",
        ]

    # Patterns that are Windows-compatible
    GOOD_ENV_PATTERNS = [
        r"\$\{USERPROFILE\}",  # Native Windows home
        r"\$\{USERPROFILE:-",  # With fallback
        r"\$\{HOME:-~",       # With fallback (works in Linux VM)
    ]

    # Patterns that need caution
    CAUTION_ENV_PATTERNS = [
        r"\$\{HOME\}(?![:-])",  # Bare HOME without fallback
    ]

    # Patterns that fail - Windows drive letters only (single letter + colon + slash/backslash)
    BAD_ENV_PATTERNS = [
        r"^[A-Za-z]:[\\/]",    # Hardcoded Windows paths like C:\ or C:/ at start
        r"[A-Za-z]:[\\/]",     # Hardcoded Windows paths like C:\ or C:/ anywhere
    ]

    # Bind mount expected absolute paths (Linux VM paths, OK for privileged containers)
    BIND_MOUNT_EXPECTED_ABSOLUTE = [
        r"^/var/run/docker\.sock",
        r"^/proc",
        r"^/sys",
        r"^/dev",
        r"^/:",                     # Root filesystem mount
    ]

    def verify_all(self) -> List[VerificationResult]:
        """Run all verifications on all compose files."""
        for compose_file in self.compose_files:
            file_path = self.project_root / compose_file
            if file_path.exists():
                self._verify_file(file_path)
            else:
                self.results.append(VerificationResult(
                    VerificationResult.WARN,
                    f"Compose file not found: {compose_file}",
                    compose_file,
                    "N/A"
                ))
        return self.results

    def _verify_file(self, file_path: Path):
        """Verify a single docker-compose file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            data = yaml.safe_load(content)
        except Exception as e:
            self.results.append(VerificationResult(
                VerificationResult.FAIL,
                f"Failed to parse YAML: {e}",
                file_path.name,
                "parse"
            ))
            return

        # Verify volumes section
        if 'services' in data:
            for service_name, service_config in data['services'].items():
                if 'volumes' in service_config:
                    self._verify_service_volumes(service_name, service_config['volumes'], file_path.name)
                if 'environment' in service_config:
                    self._verify_service_environment(service_name, service_config['environment'], file_path.name)

        # Verify top-level volumes (named volumes)
        if 'volumes' in data:
            self._verify_named_volumes(data['volumes'], file_path.name)

        # Validate docker compose config interpolation by loading all relevant files
        # docker-compose.remote-executor.yml extends the main compose, so load both
        if file_path.name == "docker-compose.remote-executor.yml":
            compose_files = ["docker-compose.yml", file_path.name]
        else:
            compose_files = [file_path.name]

        self._verify_docker_compose_config(compose_files, file_path.name)

    def _verify_service_volumes(self, service_name: str, volumes: List, file_name: str):
        """Verify bind mounts in a service's volumes section."""
        for i, vol in enumerate(volumes):
            if isinstance(vol, str):
                self._verify_bind_mount_string(service_name, vol, f"volumes[{i}]", file_name)
            elif isinstance(vol, dict):
                # Short syntax with type/bind
                source = vol.get('source', '')
                target = vol.get('target', '')
                if source:
                    self._verify_bind_mount_string(service_name, f"{source}:{target}", f"volumes[{i}] (dict)", file_name)

    def _verify_bind_mount_string(self, service_name: str, vol_str: str, location: str, file_name: str):
        """Verify a single bind mount string."""
        # Parse "source:target[:mode]" format - handle ${VAR:-value} with colons
        # Use a more careful parsing that accounts for ${...} containing colons
        source, target = self._parse_bind_mount(vol_str)
        if source is None:
            self.results.append(VerificationResult(
                VerificationResult.FAIL,
                f"Invalid bind mount format: {vol_str}",
                file_name,
                f"{service_name}.{location}"
            ))
            return

        # Check if it's a bind mount (not a named volume)
        # Bind mounts start with ./ or / or ${ or ~
        is_named_volume = not (source.startswith('./') or source.startswith('/') or source.startswith('${') or source.startswith('~'))

        if is_named_volume:
            # Named volume - just verify naming convention
            self._verify_named_volume_name(source, file_name, f"{service_name}.{location}")
            return

        # Check for Windows-compatible patterns
        status, message = self._check_bind_mount_source(source)
        self.results.append(VerificationResult(
            status,
            f"Service '{service_name}' bind mount: {message}",
            file_name,
            f"{service_name}.{location}: {vol_str}"
        ))

    def _parse_bind_mount(self, vol_str: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse bind mount string handling ${VAR:-value} syntax."""
        # Strategy: find the first colon that is NOT inside ${...}
        in_brace = 0
        for i, ch in enumerate(vol_str):
            if ch == '$' and i + 1 < len(vol_str) and vol_str[i + 1] == '{':
                in_brace += 1
            elif ch == '}' and in_brace > 0:
                in_brace -= 1
            elif ch == ':' and in_brace == 0:
                # Found separator
                source = vol_str[:i]
                target = vol_str[i + 1:]
                # Remove mode if present (third colon not in braces)
                # Find next colon not in braces
                in_brace2 = 0
                for j, ch2 in enumerate(target):
                    if ch2 == '$' and j + 1 < len(target) and target[j + 1] == '{':
                        in_brace2 += 1
                    elif ch2 == '}' and in_brace2 > 0:
                        in_brace2 -= 1
                    elif ch2 == ':' and in_brace2 == 0:
                        target = target[:j]
                        break
                return source, target
        return None, None

    def _check_bind_mount_source(self, source: str) -> Tuple[str, str]:
        """Check if a bind mount source is Windows-compatible."""
        # Good patterns - use string matching for clarity
        # 1. Relative paths ./...
        if source.startswith('./'):
            return VerificationResult.PASS, f"Good pattern: {source}"

        # 2. USERPROFILE with or without fallback
        if source.startswith('${USERPROFILE'):
            return VerificationResult.PASS, f"Good pattern: {source}"

        # 3. HOME with fallback (${HOME:-~} or ${HOME:-~/...})
        # Source from YAML may have ${HOME:-~} or \${HOME:-~} depending on how it was written
        if source.startswith('${HOME:-~}') or source.startswith(r'\${HOME:-~}'):
            return VerificationResult.PASS, f"Good pattern: {source}"

        # 4. Root mount (for privileged containers)
        if source == '/':
            return VerificationResult.PASS, f"Good pattern: {source}"

        # Expected absolute paths (Linux VM paths, OK for privileged containers)
        for pattern in self.BIND_MOUNT_EXPECTED_ABSOLUTE:
            if re.match(pattern, source):
                return VerificationResult.PASS, f"Expected Linux VM path (privileged): {source}"

        # Caution patterns - bare HOME without fallback
        if re.match(r'^\$\{HOME\}(?![:-])', source):
            return VerificationResult.WARN, f"Uses ${{HOME}} without fallback: {source}"

        # Unknown pattern
        return VerificationResult.WARN, f"Unrecognized pattern (manual review): {source}"

    def _verify_service_environment(self, service_name: str, env: Any, file_name: str):
        """Verify environment variables for path-like values."""
        env_dict = {}
        if isinstance(env, list):
            # Array format: "KEY=VALUE" or "KEY"
            for item in env:
                if '=' in item:
                    k, v = item.split('=', 1)
                    env_dict[k] = v
                else:
                    env_dict[item] = ""
        elif isinstance(env, dict):
            env_dict = env

        for key, value in env_dict.items():
            if not isinstance(value, str):
                continue

            # Check if value looks like a path
            if self._looks_like_path(value):
                self._verify_env_value(service_name, key, value, file_name)

    def _looks_like_path(self, value: str) -> bool:
        """Check if a string value looks like a HOST filesystem path reference."""
        # Skip URLs - they contain :// which is not a filesystem path
        if '://' in value:
            return False
        # Skip container-internal absolute paths (they start with / but don't contain vars)
        if value.startswith('/') and '$' not in value and '~' not in value:
            return False
        # Skip simple variable references that don't look like paths
        # e.g., ${VAR}, ${VAR:-default}, ${VAR:-} - unless they contain path separators
        if re.match(r'^\$\{[A-Z_][A-Z0-9_]*(:-[^}]*)?\}$', value):
            # Only consider it path-like if it contains / or ~
            if '/' not in value and '~' not in value and '\\' not in value:
                return False
        # Contains path-like patterns that suggest HOST filesystem reference
        return bool(re.search(r'[/~$\\]', value))

    def _verify_env_value(self, service_name: str, key: str, value: str, file_name: str):
        """Verify an environment variable value for Windows compatibility."""
        # Check for bad patterns first
        for pattern in self.BAD_ENV_PATTERNS:
            if re.search(pattern, value):
                self.results.append(VerificationResult(
                    VerificationResult.FAIL,
                    f"Env '{key}': Hardcoded Windows path detected: {value}",
                    file_name,
                    f"{service_name}.environment.{key}"
                ))
                return

        # Check for good patterns
        for pattern in self.GOOD_ENV_PATTERNS:
            if re.search(pattern, value):
                self.results.append(VerificationResult(
                    VerificationResult.PASS,
                    f"Env '{key}': Good Windows-compatible pattern: {value}",
                    file_name,
                    f"{service_name}.environment.{key}"
                ))
                return

        # Check for caution patterns
        for pattern in self.CAUTION_ENV_PATTERNS:
            if re.search(pattern, value):
                self.results.append(VerificationResult(
                    VerificationResult.WARN,
                    f"Env '{key}': Uses ${{HOME}} without fallback: {value}",
                    file_name,
                    f"{service_name}.environment.{key}"
                ))
                return

        # If it contains path-like chars but no recognized pattern
        self.results.append(VerificationResult(
            VerificationResult.WARN,
            f"Env '{key}': Unrecognized path pattern (manual review): {value}",
            file_name,
            f"{service_name}.environment.{key}"
        ))

    def _verify_named_volumes(self, volumes: Dict, file_name: str):
        """Verify named volume definitions."""
        for vol_name, vol_config in volumes.items():
            self._verify_named_volume_name(vol_name, file_name, f"volumes.{vol_name}")

            if isinstance(vol_config, dict):
                driver = vol_config.get('driver', 'local')
                if driver != 'local':
                    self.results.append(VerificationResult(
                        VerificationResult.WARN,
                        f"Named volume '{vol_name}': Non-local driver '{driver}' may not work on Windows",
                        file_name,
                        f"volumes.{vol_name}.driver"
                    ))

    def _verify_named_volume_name(self, name: str, file_name: str, location: str):
        """Verify named volume naming convention."""
        # Docker volume names should be lowercase with hyphens/underscores
        if not re.match(r'^[a-z0-9][a-z0-9_-]*$', name):
            self.results.append(VerificationResult(
                VerificationResult.WARN,
                f"Named volume '{name}': Non-standard naming (use lowercase, hyphens, underscores)",
                file_name,
                location
            ))
        else:
            self.results.append(VerificationResult(
                VerificationResult.PASS,
                f"Named volume '{name}': Good naming convention",
                file_name,
                location
            ))

    def _verify_docker_compose_config(self, compose_files: List[str], file_name: str):
        """Run docker compose config --dry-run to validate variable interpolation."""
        import subprocess
        try:
            cmd = ['docker', 'compose']
            for f in compose_files:
                cmd.extend(['-f', f])
            cmd.extend(['config', '--dry-run'])
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=30
            )
            if result.returncode == 0:
                self.results.append(VerificationResult(
                    VerificationResult.PASS,
                    f"docker compose config --dry-run succeeded",
                    file_name,
                    "config-validation"
                ))
            else:
                # Check if it's just warnings about unset variables
                if "variable is not set" in result.stderr and result.returncode == 0:
                    self.results.append(VerificationResult(
                        VerificationResult.WARN,
                        f"docker compose config has unset variable warnings: {result.stderr[:200]}",
                        file_name,
                        "config-validation"
                    ))
                else:
                    self.results.append(VerificationResult(
                        VerificationResult.FAIL,
                        f"docker compose config --dry-run failed: {result.stderr[:500]}",
                        file_name,
                        "config-validation"
                    ))
        except subprocess.TimeoutExpired:
            self.results.append(VerificationResult(
                VerificationResult.WARN,
                f"docker compose config --dry-run timed out",
                file_name,
                "config-validation"
            ))
        except Exception as e:
            self.results.append(VerificationResult(
                VerificationResult.WARN,
                f"docker compose config --dry-run error: {e}",
                file_name,
                "config-validation"
            ))

    def print_report(self, ci_mode: bool = False) -> int:
        """Print verification report and return exit code."""
        print("=" * 80)
        print("Docker Compose Windows Path Convention Verification Report")
        print("=" * 80)

        # Group by status
        passes = [r for r in self.results if r.status == VerificationResult.PASS]
        warns = [r for r in self.results if r.status == VerificationResult.WARN]
        fails = [r for r in self.results if r.status == VerificationResult.FAIL]

        print(f"\nSUMMARY: {len(passes)} PASS, {len(warns)} WARN, {len(fails)} FAIL")
        print("-" * 80)

        if fails:
            print("\n[FAIL] FAILURES:")
            for r in fails:
                print(f"  {r}")

        if warns:
            print("\n[WARN] WARNINGS:")
            for r in warns:
                print(f"  {r}")

        if passes:
            print("\n[PASS] PASSES:")
            for r in passes:
                print(f"  {r}")

        print("\n" + "=" * 80)

        # Exit code logic
        if fails:
            return 1
        if warns and ci_mode:
            return 1
        return 0


def main():
    parser = argparse.ArgumentParser(description="Verify Docker Compose Windows path conventions")
    parser.add_argument("--ci", action="store_true", help="Exit with code 1 on warnings (for CI)")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).parent.parent,
                        help="Project root directory")
    args = parser.parse_args()

    verifier = DockerWindowsPathVerifier(args.project_root)
    verifier.verify_all()
    exit_code = verifier.print_report(ci_mode=args.ci)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()