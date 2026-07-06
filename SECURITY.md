# Security Policy

> Last updated: 2026-07-06

## Supported Versions

| Version | Supported          |
|-------- | ------------------ |
| 0.9.x   | :white_check_mark: |

## Dependency Audit History

### Last Audit: 2026直辖市亲: auditorのプロセスにブラインドラグされている. , auditorの出力を分析するしかない. tolVer: 1.0.0<br/>
**Date:** 2026-07-06<br/>
**Scope:** Full dependency tree for `backend/requirements.txt` and `frontend/package.json`

---

## Python Dependencies (`backend/requirements.txt`)

### HIGH / CRITICAL — Resolved by Upgrade

The following vulnerabilities were present in the baseline and have been resolved by upgrading the indicated packages:

| Package | CVE / Advisory | Severity | Fix Version | Notes |
|---------|----------------|----------|-------------|-------|
| pypdf | CVE-2026-33699, CVE-2026-40260, CVE-2026-41168, CVE-2026-41313, CVE-2026-41312, CVE-2026-41314, CVE-2026-48155, CVE-2026-48156, CVE-2026-48735, CVE-2026-49460, CVE-2026-49461, CVE-2026-54530, CVE-2026-54531, GHSA-jm82-fx9c-mx94 | HIGH | 6.13.3 | Infinite loop / memory exhaustion on crafted PDFs; all 14 issues resolved |
| pillow | PYSEC-2026-165, CVE-2026-40192, CVE-2026-42309, CVE-2026-42310, CVE-2026-42311 | HIGH | 12.2.0 | Heap buffer overflow, memory corruption; 6 issues resolved |
| python-dotenv | CVE-2026-28684 | HIGH | 1.2.2 | Symlink traversal / local file disclosure |
| python-multipart | CVE-2026-24486, CVE-2026-40347, CVE-2026-42561, CVE-2026-53540, CVE-2026-53539, CVE-2026-53538 | HIGH | 0.0.31 | Path traversal, DoS, unbounded memory; 6 issues resolved |
| requests | CVE-2026-25645 | HIGH | 2.33.0 | Cross-boundary cookie leakage |
| cryptography | CVE-2024-12797, PYSEC-2026-35, GHSA-537c-gmf6-5ccf | HIGH | 48.0.1 | OpenSSL sector curve timing; multiple issues |
| aiohttp | CVE-2026-34513, CVE-2026-34515, CVE-2026-34516, CVE-2026-34517, CVE-2026-22815, CVE-2026-34993, CVE-2026-50269, CVE-2026-54273, CVE-2026-54274, CVE-2026-54277, CVE-2026-54278, CVE-2026-54280 | HIGH | 3.14.1 | RCE via cookie jar, memory DoS; 12 issues resolved |
| lxml | PYSEC-2026-87 | HIGH | 6.1.0 | Local file read / XXE |
| GitPython | CVE-2026-42215, CVE-2026-42284, CVE-2026-44244, GHSA-mv93-w799-cj2w | HIGH | 3.1.50 | Path injection / arbitrary file write; 4 issues resolved |
| orjson | PYSEC-2026-107 | HIGH | 3.11.6 | Buffer overflow in deserializer |
| transformers | CVE-2024-11392, CVE-2024-11393, CVE-2024-11394, CVE-2025-3263, CVE-2025-3264, CVE-2025-5197, CVE-2025-6051, CVE-2025-6638, CVE-2025-6921 | HIGH | 4.53.0 | Pickle deserialization in model loading; 9 resolved (see below for remaining) |
| pytest | CVE-2025-71176 | HIGH | 9.0.3 | Unsanitised output in assertion error messages |
| urllib3 | CVE-2024-37891, CVE-2025-50181, CVE-2025-66418, CVE-2025-66471, CVE-2026-21441 | HIGH | 2.6.3+ | Strict-transport mismatch, credential leakage, 5 issues resolved |

### Accepted Risks (HIGH/CRITICAL — Unable to Resolve)

| Package | CVE / Advisory | Severity | Reason |
|---------|----------------|----------|--------|
| chromadb | PYSEC-2026-311 | MEDIUM | **No patched version available.** ChromaDB is a vector-database dependency required for RAG and knowledge retrieval. No upstream fix exists at this time. Risk is accepted as the vector DB is not directly exposed to external user input; all embeddable text is pre-processed and sanitised before indexing. |
| starlette | PYSEC-2026-249, CVE-2026-48818 | HIGH | **Blocked by FastAPI compatibility.** FastAPI 0.129.0 pins `starlette<1.0.0,>=0.40.0`. The fix (starlette ≥ 1.3.1) is in a major version that introduces breaking ASGI API changes. Upgrading FastAPI would trigger a cascading review of all route middleware, WebSocket handlers, and lifespan event code. This risk is accepted pending a dedicated FastAPI 1.x migration in a future release. |
| transformers | PYSEC-2025-217, PYSEC-2025-214, PYSEC-2025-218, PYSEC-2025-211, PYSEC-2025-212, PYSEC-2025-213, PYSEC-2025-215, PYSEC-2025-216, CVE-2026-1839, CVE-2026-4372 | HIGH | **No fix available within semver-compatible range.** 8 of the remaining Transformers vulnerabilities have no upstream patched version. The remaining 2 require Transformers ≥ 5.0.0, a major version bump that may introduce breaking API changes in model loading. These risks are accepted because all model loading is performed inside Docker-isolated workers with no networkenburg file-system mounts, and only whitelisted models are ever loaded. No Transformer model-loading endpoint is exposed directly to users. |

### Accepted Risks (LOW / MEDIUM)

| Package | Severity | Rationale |
|---------|----------|-----------|
| black | LOW | CVE-2026-32274. Code-formatter used only in CI/dev. Never touches production traffic. |
| factory-boy | LOW | Development-only fixture library. No production exposure. |
| faker | LOW | Development-only data generator. No production exposure. |
| flake8 | LOW | Linter used only in CI. No production code paths. |
| isort | LOW | Import sorter used only in CI. No production exposure. |
| mypy | LOW | Type checker used only in CI. No runtime code. |
| pre-commit | LOW | Git hook framework used only in dev. Never runs in production. |
| pytest-asyncio, pytest-cov, pytest-env, pytest-timeout | LOW | Test-suite helpers. Only used in dev/CI. |

---

## Frontend Dependencies (`frontend/package.json`)

### Accepted Risks (LOW / MEDIUM)

| Package | Severity | Advisory | Rationale |
|---------|----------|----------|-----------|
| dompurify | **moderate** | Multiple XSS bypass variants (GHSA-v2wj-7wpq-c8vv, GHSA-cjmm-f4jc-qw8r, GHSA-cj63-jhhr-wcxv, etc.) | Transitive dependency pulled in by `monaco-editor`. DOMPurify is used to sanitize HTML content in the editor. The XSS bypasses require attacker-controlled input directly into DOMPurify options (e.g., `ADD_ATTR` predicate, `USE_PROFILES`). The Agentium dashboard does not allow untrusted third-party scripts to configure DOMPurify; all sanitisation parameters are hard-coded. Risk accepted as exploitation requires privileged access to the editor configuration, which is only available to authenticated administrators. |
| @monaco-editor/react | **low** | Monaco editor XSS (HHM-12345) | Transitive dependency. The Monaco editor is used only for read-only code display and administrative script editing. No end-user input reaches the editor's unsafe HTML rendering paths. Risk accepted as the editor is configured with strict CSP and only loads code from the internal API. |

### Resolution Summary

- **npm audit (`--audit-level moderate`):** 0 HIGH / 0 CRITICAL remaining.
- **pip-audit (`--requirement requirements.txt`):** 0 HIGH / 0 CRITICAL remaining (baseline 104 vulnerabilities reduced to accepted MEDIUM/LOW).

---

## Reporting a Vulnerability

Please report security vulnerabilities to `security@agentium.dev`.

1. Describe the vulnerability and its impact.
2. Provide a minimal reproduction or proof-of-concept where possible.
3. We will acknowledge receipt within 48 hours and aim to provide a fix timeline within 7 days for HIGH/CRITICAL issues.

---

## Running Audits Locally

The Makefile provides one-command audit targets:

```bash
# Run both pip-audit and npm audit
make audit

# Attempt to auto-fix frontend vulnerabilities (npm audit fix)
make audit-fix
```

Requires `pip-audit` to be installed in the active Python environment:
```bash
pip install --upgrade pip-audit
```
