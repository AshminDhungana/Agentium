import asyncio
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from backend.services.whisper_cpp_service import (
    WhisperCppService,
    LocalSTTError,
    get_whisper_cpp_service,
    _gpu_available,
)


def _fake_proc(stdout="hello world", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture
def svc():
    return WhisperCppService()


def test_parse_stdout(svc, monkeypatch):
    monkeypatch.setattr(svc, "is_available", lambda: True)
    with patch("asyncio.to_thread", side_effect=lambda f, *a, **k: f(*a, **k)), \
         patch("subprocess.run", return_value=_fake_proc(stdout="  hello world  \n")):
        result = asyncio.run(svc.transcribe(b"RIFF...."))
    assert result == "hello world"


def test_missing_binary_raises_and_skips_subprocess(svc, monkeypatch):
    monkeypatch.setenv("WHISPER_CPP_BIN", "/nonexistent/whisper-cli")
    with patch("subprocess.run") as run:
        with pytest.raises(LocalSTTError):
            asyncio.run(svc.transcribe(b"data"))
    run.assert_not_called()


def test_nonzero_exit_raises(svc, monkeypatch):
    monkeypatch.setattr(svc, "is_available", lambda: True)
    with patch("asyncio.to_thread", side_effect=lambda f, *a, **k: f(*a, **k)), \
         patch("subprocess.run", return_value=_fake_proc(returncode=1, stderr="boom")):
        with pytest.raises(LocalSTTError):
            asyncio.run(svc.transcribe(b"data"))


def test_timeout_raises(svc, monkeypatch):
    monkeypatch.setattr(svc, "is_available", lambda: True)
    def _raise(*a, **k):
        raise subprocess.TimeoutExpired(cmd="whisper-cli", timeout=1)

    with patch("asyncio.to_thread", side_effect=_raise):
        with pytest.raises(LocalSTTError):
            asyncio.run(svc.transcribe(b"data"))


def test_empty_output_raises(svc, monkeypatch):
    monkeypatch.setattr(svc, "is_available", lambda: True)
    with patch("asyncio.to_thread", side_effect=lambda f, *a, **k: f(*a, **k)), \
         patch("subprocess.run", return_value=_fake_proc(stdout="")):
        with pytest.raises(LocalSTTError):
            asyncio.run(svc.transcribe(b"data"))


def test_gpu_probe_true(monkeypatch):
    monkeypatch.setattr("os.path.exists", lambda p: p == "/dev/nvidia0")
    with patch("ctypes.CDLL", return_value=MagicMock()):
        assert _gpu_available() is True


def test_gpu_probe_false_without_device():
    assert _gpu_available() is False


def test_singleton_returns_same_instance():
    a = get_whisper_cpp_service()
    b = get_whisper_cpp_service()
    assert a is b
