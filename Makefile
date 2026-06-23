# Agentium Makefile

.PHONY: up down restart voice-reinstall voice-logs voice-status uninstall-voice test-integration

# ── Normal start — voice bridge installs automatically ────────────────────────
up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose down && docker compose up -d

# ── Force reinstall voice bridge (deletes the skip-marker then restarts) ──────
voice-reinstall:
	@echo "Clearing voice install marker..."
	@rm -f ~/.agentium/voice-installed.marker
	@echo "Restarting voice-autoinstall service..."
	docker compose up -d voice-autoinstall
	docker compose logs -f voice-autoinstall

# ── Uninstall voice bridge from host ──────────────────────────────────────────
uninstall-voice:
	@bash scripts/uninstall-voice-bridge.sh
	@rm -f ~/.agentium/voice-installed.marker
	@echo "Voice bridge uninstalled."

# ── Tail voice bridge logs ─────────────────────────────────────────────────────
voice-logs:
	@SVC=$$(grep SVC_MGR ~/.agentium/env.conf 2>/dev/null | cut -d= -f2); \
	case "$$SVC" in \
	  systemd) journalctl --user -u agentium-voice -f ;; \
	  launchd)  tail -f ~/.agentium/voice-bridge.log ;; \
	  *)        tail -f ~/.agentium/voice-bridge.log ;; \
	esac

# ── Check voice bridge service status ─────────────────────────────────────────
voice-status:
	@SVC=$$(grep SVC_MGR ~/.agentium/env.conf 2>/dev/null | cut -d= -f2); \
	case "$$SVC" in \
	  systemd) systemctl --user status agentium-voice ;; \
	  launchd)  launchctl list com.agentium.voice ;; \
	  wsl2)     ps aux | grep agentium-voice ;; \
	  *)        echo "Run manually: ps aux | grep main.py" ;; \
	esac

# ── Integration Tests (Phase 18) ─────────────────────────────────────────────
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
	  pytest --cov=backend/services --cov-report=term-missing --cov-fail-under=80
	@docker compose -f docker-compose.test.yml down
