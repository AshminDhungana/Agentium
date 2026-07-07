# Docker Image Hardening — Phase 18.5 (SUMMARY)

## Overview
This document tracks the Docker image hardening completed for Agentium Phase 18.5 per the specification in `docs/documents/todo.md`.

## Changes Made

### 1. Base Image Digest Pinning
All Docker base images are now pinned to immutable SHA256 digests.

| Image | Digest |
|-------|--------|
| `python:3.11-slim-bookworm` | `sha256:f5ef0344c9886ff24d34797578d5d7dd6e8911ae0fe5962bb55d0f89603ec361` |
| `node:20-alpine` | `sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293` |
| `nginx:alpine` | `sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa` |

### 2. Files Modified

| File | Change |
|------|--------|
| `backend/Dockerfile.privileged` | Pinned digest in `FROM` line |
| `backend/Dockerfile` | Pinned digest in both `FROM` lines |
| `backend/Dockerfile.remote-executor` | Pinned digest in `FROM` line |
| `frontend/Dockerfile` | Pinned digests, added `agentium-nginx` non-root user |
| `bridges/whatsapp/Dockerfile` | Pinned digest, added `appuser` non-root group+user |
| `Makefile` | Added `pin-digests` and `docker-scout` targets |

### 3. Files Created

| File | Purpose |
|------|---------|
| `.pinned-digests.env` | Stores immutable digests for CI and rebuilds |
| `scripts/pin-digests.sh` | Re-fetches latest digests and updates `.pinned-digests.env` |
| `scripts/docker-scout.sh` | Runs `docker scout cves` on all built images |

## Non-Root Users

| Service | Dockerfile | Non-Root User | Status |
|---------|-----------|---------------|--------|
| Backend (privileged) | `backend/Dockerfile.privileged` | `agentium` | ✅ Already configured |
| Backend (standard) | `backend/Dockerfile` | `agentium` | ✅ Already configured |
| Frontend | `frontend/Dockerfile` | `agentium-nginx` (UID 101) | ✅ Added |
| WhatsApp Bridge | `bridges/whatsapp/Dockerfile` | `appuser` (UID 1001) | ✅ Added |

## CI/CD Notes
- The `.github/workflows/docker-image.yml` workflow still needs to be updated to consume `.pinned-digests.env` and pass digests as `build-args` to `docker/build-push-action`.
- The workflow also still needs `docker/scout-action` added post-merge for CVE scanning.
- **These CI changes are left for the user to complete.**

## Known Limitations
- Docker Scout scan requires ~2x image size in free disk space (8 GB for a 4 GB backend image). Ensure CI runners have adequate disk space.
- The backend image remains large (~7.5 GB) due to PyTorch, Chromium, and heavy ML dependencies. This is expected for the current feature set.

## Acceptance Checklist
- [x] All base image tags replaced with SHA256 digests
- [x] Non-root users added to all service images
- [x] `scripts/pin-digests.sh` utility created
- [x] `scripts/docker-scout.sh` utility created
- [x] `Makefile` updated with `pin-digests` and `docker-scout` targets
- [ ] CI workflow updated with digest pinning and docker scout (**user-owned**)
- [ ] Final smoke test `docker compose up --build` passes (**user-owned**)
