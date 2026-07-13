# whisper.cpp Local STT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local whisper.cpp the primary speech-to-text engine (built into the backend container), with a fallback chain of whisper.cpp → OpenAI Whisper → browser-native Web Speech.

**Architecture:** whisper.cpp is compiled into the backend image via a new CMake build stage and invoked through its `whisper-cli` binary by a new `WhisperCppService`. `AudioService.transcribe()` owns the server-side chain (local first, then OpenAI). The host voice-bridge relays mic audio to the backend; the frontend switches to browser-native only when the backend reports no server STT.

**Tech Stack:** whisper.cpp (C/C++, CMake build), `whisper-cli` subprocess, FastAPI/pytest (backend), React/TypeScript (frontend), Docker Compose (build).

## Global Constraints

- Model default **`base.en`**, configurable via `WHISPER_MODEL`. Downloaded via `models/download-ggml-model.sh` → `ggml-base.en.bin` (~142 MiB).
- Binary path default **`/usr/local/bin/whisper-cli`**; model dir default **`/opt/whisper/models`**.
- Per-transcription timeout **`WHISPER_TIMEOUT=60`** (seconds); max concurrent transcriptions **`WHISPER_MAX_CONCURRENCY=1`** on CPU (memory guard).
- whisper.cpp builds with **CMake** (current, 2026): CPU = `cmake -B build && cmake --build build -j --config Release`; CUDA = `cmake -B build -DGGML_CUDA=1 ...`. The old `make WHISPER_CUDA=1` flag is obsolete — do not use it.
- CUDA build is **opt-in** via `WHISPER_BACKEND=cuda` build-arg and must run on a GPU host with `--gpus all` (privileged). A CUDA-compiled binary does **NOT** fall back to CPU; without a GPU it errors and the chain catches it.
- Invocation is a **subprocess** to `whisper-cli` with `--output-txt -np` (suppress progress bars so stdout is only the transcript).
- **No new backend Python dependencies** — subprocess only.
- Chain order is immutable: **whisper.cpp → OpenAI Whisper → browser-native**.
- `POST /api/v1/audio/transcribe` and `POST /api/v1/voice/transcribe` keep their request/response contracts; only engine *selection* changes.
- When no server STT is available the backend returns HTTP 503 with `code: "STT_UNAVAILABLE"`, `detail: {"fallback": "browser"}` so the frontend knows to switch.

---

## File Structure

**Create**
- `backend/services/whisper_cpp_service.py` — `WhisperCppService` (is_available, transcribe, GPU probe, concurrency lock), `LocalSTTError`, `get_whisper_cpp_service()` singleton.
- `backend/tests/unit/test_whisper_cpp_service.py` — unit tests, `subprocess.run` mocked.
- `backend/tests/unit/test_audio_service_transcribe_chain.py` — unit tests for the AudioService fallback chain.
- `backend/tests/unit/test_stt_route_envelope.py` — unit tests for the 503 envelope + `/status` reporting (standalone FastAPI, mirrors `backend/tests/test_error_responses.py`).
- `voice-bridge/tests/test_stt_relay.py` — unit test for the bridge's backend-relay + Vosk net (urllib mocked).

**Modify**
- `backend/core/exceptions.py` — add `LocalSTTError` (plain `Exception`) and `ServerSTTUnavailable(ServiceUnavailableError)`.
- `backend/services/audio_service.py` — refactor `transcribe()` into the chain; add `_transcribe_openai()`; update `is_available()` and `get_status()`.
- `backend/api/routes/audio.py` — re-raise `ServerSTTUnavailable` in `transcribe_audio`.
- `backend/api/routes/voice.py` — re-raise `ServerSTTUnavailable` in `transcribe_audio`; update `check_voice_available()` + `GET /status` + `GET /enhanced-status` to report `whisper_cpp`.
- `backend/Dockerfile` — add whisper.cpp CPU + CUDA build stages; copy binary + model into the runtime.
- `voice-bridge/main.py` — `_listen_sync()` relays captured audio to the backend; keep Vosk as offline net; add `STT_BACKEND_URL` config.
- `frontend/src/services/voiceApi.ts` — `transcribe()` falls back to `localVoice` on `STT_UNAVAILABLE`; `checkStatus()` recognizes the `whisper_cpp` provider.

---

### Task 1: Exceptions + WhisperCppService module

**Files:**
- Modify: `backend/core/exceptions.py`
- Create: `backend/services/whisper_cpp_service.py`
- Test: `backend/tests/unit/test_whisper_cpp_service.py`

**Interfaces:**
- Consumes: env vars `WHISPER_CPP_BIN`, `WHISPER_MODEL`, `WHISPER_MODEL_DIR`, `WHISPER_TIMEOUT`, `WHISPER_MAX_CONCURRENCY`.
- Produces: `WhisperCppService.is_available() -> bool`, `WhisperCppService.transcribe(audio_bytes: bytes, language: str | None) -> str` (raises `LocalSTTError`), `get_whisper_cpp_service() -> WhisperCppService`, `LocalSTTError`. Later tasks import these exact names.

- [ ] **Step 1: Add the two exceptions**

In `backend/core/exceptions.py`, after `ServiceUnavailableError` (line 72), add:

```python
class LocalSTTError(Exception):
    """Local whisper.cpp STT failed (binary/model missing, crash, timeout).

    Internal — not an HTTP error. The caller's fallback chain converts it
    into a user-facing signal.
    """


class ServerSTTUnavailable(ServiceUnavailableError):
    """No server-side STT engine (whisper.cpp nor OpenAI) is available.

    The frontend should fall back to the browser-native Web Speech API.
    Rendered by the global handler as HTTP 503 with code STT_UNAVAILABLE.
    """
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/unit/test_whisper_cpp_service.py`:

```python
import asyncio
import subprocess
from pathlib import Path
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


def test_parse_stdout(svc):
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


def test_nonzero_exit_raises(svc):
    with patch("asyncio.to_thread", side_effect=lambda f, *a, **k: f(*a, **k)), \
         patch("subprocess.run", return_value=_fake_proc(returncode=1, stderr="boom")):
        with pytest.raises(LocalSTTError):
            asyncio.run(svc.transcribe(b"data"))


def test_timeout_raises(svc):
    def _raise(*a, **k):
        raise subprocess.TimeoutExpired(cmd="whisper-cli", timeout=1)

    with patch("asyncio.to_thread", side_effect=_raise):
        with pytest.raises(LocalSTTError):
            asyncio.run(svc.transcribe(b"data"))


def test_empty_output_raises(svc):
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_whisper_cpp_service.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: backend.services.whisper_cpp_service` (module not created yet).

- [ ] **Step 4: Write the module**

Create `backend/services/whisper_cpp_service.py`:

```python
"""Local speech-to-text via whisper.cpp (whisper-cli subprocess).

Primary STT engine for Agentium. Runs the compiled ``whisper-cli`` binary
and parses its stdout. The caller's fallback chain (see
``backend.services.audio_service.AudioService.transcribe``) moves on to
OpenAI / browser-native when this raises ``LocalSTTError``.
"""
from __future__ import annotations

import asyncio
import ctypes
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config (env, with defaults) ──────────────────────────────────────────────
WHISPER_CPP_BIN = os.getenv("WHISPER_CPP_BIN", "/usr/local/bin/whisper-cli")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base.en")
WHISPER_MODEL_DIR = os.getenv("WHISPER_MODEL_DIR", "/opt/whisper/models")
WHISPER_TIMEOUT = float(os.getenv("WHISPER_TIMEOUT", "60"))
WHISPER_MAX_CONCURRENCY = int(os.getenv("WHISPER_MAX_CONCURRENCY", "1"))


class LocalSTTError(Exception):
    """whisper.cpp local STT failed (missing binary/model, crash, timeout)."""


def _model_path() -> Path:
    return Path(WHISPER_MODEL_DIR) / f"ggml-{WHISPER_MODEL}.bin"


def _gpu_available() -> bool:
    """Best-effort: is an NVIDIA GPU usable at runtime?

    A privileged container run with ``--gpus all`` has nvidia-container-toolkit
    mount ``/dev/nvidia0`` and ``libcuda.so.1``. Without them this is False.
    """
    if not os.path.exists("/dev/nvidia0"):
        return False
    try:
        ctypes.CDLL("libcuda.so.1")
        return True
    except OSError:
        return False


class WhisperCppService:
    def __init__(self) -> None:
        self._lock: Optional[asyncio.Lock] = None
        self._gpu = _gpu_available()
        logger.info(
            "[STT] whisper.cpp backend=%s bin=%s model=%s",
            "GPU" if self._gpu else "CPU", WHISPER_CPP_BIN, WHISPER_MODEL,
        )

    def is_available(self) -> bool:
        return Path(WHISPER_CPP_BIN).is_file() and _model_path().is_file()

    async def transcribe(
        self, audio_bytes: bytes, language: Optional[str] = None
    ) -> str:
        if not self.is_available():
            raise LocalSTTError("whisper.cpp binary or model not found")

        # Serialize transcriptions so a CPU build doesn't OOM under load.
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            try:
                cmd = [
                    WHISPER_CPP_BIN, "-m", str(_model_path()),
                    "-f", tmp_path, "--output-txt", "-np",
                ]
                if language:
                    cmd += ["-l", language]
                try:
                    proc = await asyncio.to_thread(
                        subprocess.run, cmd,
                        text=True, capture_output=True, timeout=WHISPER_TIMEOUT,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise LocalSTTError(
                        f"whisper.cpp timed out after {WHISPER_TIMEOUT}s"
                    ) from exc
                if proc.returncode != 0:
                    raise LocalSTTError(
                        f"whisper-cli exited {proc.returncode}: {proc.stderr[:500]}"
                    )
                text = (proc.stdout or "").strip()
                if not text:
                    raise LocalSTTError("whisper.cpp returned empty transcription")
                return text
            finally:
                Path(tmp_path).unlink(missing_ok=True)


_service: Optional[WhisperCppService] = None


def get_whisper_cpp_service() -> WhisperCppService:
    """Return the singleton WhisperCppService (lazy init)."""
    global _service
    if _service is None:
        _service = WhisperCppService()
    return _service
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_whisper_cpp_service.py -v --no-cov`
Expected: PASS (all 9 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/core/exceptions.py backend/services/whisper_cpp_service.py backend/tests/unit/test_whisper_cpp_service.py
git commit -m "feat(stt): add whisper.cpp local STT service + exceptions"
```

---

### Task 2: Backend Dockerfile — whisper.cpp build stages

**Files:**
- Modify: `backend/Dockerfile`

**Interfaces:**
- Consumes: `WHISPER_MODEL` (build-arg, default `base.en`), `WHISPER_BACKEND` (build-arg, `cpu`|`cuda`).
- Produces: `/usr/local/bin/whisper-cli` and `/opt/whisper/models/ggml-base.en.bin` present in the runtime image.

- [ ] **Step 1: Add the CPU whisper.cpp builder stage**

Insert this new stage **after** the existing `builder` stage (after the `COPY requirements.txt .` / `pip install` lines, before the `Production Stage` comment):

```dockerfile
# ── whisper.cpp (CPU) ─────────────────────────────────────────────────────
# whisper.cpp builds with CMake (2026). The Makefile only has demo targets;
# "CUDA needs CMake". CPU build runs on any host (no GPU required).
FROM python:3.11-slim-bookworm AS whisper-cpp
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git \
    && rm -rf /var/lib/apt/lists/*
ARG WHISPER_MODEL=base.en
RUN git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git /whisper.cpp \
    && cd /whisper.cpp \
    && cmake -B build \
    && cmake --build build -j --config Release \
    && bash ./models/download-ggml-model.sh ${WHISPER_MODEL} \
    && mkdir -p /opt/whisper/models \
    && cp models/ggml-${WHISPER_MODEL}.bin /opt/whisper/models/ \
    && cp ./build/bin/whisper-cli /usr/local/bin/whisper-cli
```

- [ ] **Step 2: Add the optional CUDA builder stage**

Insert immediately after the CPU stage above:

```dockerfile
# ── whisper.cpp (CUDA, opt-in) ──────────────────────────────────────────
# Only used when WHISPER_BACKEND=cuda. Requires a GPU host run with
# --gpus all. A CUDA-compiled binary does NOT fall back to CPU.
FROM nvidia/cuda:12.4.0-devel-ubuntu22.04 AS whisper-cpp-cuda
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git \
    && rm -rf /var/lib/apt/lists/*
ARG WHISPER_MODEL=base.en
RUN git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git /whisper.cpp \
    && cd /whisper.cpp \
    && cmake -B build -DGGML_CUDA=1 \
    && cmake --build build -j --config Release \
    && bash ./models/download-ggml-model.sh ${WHISPER_MODEL}
```

- [ ] **Step 3: Select the stage and copy artifacts into the runtime**

At the top of the **Production Stage** (`FROM python:3.11-slim-bookworm@...` line, currently line 45), add the build-arg and a `FROM ... AS whisper-cpp-src` alias that points at the chosen builder:

```dockerfile
ARG WHISPER_BACKEND=cpu
FROM whisper-cpp AS whisper-cpp-src
FROM python:3.11-slim-bookworm@${PYTHON_DIGEST}
```

Then, inside the Production Stage **after** the `COPY --from=builder /opt/venv /opt/venv` line, add:

```dockerfile
# whisper.cpp binary + model (from the stage chosen by WHISPER_BACKEND)
COPY --from=whisper-cpp-src /usr/local/bin/whisper-cli /usr/local/bin/whisper-cli
COPY --from=whisper-cpp-src /opt/whisper /opt/whisper
```

Note: when `WHISPER_BACKEND=cuda`, the CUDA builder also needs its runtime `.so` files copied (resolve the exact set — `libcudart.so*`, `libcublas*`, `libcufft*`, `libcurand*`, `libcublasLt*` — from `/usr/local/cuda/lib64` of that stage) so the slim runtime can `dlopen` them once `--gpus all` mounts `libcuda`.

- [ ] **Step 4: Build the default (CPU) image and smoke-test**

Run: `docker compose build backend`
Expected: build succeeds; the final backend image contains the binary + model.
Then verify the binary + model exist and one short transcription works:

```bash
docker compose run --rm backend bash -c \
  "test -x /usr/local/bin/whisper-cli && \
   test -f /opt/whisper/models/ggml-base.en.bin && \
   echo BUILD_OK"
```

(For a full transcription smoke test, mount a tiny `*.wav` and run
`whisper-cli -m /opt/whisper/models/ggml-base.en.bin -f sample.wav --output-txt -np`.)

- [ ] **Step 5: Commit**

```bash
git add backend/Dockerfile
git commit -m "build: compile whisper.cpp (CPU default, CUDA opt-in) into backend"
```

---

### Task 3: AudioService transcribe chain

**Files:**
- Modify: `backend/services/audio_service.py` (transcribe at lines 104-158, is_available at 86-88, get_status at 90-100)
- Test: `backend/tests/unit/test_audio_service_transcribe_chain.py`

**Interfaces:**
- Consumes: `get_whisper_cpp_service()` and `WhisperCppService.transcribe` / `.is_available` (Task 1); `AudioService._get_openai_api_key` (existing).
- Produces: `AudioService.transcribe(db, user_id, audio_bytes, language=None, filename="audio.wav") -> str` — now returns whisper.cpp text first, then OpenAI, then raises `ServerSTTUnavailable`. `AudioService.is_available` and `.get_status` report `whisper_cpp` as primary when present.

- [ ] **Step 1: Write the failing chain test**

Create `backend/tests/unit/test_audio_service_transcribe_chain.py`:

```python
import asyncio
from unittest.mock import patch, MagicMock

import pytest

from backend.core.exceptions import ServerSTTUnavailable
from backend.services.audio_service import AudioService
from backend.services.whisper_cpp_service import LocalSTTError


def _whisper_svc(available=True, text="local transcript"):
    svc = MagicMock()
    svc.is_available.return_value = available
    svc.transcribe.return_value = text
    return svc


@pytest.fixture
def svc():
    return AudioService()


def test_whisper_primary_used_when_available(svc):
    with patch(
        "backend.services.audio_service.get_whisper_cpp_service",
        return_value=_whisper_svc(available=True),
    ), patch.object(AudioService, "_get_openai_api_key", return_value=None):
        result = asyncio.run(svc.transcribe(db=MagicMock(), user_id="u", audio_bytes=b"x"))
    assert result == "local transcript"


def test_whisper_failure_falls_back_to_openai(svc):
    w = _whisper_svc(available=True)
    w.transcribe.side_effect = LocalSTTError("crash")
    with patch(
        "backend.services.audio_service.get_whisper_cpp_service", return_value=w
    ), patch.object(
        AudioService, "_get_openai_api_key", return_value="sk-test"
    ), patch.object(
        AudioService, "_transcribe_openai", return_value="openai transcript"
    ):
        result = asyncio.run(svc.transcribe(db=MagicMock(), user_id="u", audio_bytes=b"x"))
    assert result == "openai transcript"


def test_openai_used_when_whisper_unavailable(svc):
    with patch(
        "backend.services.audio_service.get_whisper_cpp_service",
        return_value=_whisper_svc(available=False),
    ), patch.object(
        AudioService, "_get_openai_api_key", return_value="sk-test"
    ), patch.object(
        AudioService, "_transcribe_openai", return_value="openai transcript"
    ):
        result = asyncio.run(svc.transcribe(db=MagicMock(), user_id="u", audio_bytes=b"x"))
    assert result == "openai transcript"


def test_no_engine_raises_server_stt_unavailable(svc):
    with patch(
        "backend.services.audio_service.get_whisper_cpp_service",
        return_value=_whisper_svc(available=False),
    ), patch.object(AudioService, "_get_openai_api_key", return_value=None):
        with pytest.raises(ServerSTTUnavailable):
            asyncio.run(svc.transcribe(db=MagicMock(), user_id="u", audio_bytes=b"x"))


def test_is_available_true_when_whisper_present(svc):
    with patch(
        "backend.services.audio_service.get_whisper_cpp_service",
        return_value=_whisper_svc(available=True),
    ):
        assert svc.is_available(db=MagicMock(), user_id="u") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_audio_service_transcribe_chain.py -v --no-cov`
Expected: FAIL — `AttributeError: 'AudioService' object has no attribute '_transcribe_openai'` (or `ServerSTTUnavailable` not raised yet).

- [ ] **Step 3: Refactor audio_service.py**

Add the import at the top of `backend/services/audio_service.py` (near the other imports):

```python
from backend.services.whisper_cpp_service import (
    get_whisper_cpp_service,
    LocalSTTError,
)
from backend.core.exceptions import ServerSTTUnavailable
```

Replace the existing `transcribe()` method (lines 104-158) with:

```python
    async def transcribe(
        self,
        db: Session,
        user_id: str,
        audio_bytes: bytes,
        language: Optional[str] = None,
        filename: str = "audio.wav",
    ) -> str:
        """
        Transcribe audio bytes to text.

        Server-side chain (backend-owned):
          1. Local whisper.cpp (PRIMARY, no API key needed)
          2. OpenAI Whisper (if an API key is configured)
          3. raise ServerSTTUnavailable -> frontend falls back to browser

        Raises:
            ServerSTTUnavailable: No server STT engine is available.
        """
        # 1. Local whisper.cpp (PRIMARY)
        whisper = get_whisper_cpp_service()
        if whisper.is_available():
            try:
                return await whisper.transcribe(audio_bytes, language)
            except LocalSTTError as exc:
                logger.warning("[STT] local whisper.cpp failed: %s — falling back", exc)

        # 2. OpenAI Whisper (if a key is configured)
        api_key = self._get_openai_api_key(db, user_id)
        if api_key:
            return await self._transcribe_openai(db, user_id, audio_bytes, language, filename)

        # 3. Nothing server-side available
        raise ServerSTTUnavailable(
            "No server STT engine available",
            code="STT_UNAVAILABLE",
            detail={"fallback": "browser"},
        )
```

Add the extracted OpenAI helper (move the existing OpenAI logic out of the old `transcribe`):

```python
    async def _transcribe_openai(
        self,
        db: Session,
        user_id: str,
        audio_bytes: bytes,
        language: Optional[str] = None,
        filename: str = "audio.wav",
    ) -> str:
        """Transcribe via OpenAI Whisper (requires an API key)."""
        api_key = self._get_openai_api_key(db, user_id)
        if not api_key:
            raise ValueError("No OpenAI API key configured for voice features")

        if len(audio_bytes) > MAX_AUDIO_SIZE:
            raise ValueError(
                f"Audio too large: {len(audio_bytes)} bytes "
                f"(max {MAX_AUDIO_SIZE} bytes)"
            )

        client = self._get_openai_client(api_key)

        suffix = Path(filename).suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as audio_file:
                kwargs: Dict[str, Any] = {
                    "model": "whisper-1",
                    "file": audio_file,
                }
                if language:
                    kwargs["language"] = language
                transcript = client.audio.transcriptions.create(**kwargs)
                return transcript.text
        finally:
            Path(tmp_path).unlink(missing_ok=True)
```

Update `is_available()` (lines 86-88) to:

```python
    def is_available(self, db: Session, user_id: str) -> bool:
        """Server STT available if whisper.cpp OR an OpenAI key is present."""
        if get_whisper_cpp_service().is_available():
            return True
        return self._get_openai_api_key(db, user_id) is not None
```

Update `get_status()` (lines 90-100) to report whisper.cpp as primary:

```python
    def get_status(self, db: Session, user_id: str) -> Dict[str, Any]:
        """Detailed availability status."""
        whisper_available = get_whisper_cpp_service().is_available()
        key = self._get_openai_api_key(db, user_id)
        provider = "whisper_cpp" if whisper_available else ("openai" if key else None)
        return {
            "available": provider is not None,
            "provider": provider,
            "whisper_cpp_available": whisper_available,
            "stt_model": "ggml-base.en" if whisper_available else "whisper-1",
            "tts_model": "tts-1",
            "voices": AVAILABLE_TTS_VOICES,
            "max_audio_size_mb": MAX_AUDIO_SIZE // (1024 * 1024),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_audio_service_transcribe_chain.py -v --no-cov`
Expected: PASS (all 5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/audio_service.py backend/tests/unit/test_audio_service_transcribe_chain.py
git commit -m "feat(stt): AudioService.transcribe chain whisper.cpp -> OpenAI"
```

---

### Task 4: Route mapping + status reporting

**Files:**
- Modify: `backend/api/routes/audio.py` (transcribe_audio), `backend/api/routes/voice.py` (transcribe_audio, check_voice_available, GET /status, GET /enhanced-status)
- Test: `backend/tests/unit/test_stt_route_envelope.py`

**Interfaces:**
- Consumes: `AudioService.transcribe` raising `ServerSTTUnavailable`; `get_whisper_cpp_service().is_available()`; `ServerSTTUnavailable` (Task 1).
- Produces: `POST /audio/transcribe` and `POST /voice/transcribe` re-raise `ServerSTTUnavailable` (→ 503, `code: STT_UNAVAILABLE`, `detail.fallback: browser`); `GET /voice/status` reports `provider: whisper_cpp` when local STT is available independent of an OpenAI key.

> **Critical gap closed here:** the existing `check_voice_available()` only reports availability when an **OpenAI key** exists. Without this task the frontend's `checkStatus()` (which hits `/voice/status`, *not* `/enhanced-status`) would still say "unavailable" even though whisper.cpp is the key-free primary. Update `check_voice_available()` to consult whisper.cpp.

- [ ] **Step 1: Write the envelope + status test**

Create `backend/tests/unit/test_stt_route_envelope.py` (mirrors `backend/tests/test_error_responses.py` — standalone FastAPI, no DB):

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.error_responses import register_error_handlers
from backend.core.exceptions import ServerSTTUnavailable
from backend.services.audio_service import AudioService


@pytest.fixture
def client():
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/api/v1/audio/transcribe")
    async def _transcribe():
        # Mirror audio.py: AudioService.transcribe raises ServerSTTUnavailable
        # when no server engine is available; the route must re-raise it
        # (NOT wrap it in a 500 InternalServerError).
        raise ServerSTTUnavailable(
            "No server STT engine available",
            code="STT_UNAVAILABLE",
            detail={"fallback": "browser"},
        )

    return TestClient(app)


def test_server_stt_unavailable_envelope(client):
    resp = client.post("/api/v1/audio/transcribe")
    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == "STT_UNAVAILABLE"
    assert body["detail"] == {"fallback": "browser"}


def test_check_voice_available_reports_whisper_without_key():
    from backend.api.routes import voice as voice_route

    with pytest.MonkeyPatch().context() as mp:
        # check_voice_available imports get_whisper_cpp_service *inside* the
        # function, so patch the name on its source module.
        mp.setattr(
            "backend.services.whisper_cpp_service.get_whisper_cpp_service",
            lambda: _fake_whisper(available=True),
        )
        status = voice_route.check_voice_available(db=_FakeDB(), user_id="u")
    assert status["available"] is True
    assert status["provider"] == "whisper_cpp"


class _FakeDB:
    pass


def _fake_whisper(available: bool):
    class _S:
        def is_available(self):
            return available
    return _S()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_stt_route_envelope.py -v --no-cov`
Expected: FAIL — `AttributeError: module 'backend.core.exceptions' has no attribute 'register_error_handlers'` (need to confirm the real import name) **and** `check_voice_available` does not yet consult whisper.cpp.

- [ ] **Step 3: Update the routes**

In `backend/api/routes/audio.py`, add the import and re-raise **before** the broad `except Exception`. Near the other exception imports add:

```python
from backend.core.exceptions import ServerSTTUnavailable
```

Inside `transcribe_audio`, change the `try/except` so `ServerSTTUnavailable` propagates (the global handler renders it as 503). Insert **before** `except Exception as exc:`:

```python
    except ServerSTTUnavailable:
        raise  # let the global handler return 503 + STT_UNAVAILABLE
```

In `backend/api/routes/voice.py`:
- Add `from backend.core.exceptions import ServerSTTUnavailable` near the other `from backend.core.exceptions import ...` line.
- In `transcribe_audio`, insert `except ServerSTTUnavailable: raise` **before** the `except Exception as exc:` block.
- Update `check_voice_available()` so whisper.cpp is reported even without an OpenAI key. At the top of the function add the whisper check:

```python
    from backend.services.whisper_cpp_service import get_whisper_cpp_service

    if get_whisper_cpp_service().is_available():
        return {
            "available": True,
            "message": "Local whisper.cpp STT ready",
            "provider": "whisper_cpp",
        }
```

(Keep the existing OpenAI-key branch below it for the `openai` provider case.)

- Update `GET /enhanced-status` (`get_enhanced_voice_status`): add a `whisper_cpp` block to the returned dict and set `recommended`/`current` to `whisper_cpp` when available. After building the `openai_status`, compute:

```python
    from backend.services.whisper_cpp_service import get_whisper_cpp_service
    whisper_available = get_whisper_cpp_service().is_available()
    return {
        "whisper_cpp": {
            "available": whisper_available,
            "message": "Local whisper.cpp STT (primary)" if whisper_available
                       else "whisper.cpp not built into this image",
            "supports_recognition": whisper_available,
        },
        "openai": {
            "available": openai_status["available"],
            "message": openai_status["message"],
            "action_required": openai_status.get("action_required"),
        },
        "local": {
            "available": True,
            "message": "Browser-native Web Speech API (fallback)",
            "supports_recognition": True,
            "supports_synthesis": True,
        },
        "recommended": "whisper_cpp" if whisper_available else ("openai" if openai_status["available"] else "local"),
        "current": "whisper_cpp" if whisper_available else ("openai" if openai_status["available"] else "local"),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_stt_route_envelope.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/audio.py backend/api/routes/voice.py backend/tests/unit/test_stt_route_envelope.py
git commit -m "feat(stt): route envelope + status reporting for whisper.cpp"
```

---

### Task 5: Host voice-bridge relays to backend

**Files:**
- Modify: `voice-bridge/main.py` (`_listen_sync`, config block ~lines 89-117)
- Test: `voice-bridge/tests/test_stt_relay.py`

**Interfaces:**
- Consumes: backend `POST /api/v1/audio/transcribe` (accepts multipart `audio`, returns `{"text": ...}`); existing `VOSK_MODEL_PATH` + `_recognize_with_vosk()`.
- Produces: `_listen_sync()` returns text from the backend when reachable, falling back to Vosk if the HTTP call fails. New config `STT_BACKEND_URL`.

- [ ] **Step 1: Write the failing relay test**

Create `voice-bridge/tests/test_stt_relay.py`:

```python
import io
import json
import urllib.error
from unittest.mock import patch, MagicMock

import pytest

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main as bridge


def _audio_wav() -> bytes:
    # Minimal non-empty bytes standing in for WAV audio.
    return b"RIFF....WAVEfmt "


def test_relay_returns_backend_text(monkeypatch):
    captured = {}

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = req.data
        resp = MagicMock()
        resp.read.return_value = json.dumps({"text": "hello from backend"}).encode()
        resp.__enter__.return_value = resp
        return resp

    monkeypatch.setattr(bridge, "STT_BACKEND_URL", "http://127.0.0.1:8000/api/v1/audio/transcribe")
    with patch("urllib.request.urlopen", _fake_urlopen):
        result = bridge._transcribe_via_backend(_audio_wav())
    assert result == "hello from backend"
    assert "audio/transcribe" in captured["url"]


def test_relay_falls_back_to_vosk_on_http_error(monkeypatch):
    def _raise(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(bridge, "STT_BACKEND_URL", "http://127.0.0.1:8000/api/v1/audio/transcribe")
    with patch("urllib.request.urlopen", _raise), \
         patch.object(bridge, "_recognize_with_vosk", return_value="vosk text"):
        result = bridge._transcribe_via_backend(_audio_wav())
    assert result == "vosk text"
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `voice-bridge/`): `python -m pytest tests/test_stt_relay.py -v`
Expected: FAIL — `ImportError`/`AttributeError: module 'main' has no attribute '_transcribe_via_backend'`.

- [ ] **Step 3: Add config + relay function to main.py**

In the config block (after `VOSK_MODEL_PATH`, ~line 110), add:

```python
# ── Backend STT relay (B/whisper.cpp) ─────────────────────────────────────
# The host bridge captures mic audio and relays it to the backend, which now
# runs whisper.cpp locally. Falls back to the offline Vosk model only if the
# backend STT call fails (backend unreachable / whisper.cpp missing).
STT_BACKEND_URL: str = _conf.get(
    "STT_BACKEND_URL", os.getenv("STT_BACKEND_URL", f"{BACKEND_URL}/api/v1/audio/transcribe")
)
```

Add the relay helper near `_recognize_with_vosk`:

```python
def _transcribe_via_backend(audio_wav: bytes) -> Optional[str]:
    """
    Relay WAV audio bytes to the backend's whisper.cpp STT endpoint.

    Returns the transcript string, or None if the backend call fails (in
    which case the caller falls back to the offline Vosk model). The backend
    requires an authenticated user; the bridge sends its VOICE_TOKEN.
    """
    import urllib.request
    import urllib.error

    if not VOICE_TOKEN:
        logger.debug("[bridge] No VOICE_TOKEN — cannot call backend STT")
        return None
    try:
        req = urllib.request.Request(
            STT_BACKEND_URL,
            data=audio_wav,
            headers={
                "Content-Type": "audio/wav",
                "Authorization": f"Bearer {VOICE_TOKEN}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=WHISPER_RELAY_TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
            text = (body.get("text") or "").strip()
            return text or None
    except Exception as exc:
        logger.warning("[WARN] Backend STT relay failed: %s — using Vosk", exc)
        return None
```

Add the timeout constant near the other session constants:

```python
WHISPER_RELAY_TIMEOUT: float = float(_conf.get("WHISPER_RELAY_TIMEOUT", os.getenv("WHISPER_RELAY_TIMEOUT", "30.0")))
```

- [ ] **Step 4: Wire relay into `_listen_sync`**

In `_listen_sync`, replace the Google STT block (the `try: text = recognizer.recognize_google(audio) ... except sr.RequestError` block, lines 359-377) with a relay to the backend, keeping Vosk as the offline net:

```python
    logger.debug("[bridge] Audio captured, sending to backend STT (whisper.cpp)…")
    audio_wav = audio.get_wav_data()
    text = _transcribe_via_backend(audio_wav)
    if text:
        logger.info("[bridge] STT result (backend whisper.cpp): '%s'", text)
        return text
    # Backend STT unreachable — fall back to the offline Vosk model.
    logger.warning("[WARN] Backend STT unavailable — trying offline Vosk")
    fallback_text = _recognize_with_vosk(audio)
    if fallback_text:
        logger.info("[bridge] STT result (Vosk fallback): '%s'", fallback_text)
        return fallback_text
    logger.warning("[WARN] Offline fallback unavailable or produced no result")
    return None
```

- [ ] **Step 5: Run test to verify it passes**

Run (from `voice-bridge/`): `python -m pytest tests/test_stt_relay.py -v`
Expected: PASS (relay returns backend text; Vosk net on HTTP error).

- [ ] **Step 6: Commit**

```bash
git add voice-bridge/main.py voice-bridge/tests/test_stt_relay.py
git commit -m "feat(stt): host bridge relays mic audio to backend whisper.cpp"
```

---

### Task 6: Frontend fallback trigger

**Files:**
- Modify: `frontend/src/services/voiceApi.ts` (`transcribe`, `checkStatus`)

**Interfaces:**
- Consumes: `POST ${API_BASE}/transcribe` (backend) may return 503 `STT_UNAVAILABLE`; `localVoice.transcribe(...)` (browser-native, callback API); `localVoice.checkAvailability()`.
- Produces: `voiceApi.transcribe()` resolves with browser transcript when the backend signals `STT_UNAVAILABLE`; `voiceApi.checkStatus()` sets `provider: 'whisper_cpp'` when the backend reports it.

> **Note on verification:** the repo's primary test runner is pytest (backend). If the frontend has no configured unit-test runner, verify this task manually via `make up` + the browser dev console, and rely on Task 3's chain test for behavioral coverage. Do not skip the code change.

- [ ] **Step 1: Update `checkStatus` to recognize `whisper_cpp`**

In `voiceApi.ts` `checkStatus` (around line 102), change the OpenAI branch so the `whisper_cpp` provider is treated like `openai`:

```typescript
    // Step 1: Ask the backend
    try {
      const response = await api.get<VoiceStatus>(`${API_BASE}/status`);
      if (response.data.available && (response.data.provider === 'openai' || response.data.provider === 'whisper_cpp')) {
        cachedStatus = { ...response.data, provider: response.data.provider };
        statusCacheTime = now;
        return cachedStatus;
      }
    } catch {
      // Backend unreachable — fall through to local
    }
```

- [ ] **Step 2: Make `transcribe` fall back to browser-native on `STT_UNAVAILABLE`**

Replace the `transcribe` function (lines 161-177) with one that detects the 503 signal and falls back to `localVoice`:

```typescript
  transcribe: async (
    audioBlob: Blob,
    language?: string,
  ): Promise<TranscribeResponse> => {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    if (language) {
      formData.append('language', normaliseLang(language));
    }

    try {
      const response = await api.post<TranscribeResponse>(
        `${API_BASE}/transcribe`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      );
      return response.data;
    } catch (err: any) {
      // Backend signals no server STT (whisper.cpp + OpenAI both down):
      // fall back to the browser-native Web Speech API.
      const code = err?.response?.data?.code;
      if (code === 'STT_UNAVAILABLE') {
        const text = await _transcribeWithLocalVoice(language);
        return { text, provider: 'local' } as TranscribeResponse;
      }
      throw err;
    }
  },
```

Add the local-voice helper that wraps `localVoice.transcribe`'s callback API in a Promise (place it just above the `voiceApi` object):

```typescript
/**
 * Wrap the browser-native localVoice callback API in a Promise so the
 * transcribe() fallback can await a single transcript string.
 */
function _transcribeWithLocalVoice(language?: string): Promise<string> {
  return new Promise((resolve, reject) => {
    localVoice.transcribe(
      (result) => {
        if (result.isFinal) resolve(result.text);
      },
      (error) => reject(new Error(error)),
      language ?? 'en-US',
    );
  });
}
```

- [ ] **Step 3: Type-check the frontend**

Run (from `frontend/`): `npx tsc --noEmit` (or the project's configured `npm run build` / `lint`).
Expected: no type errors in `voiceApi.ts`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/services/voiceApi.ts
git commit -m "feat(stt): frontend falls back to browser-native on STT_UNAVAILABLE"
```

---

### Task 7: Integration test — OpenAI leg via FakeProviderServer

**Files:**
- Create: `backend/tests/integration/test_stt_fallback_integration.py`

**Interfaces:**
- Consumes: `FakeProviderServer` + `make_fake_config` from `backend/tests/integration/test_provider_resilience.py`; `AudioService.transcribe`; `seeded_db` fixture (integration conftest).
- Produces: an integration test proving the `whisper unavailable → OpenAI` leg of the chain hits the real OpenAI SDK path pointed at the fake server.

> Requires running services (`make up` / docker-compose stack) and is marked `@pytest.mark.integration`. Run with `pytest backend/tests/integration/test_stt_fallback_integration.py -v -m integration`.

- [ ] **Step 1: Write the integration test**

```python
"""Integration: whisper.cpp unavailable -> OpenAI Whisper leg of the chain.

Drives the REAL OpenAI SDK through AudioService._transcribe_openai against
the FakeProviderServer (reused from test_provider_resilience.py), with the
local whisper.cpp leg disabled by patching is_available() -> False.
"""
import pytest
from sqlalchemy.orm import Session

from backend.services.audio_service import AudioService
from backend.tests.integration.test_provider_resilience import (
    FakeProviderServer,
    make_fake_config,
    _delete_fake_configs,
)
from backend.services.whisper_cpp_service import get_whisper_cpp_service


@pytest.mark.integration
class TestWhisperDownFallsBackToOpenAI:
    def test_openai_leg_used_when_whisper_unavailable(self, seeded_db: Session, monkeypatch):
        srv = FakeProviderServer(default_status=200)
        created = []
        try:
            cfg = make_fake_config(srv.base_url, rpm=100000)
            created.append(str(cfg.id))

            # Disable the local whisper.cpp leg so the chain must use OpenAI.
            monkeypatch.setattr(
                get_whisper_cpp_service(), "is_available", lambda: False
            )

            svc = AudioService()
            text = svc.transcribe(
                db=seeded_db, user_id="sovereign",
                audio_bytes=b"RIFF....", language="en",
            )
            assert text == "ok"  # FakeProviderServer returns "ok"
            assert srv.hits() >= 1
        finally:
            srv.shutdown()
            _delete_fake_configs(created)
```

- [ ] **Step 2: Run it against the stack**

Run: `pytest backend/tests/integration/test_stt_fallback_integration.py -v -m integration`
Expected: PASS (chain uses the OpenAI leg and the fake server returns "ok").

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_stt_fallback_integration.py
git commit -m "test(stt): integration coverage for whisper-down -> OpenAI fallback"
```

---

### Task 8: Final verification + docs

**Files:**
- Read: `README.md` (voice section), `docs/documents/todo.md` (if a voice task is tracked there)

**Interfaces:**
- Consumes: all tasks above.

- [ ] **Step 1: Run the full backend unit suite**

Run: `pytest backend/tests/unit -v --no-cov`
Expected: PASS (includes the 3 new unit test files). Note: the repo's `pytest.ini` enforces `--cov-fail-under=20`; run the full `pytest` (no `--no-cov`) in CI to honour that gate.

- [ ] **Step 2: Document the new env vars in README**

In `README.md`'s voice/STT section, add a short paragraph:

```markdown
### Local Speech-to-Text (whisper.cpp)

Agentium builds [whisper.cpp](https://github.com/ggerganov/whisper.cpp) into the
backend image and uses it as the **primary** STT engine — no API key required.
Fallback chain: `whisper.cpp → OpenAI Whisper (if a key is set) → browser-native`.
Configurable env vars: `WHISPER_MODEL` (default `base.en`), `WHISPER_CPP_BIN`,
`WHISPER_MODEL_DIR`, `WHISPER_TIMEOUT` (default 60s), `WHISPER_MAX_CONCURRENCY`
(default 1). For GPU: build with `--build-arg WHISPER_BACKEND=cuda` and run
the backend with `--gpus all`.
```

- [ ] **Step 3: Final commit**

```bash
git add README.md
git commit -m "docs: document whisper.cpp local STT env vars"
```

- [ ] **Step 4: Push branch and open a draft PR**

```bash
git push -u origin worktree-feat+whisper-cpp-stt-design
gh pr create --draft --title "feat(stt): local whisper.cpp primary STT" \
  --body "Local whisper.cpp as primary STT (whisper.cpp -> OpenAI -> browser-native). See docs/superpowers/specs/2026-07-13-whisper-cpp-stt-design.md"
```
