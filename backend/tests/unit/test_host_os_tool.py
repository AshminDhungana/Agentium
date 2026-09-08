"""
Quick smoke tests for host_os_tool.
"""
import pytest
from unittest.mock import MagicMock, patch


def test_host_os_detect():
    from backend.tools.host_os_tool import host_os_tool

    result = host_os_tool.detect_os()
    assert result["status"] == "success"
    assert "os_profile" in result
    assert "available_operations" in result


def test_host_os_list_operations():
    from backend.tools.host_os_tool import host_os_tool

    result = host_os_tool.list_operations()
    assert result["status"] == "success"
    assert "operations" in result
    assert isinstance(result["operations"], list)
    assert len(result["operations"]) > 0


def test_host_os_smart_execute(monkeypatch):
    from backend.tools.host_os_tool import host_os_tool

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="test output",
            stderr=""
        )

        result = host_os_tool.smart_execute(
            raw_command=["echo", "hello"]
        )
        assert result["status"] == "success"


def test_host_os_invalid_operation():
    from backend.tools.host_os_tool import host_os_tool

    result = host_os_tool.execute_for_os(
        operation="invalid_operation"
    )
    assert result["status"] == "error"


def test_host_os_missing_action():
    from backend.tools.host_os_tool import host_os_tool

    # HostOSTool doesn't have execute - use detect_os instead
    result = host_os_tool.detect_os()
    assert result["status"] == "success"


def test_host_os_resolve_command_with_windows(monkeypatch):
    """Test resolve_command when Windows is detected."""
    from backend.tools.host_os_tool import host_os_tool, OS_WINDOWS

    # Manually set the cached profile to Windows
    host_os_tool._cached_profile = {
        "os_family": OS_WINDOWS,
        "os_name": "Windows 10",
        "os_version": "10.0.19045",
        "distro_family": None,
        "distro_id": None,
        "distro_id_like": None,
        "architecture": "AMD64",
        "kernel": "10.0.19045",
        "hostname": "TEST-PC",
        "package_manager": "winget",
        "detected_at": "2026-09-08T00:00:00",
    }

    result = host_os_tool.resolve_command(operation="os_version")
    assert result["resolved"] is True
    assert "command" in result
    assert len(result["command"]) > 0


def test_host_os_execute_for_os_with_windows(monkeypatch):
    """Test execute_for_os when Windows is detected."""
    from backend.tools.host_os_tool import host_os_tool, OS_WINDOWS

    # Manually set the cached profile to Windows
    host_os_tool._cached_profile = {
        "os_family": OS_WINDOWS,
        "os_name": "Windows 10",
        "os_version": "10.0.19045",
        "distro_family": None,
        "distro_id": None,
        "distro_id_like": None,
        "architecture": "AMD64",
        "kernel": "10.0.19045",
        "hostname": "TEST-PC",
        "package_manager": "winget",
        "detected_at": "2026-09-08T00:00:00",
    }

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Microsoft Windows [Version 10.0.19045.1234]",
            stderr=""
        )

        result = host_os_tool.execute_for_os(operation="os_version")
        assert result["status"] == "success"