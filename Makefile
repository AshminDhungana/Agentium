# Agentium Makefile

.PHONY: up down restart voice-reinstall voice-logs voice-status uninstall-voice test hallmark test-integration load-test benchmark perf-gate test-staging audit audit-fix pin-digests docker-scout

# -- Normal start -- voice bridge installs automatically --
up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose down && docker compose up -d

# -- Force reinstall voice bridge --
voice-reinstall:
	@if [ -d /run/desktop/mnt/host ] || uname -s | grep -qiE "MINGW|MSYS|CYGWIN"; then \
	  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Force; \
	else \
	  rm -f ~/.agentium/voice-installed.marker; \
	  docker compose up -d voice-autoinstall; \
	  docker compose logs -f voice-autoinstall; \
	fi

# -- Uninstall voice bridge from host --
uninstall-voice:
	@if [ -d /run/desktop/mnt/host ] || uname -s | grep -qiE "MINGW|MSYS|CYGWIN"; then \
	  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/uninstall-voice-bridge.ps1; \
	else \
	  bash scripts/uninstall-voice-bridge.sh && rm -f ~/.agentium/voice-installed.marker; \
	fi
	@echo "Voice bridge uninstalled."

# -- Tail voice bridge logs --
voice-logs:
	@if [ -d /run/desktop/mnt/host ] || uname -s | grep -qiE "MINGW|MSYS|CYGWIN"; then \
	  powershell.exe -NoProfile -Command "Get-Content (Join-Path $$env:USERPROFILE '.agentium\\voice-bridge.log') -Tail 50"; \
	else \
	  SVC=$$(grep SVC_MGR ~/.agentium/env.conf 2>/dev/null | cut -d= -f2); \
	  case "$$SVC" in \
	    systemd) journalctl --user -u agentium-voice -f ;; \
	    launchd)  tail -f ~/.agentium/voice-bridge.log ;; \
	    *)        tail -f ~/.agentium/voice-bridge.log ;; \
	  esac; \
	fi

# -- Check voice bridge service status --
voice-status:
	@if [ -d /run/desktop/mnt/host ] || uname -s | grep -qiE "MINGW|MSYS|CYGWIN"; then \
	  powershell.exe -NoProfile -Command "Get-ScheduledTask -TaskName AgentiumVoiceBridge -ErrorAction SilentlyContinue | Select-Object TaskName,State"; \
	else \
	  SVC=$$(grep SVC_MGR ~/.agentium/env.conf 2>/dev/null | cut -d= -f2); \
	  case "$$SVC" in \
	    systemd) systemctl --user status agentium-voice ;; \
	    launchd)  launchctl print gui/$$(id -u)/com.agentium.voice ;; \
	    *)        echo "Run manually: ps aux | grep agentium-voice" ;; \
	  esac; \
	fi
	@echo "── whisper.cpp (local STT) ──"
	@if docker compose ps --status running backend >/dev/null 2>&1; then \
	  docker compose exec -T backend sh -c 'if [ -x /usr/local/bin/whisper-cli ] && [ -f /opt/whisper/models/ggml-base.en.bin ]; then echo "whisper.cpp: OK (binary + model present)"; else echo "whisper.cpp: MISSING (binary or model not found)"; fi'; \
	else \
	  echo "backend container not running — start with 'make up' to verify whisper.cpp"; \
	fi

# -- Integration Tests (Phase 18) --
test-integration:
	@echo "Starting ephemeral test infrastructure..."
	@docker compose -f docker-compose.test.yml up -d
	@sleep 5
	@cd backend && \
	  DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test \
	  REDIS_URL=redis://localhost:6379/1 \
	  CHROMA_HOST=localhost \
	  CHROMA_PORT=8001 \
	  CELERY_TASK_ALWAYS_EAGER=true \
	  TESTING=true \
	  PYTHONPATH=. \
	  pytest
	@docker compose -f docker-compose.test.yml down

# -- Performance Regression Gate (Phase 18.2) --
STAGING_HOST ?= http://localhost:8000

# Run pytest-benchmark ChromaDB query benchmark
benchmark:
	@echo "Running ChromaDB performance benchmark..."
	@cd backend && \
	  DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test \
	  REDIS_URL=redis://localhost:6379/1 \
	  CHROMA_HOST=localhost \
	  CHROMA_PORT=8001 \
	  TESTING=true \
	  PYTHONPATH=. \
	  pytest tests/benchmarks/test_chroma_query.py -m benchmark --benchmark-only --benchmark-save=baseline

# Run Locust load-test suite against ephemeral infra or staging
load-test:
	@echo "Running Locust load-test suite..."
	@echo "Target: $(STAGING_HOST) | Users: $(or $(LOCUST_USERS),1000) | Duration: $(or $(LOCUST_RUN_TIME),5m)"
	@cd backend/tests/load && \
	  locust \
	    --host $(STAGING_HOST) \
	    --users $(or $(LOCUST_USERS),1000) \
	    --spawn-rate $(or $(LOCUST_SPAWN_RATE),10) \
	    --run-time $(or $(LOCUST_RUN_TIME),5m) \
	    --headless \
	    --html locust_report.html

# Run all performance gates (benchmark + load-test)
perf-gate: benchmark load-test
	@echo "Performance regression gate complete."

# Run tests against a staging environment (set STAGING_HOST env var)
test-staging:
	@echo "Running performance gates against staging: $(STAGING_HOST)"
	@make load-test STAGING_HOST=$(STAGING_HOST)

# --- Security Audit Targets (Phase 18.5) ---

## Run all security audits (pip-audit + npm audit)
audit:
	@echo "==> Running pip-audit on backend/requirements.txt..."
	@cd backend && pip-audit --requirement requirements.txt --format=markdown || true
	@echo "==> Running npm audit on frontend..."
	@cd frontend && npm audit || true

## Attempt to auto-fix resolvable frontend vulnerabilities (npm audit fix)
audit-fix:
	@echo "==> Running npm audit fix..."
	@cd frontend && npm audit fix
	@echo "==> Re-running audits..."
	@make audit

# ── Docker Image Hardening (Phase 18.5) ──────────────────────────────

## Pin base image digests to .pinned-digests.env
pin-digests:
	@echo "==> Pinning base image digests..."
	@bash scripts/pin-digests.sh

## Run docker scout CVE scan on all built images (fails on HIGH/CRITICAL)
docker-scout:
	@echo "==> Running docker scout on all images..."
	@bash scripts/docker-scout.sh high

## Build all images locally before scanning
docker-scout-build: pin-digests
	@echo "==> Building all Docker images..."
	@docker build -t agentium-backend:privileged -f backend/Dockerfile.privileged backend/
	@docker build -t agentium-frontend:latest -f frontend/Dockerfile frontend/
	@docker build -t agentium-whatsapp:latest -f bridges/whatsapp/Dockerfile bridges/whatsapp/
	@echo "==> Built all images. Running docker scout..."
	@bash scripts/docker-scout.sh high
