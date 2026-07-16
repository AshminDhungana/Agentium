# tests/voice_bridge_scripts/test_install_improvements.py
"""Static invariants for the voice-bridge installer improvements."""
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
MAKEFILE = SCRIPTS.parent / "Makefile"


def _read(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8", errors="ignore")


def test_install_sh_no_legacy_launchctl_load():
    src = _read("install-voice-bridge.sh")
    assert "launchctl load" not in src, "macOS must use 'launchctl bootstrap', not legacy 'load'"
    assert "launchctl unload" not in src, "macOS must use 'launchctl bootout', not legacy 'unload'"
    assert "launchctl bootstrap" in src
    assert "launchctl kickstart" in src


def test_install_sh_plist_perms():
    src = _read("install-voice-bridge.sh")
    assert "chmod 644" in src, "LaunchAgent plist must be chmod 644"
    assert "chown" in src, "LaunchAgent plist must be chowned to the user"


def test_uninstall_sh_uses_bootout():
    src = _read("uninstall-voice-bridge.sh")
    assert "launchctl bootout" in src
    assert "launchctl unload" not in src


def test_detect_sh_macos_host_docker_internal():
    src = _read("detect-host.sh")
    assert "host.docker.internal" in src, "macOS/Windows/WSL2 must use host.docker.internal"


def test_install_ps1_cleans_lnk():
    src = _read("install-voice-bridge.ps1")
    assert "AgentiumVoiceBridge.lnk" in src, "installer cleanup must remove the .lnk launcher"


def test_install_ps1_marker_gated_on_up():
    src = _read("install-voice-bridge.ps1")
    assert "voice-installed.marker" in src
    assert "$BridgeUp" in src, "marker creation must be gated on the bridge actually coming up"


def test_uninstall_ps1_cleans_lnk():
    src = _read("uninstall-voice-bridge.ps1")
    assert "AgentiumVoiceBridge.lnk" in src


def test_setup_ps1_force_param_and_marker_guard():
    src = _read("setup.ps1")
    assert "Force" in src, "setup.ps1 needs a -Force switch"
    assert "voice-installed.marker" in src, "setup.ps1 must early-exit when already installed"


def test_install_sh_brew_not_malformed():
    src = _read("install-voice-bridge.sh")
    # When SUDO is empty (root) we must NOT emit a bare '-u <user> brew'
    assert 'if [[ -n "$SUDO" ]]' in src, "brew branch must guard the -u flag on SUDO"


def test_makefile_logs_status_windows_aware():
    mk = MAKEFILE.read_text(encoding="utf-8", errors="ignore")
    assert "voice-logs:" in mk and "voice-status:" in mk
    # Windows/Docker-Desktop aware branch references powershell
    assert "powershell.exe" in mk, "voice-logs/voice-status should be Docker-Desktop aware"
