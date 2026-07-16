# Voice Bridge Setup (Host-Side)

The **Voice Bridge** (`voice-bridge/`) is a small Python service that runs on your
**host machine (outside Docker)**. It captures microphone audio, streams it to the
backend for speech-to-text, speaks the reply back via TTS, and exposes a local
WebSocket control channel at `ws://127.0.0.1:9999`. It is what turns Agentium into a
"Jarvis"-style assistant (wake word → talk → spoken reply).

Because it needs the host microphone and speakers, it cannot live inside a container
that has no audio device. So Agentium installs it **on the host** automatically.

> Related: feature/design background lives in
> `docs/superpowers/specs/2026-07-15-voice-bridge-jarvis-design.md`.
> Installer fixes are tracked in
> `docs/superpowers/plans/2026-07-16-voice-bridge-install-fix.md` and
> `docs/superpowers/plans/2026-07-16-voice-bridge-install-improvements.md`.

## Prerequisites

- The backend stack is already running (`make up`) — the auto-installer waits for the
  backend to be healthy before dropping files.
- **Python 3.10+** installed on the host.
  - Windows: install from <https://www.python.org/downloads/> (the Microsoft Store
    build also works — the installer uses a VBScript launcher for it).
  - macOS: `brew install python` (and `brew install portaudio` for mic capture).
  - Linux: your distro's `python3` (`apt`/`dnf`/`pacman`/`zypper`/`apk`).

## Quick start (automatic)

```bash
make up
```

On `docker compose up`, the `voice-autoinstall` service runs once:

- **Linux / macOS / WSL2:** it detects the OS and installs the bridge directly
  (creates a venv at `~/.agentium/voice-venv`, installs deps, registers the OS
  service, and starts it).
- **Windows (Docker Desktop):** a Linux container cannot run PowerShell on your host,
  so it only **drops installer files** into your user profile via the
  `${USERPROFILE}` mount, then exits. The real install happens later on the host
  (see Windows below).

## Install by OS (manual)

### Windows

After `make up`, look for one of these on your host:

- **Desktop shortcut:** `Install Agentium Voice Bridge.cmd`
- **Startup folder:** `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\agentium-voice-startup.cmd`

Double-click the Desktop shortcut (or log out/in to trigger the Startup launcher).
A **UAC prompt** appears once → click **Allow**. `setup.ps1` then:

1. Creates a Python venv at `%USERPROFILE%\.agentium\voice-venv`
2. Installs `websockets`, `SpeechRecognition`, `python-jose`, `pyttsx3`, `PyAudio`
3. Registers the auto-start mechanism (Task Scheduler for normal Python, or a
   Startup VBScript shortcut for Windows Store Python)
4. Starts the bridge and verifies it is listening on port `9999`

Alternatively, run it directly from a repo checkout:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

To force a clean reinstall (ignores the "already installed" guard):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Force
# or:  make voice-reinstall
```

### Linux

```bash
bash voice-bridge/install.sh
```

This runs OS detection then the dependency + service installer. The bridge is
registered as a **systemd user service** (`agentium-voice`) when a user session is
available, otherwise it falls back to a `nohup` start + an `rc`/`.profile` entry.
If the service does not auto-start after a reboot, enable linger:

```bash
loginctl enable-linger "$USER"
```

### macOS

```bash
bash voice-bridge/install.sh
```

Registers a **LaunchAgent** (`~/Library/LaunchAgents/com.agentium.voice.plist`)
using the modern `launchctl bootstrap` / `kickstart` API, and starts it. Grant
microphone permission when macOS prompts.

> Note: there is no `make install-voice` target. Use `bash voice-bridge/install.sh`
> (or `make voice-reinstall` / `make uninstall-voice` which do exist).

## Verify it is running

```bash
make voice-status     # Docker-Desktop aware (PowerShell on Windows, systemd/launchctl on Unix)
make voice-logs       # tails ~/.agentium/voice-bridge.log
```

Or check the port directly:

```bash
# Windows (PowerShell)
Test-NetConnection -ComputerName 127.0.0.1 -Port 9999
# Linux/macOS
( ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null ) | grep 9999
```

The bridge's own log: `~/.agentium/voice-bridge.log`.

## Uninstall

```bash
make uninstall-voice
```

- **Windows / WSL→Docker Desktop:** runs `scripts/uninstall-voice-bridge.ps1` — stops
  the Task Scheduler job, removes the Startup launcher, Desktop shortcut, venv
  bootstrap files, and the `voice-installed.marker`.
- **Native Linux / macOS:** runs `scripts/uninstall-voice-bridge.sh` — stops the
  systemd user service / LaunchAgent and the running process.

(The venv and `env.conf` under `~/.agentium/` are left in place; delete them
manually if you want a fully clean slate.)

## Reinstall / force

```bash
make voice-reinstall
```

- **Windows:** runs `setup.ps1 -Force`.
- **Linux / macOS:** deletes `~/.agentium/voice-installed.marker` and re-runs the
  `voice-autoinstall` container.

You can also just delete the marker manually and log out/in (Windows) or re-run
`bash voice-bridge/install.sh` (Unix).

## Configuration

All runtime options are read from `~/.agentium/env.conf` (written by the OS detector)
or environment variables. See the **Voice Bridge (host-side) configuration** table in
`README.md` (wake word, TTS voice, VAD silence, proactive mode, backend URL, etc.).
The backend URL is auto-detected: `http://host.docker.internal:8000` on Docker Desktop
(macOS/Windows/WSL2), or `http://172.17.0.1:8000` on native Linux.

## Logs & troubleshooting

| Symptom | Fix |
|---|---|
| Windows: nothing happened after `make up` | Look for the **Desktop shortcut** `Install Agentium Voice Bridge.cmd`. Once installed, the `voice-installed.marker` suppresses the auto-prompt by design. |
| Bridge won't install / deps fail | Read `%USERPROFILE%\.agentium\install.log` and `voice-bridge.log`. Ensure Python 3.10+ is on `PATH`. |
| "Already installed" but bridge not running | Delete `~/.agentium/voice-installed.marker` (Windows) or `~/.agentium/voice-installed.marker` (Unix) and re-run, or use `make voice-reinstall`. |
| Backend unreachable (macOS/Windows) | The installer auto-selects `host.docker.internal`. Confirm the backend container is up (`docker compose ps`). |
| Linux: service doesn't start after reboot | `loginctl enable-linger "$USER"`. |
| macOS: mic silent | Grant microphone permission to the bridge in System Settings → Privacy & Security → Microphone. Inspect with `launchctl print gui/$(id -u)/com.agentium.voice`. |

## How it works (files & marker)

- **Install marker:** `~/.agentium/voice-installed.marker` is created **only when the
  bridge is confirmed listening on port 9999**. It is what stops the auto-prompt and
  Startup launcher from re-firing. If the bridge fails to start, the marker is NOT
  written, so the next login retries.
- **Windows dropped files** (in `%USERPROFILE%\.agentium` and Startup/Desktop):
  `bootstrap-voice.cmd`, `agentium-voice-startup.cmd`, `Install Agentium Voice Bridge.cmd`.
- **Unix service units:** systemd `~/.config/systemd/user/agentium-voice.service`,
  or LaunchAgent `~/Library/LaunchAgents/com.agentium.voice.plist`, or a `nohup`
  fallback.

## Implementation notes

- The Linux/macOS auto-install runs *inside* the ephemeral `voice-autoinstall`
  container, so for a **persistent** install on a native Linux/macOS host, run
  `bash voice-bridge/install.sh` directly on the host (the container path is mainly
  for dropping the Windows bootstrap files).
- All installer behavior is covered by static tests in
  `tests/voice_bridge_scripts/`.
