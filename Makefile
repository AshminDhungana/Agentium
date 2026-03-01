# Agentium Makefile

.PHONY: up down restart voice-reinstall voice-logs voice-status uninstall-voice

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