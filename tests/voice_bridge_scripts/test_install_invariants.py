# tests/voice_bridge_scripts/test_install_invariants.py
"""Static invariants for the voice-bridge self-installer.

These parse the shell/PowerShell sources as text and assert the
correctness rules from the plan. They run on any platform with pytest.
"""
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _read(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8", errors="ignore")


def test_autoinstall_does_not_touch_marker():
    src = _read("voice-autoinstall.sh")
    assert 'touch "$MARKER"' not in src, (
        "voice-autoinstall.sh must NOT create the install marker; "
        "only the host installer (install-voice-bridge.*) may."
    )


def test_autoinstall_windows_no_dead_triggers():
    src = _read("voice-autoinstall.sh")
    for dead in ("agentium-runonce.reg", "prompt.vbs",
                 "agentium-voice-setup.hta", "agentium-voice-prompt.cmd"):
        assert dead not in src, f"Dead/duplicate Windows trigger left in: {dead}"


def test_install_ps1_creates_marker():
    src = _read("install-voice-bridge.ps1")
    assert "voice-installed.marker" in src, (
        "install-voice-bridge.ps1 must create voice-installed.marker on success"
    )


def test_uninstall_ps1_removes_marker_and_artifacts():
    src = _read("uninstall-voice-bridge.ps1")
    assert "voice-installed.marker" in src
    assert "agentium-voice-startup.cmd" in src   # Startup launcher cleanup
    assert "Install Agentium Voice Bridge.cmd" in src  # Desktop shortcut cleanup


def test_startup_cmd_guards_marker():
    src = _read("agentium-voice-startup.cmd")
    assert "voice-installed.marker" in src, (
        "Startup launcher must bail out when the install marker exists"
    )


def test_install_sh_handles_apk():
    src = _read("install-voice-bridge.sh")
    assert "apk)" in src, "install-voice-bridge.sh must handle the apk pkg manager"


def test_install_sh_creates_marker():
    src = _read("install-voice-bridge.sh")
    assert "voice-installed.marker" in src


def test_uninstall_sh_removes_marker():
    src = _read("uninstall-voice-bridge.sh")
    assert "voice-installed.marker" in src


def test_makefile_no_corrupted_log_literal():
    makefile = (SCRIPTS.parent / "Makefile").read_text(encoding="utf-8", errors="ignore")
    assert "voice-br" not in makefile or "voice-br将会是" not in makefile, (
        "Makefile voice-logs has a corrupted log filename literal"
    )
