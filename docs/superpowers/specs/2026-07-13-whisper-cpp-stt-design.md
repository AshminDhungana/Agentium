# Local whisper.cpp Speech-to-Text — Design Spec

**Date:** 2026-07-13
**Status:** Approved (design)
**Author:** Claude (brainstorming session with user)

## Goal

Replace the current "OpenAI Whisper if API key present, else browser-native"
STT arrangement with a production-ready **local** speech-recognition path built
on [whisper.cpp](https://github.com/ggerganov/whisper.cpp), in the spirit of
[meetily](https://github.com/Zackriya-Solutions/meetily).

New STT priority chain:

```
1. whisper.cpp  (local, in the backend container)   ← PRIMARY
2. OpenAI Whisper (cloud, if an OpenAI API key is configured)
3. Browser-native Web Speech API (frontend fallback)
```

whisper.cpp is built **into the backend container** at image build time. The
backend detects an NVIDIA GPU at runtime (privileged container + `--gpus all`)
and uses the CUDA backend; otherwise it runs on CPU. This keeps the topology
simple (no new service to orchestrate) and makes local, private, API-key-free
transcription the default.

## Current State (what this changes)

| Path | Today | After this spec |
|------|-------|-----------------|
| `voice-bridge/main.py` (host) | `speech_recognition` → Google Web Speech API, Vosk offline fallback | Captures mic, relays audio to backend `audio/transcribe` (whisper.cpp); Vosk kept as offline net |
| `backend/api/routes/voice.py` `POST /voice/transcribe` | OpenAI `whisper-1`, requires OpenAI key | Unchanged endpoint; server chain now tries local whisper.cpp first |
| `backend/api/routes/audio.py` `POST /audio/transcribe` | OpenAI `whisper-1`, requires OpenAI key | Server chain tries local whisper.cpp first |
| `frontend/src/services/localVoice.ts` | Browser-native Web Speech (final fallback) | Unchanged engine; now the explicit 3rd-tier fallback when backend reports no server STT |

Key facts established during exploration:
- `backend/Dockerfile` is two-stage: a `builder` (compiles a venv with **CPU
  torch**, sentence-transformers, chromadb) → lean `python:3.11-slim-bookworm`
  runtime that copies the venv. The image is currently **CPU-only and lean**.
- `AudioService.transcribe()` (`backend/services/audio_service.py:104`) does
  **only** OpenAI Whisper today and raises `ValueError` when no key is present.
  This is the insertion point for the local engine.

## Design Decisions (confirmed with user)

1. **Deploy target:** whisper.cpp compiled **inside the backend container**;
   exposed through `audio.py` → `AudioService.transcribe()`.
2. **Fallback ownership:** the **backend owns the server-side chain**
   (whisper.cpp → OpenAI). The frontend only steps in with browser-native when
   the backend returns `STT_UNAVAILABLE`.
3. **Build / GPU:** CPU build by default; optional CUDA build via build-arg
   `WHISPER_BACKEND=cuda`. Runtime GPU probe selects CUDA vs CPU inside
   whisper.cpp. Privileged container + `--gpus all` mounts `libcuda` so the GPU
   path activates automatically.
4. **Model:** default **`base.en`** (~140 MB, fast, good accuracy). Configurable
   via `WHISPER_MODEL`.
5. **Invocation:** backend calls the compiled `whisper-cli` binary via
   **subprocess**, parsing stdout. No Python bindings, no sidecar — simplest
   and most isolated (a crash cannot take down the app).
6. **Host voice-bridge:** kept as the desktop voice companion; relays mic audio
   to the backend for transcription; Vosk retained as an offline safety net.

## §1 — Build & Image Assembly

Modify `backend/Dockerfile` to add whisper.cpp. Two paths:

### Default (CPU)
A new stage clones whisper.cpp and builds the CPU binary:

```dockerfile
# ── whisper.cpp (CPU) ───────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS whisper-cpp
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git \
    && rm -rf /var/lib/apt/lists/*
ARG WHISPER_MODEL=base.en
RUN git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git /whisper.cpp \
    && cd /whisper.cpp \
    && make -j$(nproc) \
    && bash ./models/download-ggml-model.sh ${WHISPER_MODEL} \
    && mkdir -p /opt/whisper/models \
    && cp models/ggml-${WHISPER_MODEL}.bin /opt/whisper/models/ \
    && cp ./build/bin/whisper-cli /usr/local/bin/whisper-cli
```

`whisper-cli` and the model are then copied into the runtime stage:

```dockerfile
COPY --from=whisper-cpp /usr/local/bin/whisper-cli /usr/local/bin/whisper-cli
COPY --from=whisper-cpp /opt/whisper /opt/whisper
```

### Optional GPU (`WHISPER_BACKEND=cuda`)
A separate CUDA builder compiles with `WHISPER_CUDA=1`; the binary + CUDA
runtime `.so` files are copied into the lean runtime. At runtime, if the
container is privileged and run with `--gpus all`, nvidia-container-toolkit
mounts the driver's `libcuda` and whisper.cpp uses the GPU; otherwise it falls
back to CPU.

```dockerfile
ARG WHISPER_BACKEND=cpu
# only used when WHISPER_BACKEND=cuda
FROM nvidia/cuda:12.4.0-devel-ubuntu22.04 AS whisper-cpp-cuda
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git \
    && rm -rf /var/lib/apt/lists/*
ARG WHISPER_MODEL=base.en
RUN git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git /whisper.cpp \
    && cd /whisper.cpp \
    && make -j$(nproc) WHISPER_CUDA=1 \
    && bash ./models/download-ggml-model.sh ${WHISPER_MODEL}
# copy whisper-cli + required CUDA runtime libs into the slim runtime
```

The `WHISPER_BACKEND` build-arg selects which stage feeds the runtime. (Exact
CUDA `.so` set copied: `libcudart.so*`, `libcublas*`, `libcufft*`,
`libcurand*`, `libcublasLt*` — resolved at implementation time.)

### Config (env, with defaults)
- `WHISPER_MODEL` — model name, default `base.en`.
- `WHISPER_MODEL_DIR` — model directory, default `/opt/whisper/models`.
- `WHISPER_CPP_BIN` — binary path, default `/usr/local/bin/whisper-cli`.
- `WHISPER_TIMEOUT` — per-transcription subprocess timeout (seconds), default `60`.
- `WHISPER_MAX_CONCURRENCY` — simultaneous transcriptions, default `1` (see §5).

## §2 — Backend Integration (server-side chain)

### New module: `backend/services/whisper_cpp_service.py`
Owns the local engine. Responsibilities:
- `is_available() -> bool` — binary exists **and** model file exists.
- `transcribe(audio_bytes: bytes, language: str | None) -> str` —
  1. write `audio_bytes` to a temp `.wav`,
  2. `subprocess.run([WHISPER_CPP_BIN, "-m", model, "-f", tmp,
     "--output-txt", *(["-l", language] if language else [])],
     text=True, timeout=WHISPER_TIMEOUT, capture_output=True)`,
  3. parse stdout (strip surrounding whitespace) → return text,
  4. raise `LocalSTTError` on missing binary/model, non-zero exit, timeout,
     or empty output.
- GPU probe at startup: `gpu_available = os.path.exists("/dev/nvidia0")
  and _can_load_libcuda()`; log `[STT] whisper.cpp backend=GPU|CPU`. Result
  cached.
- A module-level `asyncio.Lock` enforces `WHISPER_MAX_CONCURRENCY` so CPU
  builds don't OOM under parallel requests.

### Refactor `AudioService.transcribe()` (`audio_service.py:104`)
Existing OpenAI logic moves to private `_transcribe_openai(...)`. New flow:

```
async def transcribe(db, user_id, audio_bytes, language=None, filename="audio.wav"):
    # 1. Local whisper.cpp (PRIMARY)
    svc = get_whisper_cpp_service()
    if svc.is_available():
        try:
            return await svc.transcribe(audio_bytes, language)
        except LocalSTTError as exc:
            logger.warning("[STT] local whisper.cpp failed: %s — falling back", exc)

    # 2. OpenAI Whisper (if a key is configured)
    api_key = self._get_openai_api_key(db, user_id)
    if api_key:
        return await self._transcribe_openai(db, user_id, audio_bytes, language, filename)

    # 3. Nothing server-side available
    raise ServerSTTUnavailable("No server STT engine available")
```

- `is_available(db, user_id)` and `get_status(db, user_id)` updated so the
  primary engine is reported as `whisper_cpp` when `get_whisper_cpp_service().is_available()`.
- `MAX_AUDIO_SIZE` / `SUPPORTED_AUDIO_TYPES` checks remain (whisper.cpp accepts
  the same formats; if a format is unsupported by the binary we surface
  `LocalSTTError` and fall through).

### Exceptions (`backend/core/exceptions.py`)
- Add `ServerSTTUnavailable` (subclass of the existing `ServiceUnavailableError`
  or a new typed error carrying `code="STT_UNAVAILABLE"`, `fallback="browser"`).
- Add `LocalSTTError` (internal, not HTTP — converts to the above when it
  reaches the route).

### Route mapping (`backend/api/routes/audio.py`, `voice.py`)
Catch `ServerSTTUnavailable` and return a recognizable JSON error so the
frontend switches to browser-native:

```json
{ "error": "No server STT engine available", "code": "STT_UNAVAILABLE", "fallback": "browser" }
```

The existing `ValueError` → `BadRequestError` mapping is preserved (used for
oversized/unsupported audio).

## §3 — Host Voice-Bridge (`voice-bridge/main.py`)

The bridge remains the **desktop voice companion** (talk to the chat box by
voice from the Windows desktop even when the browser chat is closed). Its STT
engine changes:

- `_listen_sync()` converts captured audio to WAV (`audio.get_wav_data()`) and
  POSTs it to `STT_BACKEND_URL` (default `BACKEND_URL + /api/v1/audio/transcribe`)
  with the existing `VOICE_TOKEN` bearer auth. The returned `text` feeds the
  wake-word check and session flow **unchanged**.
- **Vosk stays as an offline safety net:** only if the backend STT HTTP call
  fails (backend unreachable / whisper.cpp missing) does it fall back to local
  Vosk — the current Google→Vosk shape, just backend-whisper.cpp→Vosk.
- New config `STT_BACKEND_URL` (derives from `BACKEND_URL` when unset).
- `_recognize_with_vosk()` is retained as-is for the offline path.

This is the minimal change that makes whisper.cpp the unified primary engine
for the bridge without rewriting its session/wake-word logic.

## §4 — Frontend (`frontend/src/services/localVoice.ts` + voice hook)

`localVoice.ts` already implements browser-native Web Speech; no new
transcription code is needed. Changes are confined to *triggering*:

- `backend/api/routes/voice.py` `GET /voice/enhanced-status` gains a
  `whisper_cpp` entry and reports `current: "whisper_cpp"` when the backend has
  the local engine available (i.e., `get_whisper_cpp_service().is_available()`).
- The calling UI (ChatPage / voice hook) switches to `localVoice.transcribe()`
  when a transcription returns `code: "STT_UNAVAILABLE"`. The existing
  `localVoice` API is sufficient.

## §5 — Error Handling & Resilience

- **Local whisper.cpp down** (binary/model missing, crash, timeout, empty
  output) → caught, logged once, chain proceeds to OpenAI or browser. Never
  blocks the user.
- **OpenAI key absent + whisper.cpp down** → `ServerSTTUnavailable` → frontend
  uses browser-native. One clear signal, no silent failure.
- **Subprocess safety** — `text=True`, `timeout=WHISPER_TIMEOUT`, `stderr`
  captured to logs, temp file always cleaned up in a `finally`, single model
  instance; concurrent requests serialize under the concurrency lock.
- **CPU memory guard** — default `WHISPER_MAX_CONCURRENCY=1` because the backend
  runs `uvicorn --workers 1` and whisper.cpp CPU inference is memory-heavy.
  Raised only when GPU is in use.

## §6 — Testing & Rollout

### Tests
- **Unit** (`backend/tests/`): `whisper_cpp_service` with a mocked subprocess —
  covers stdout parsing, `WHISPER_TIMEOUT` expiry, missing-model →
  `LocalSTTError`, GPU-probe result.
- **Integration** (reuse the fake OpenAI-compatible provider server already in
  the repo, per recent commits): assert the chain
  `whisper unavailable → openai → unavailable`, the fallback order, and the
  `STT_UNAVAILABLE` signal shape.
- **Build smoke** (CI, CPU only, no GPU): assert `whisper-cli` + `base.en` exist
  in the image and one real short-sample transcription succeeds.

### Rollout
- Ships inside the existing backend image; default model `base.en`.
- Opt into GPU with `WHISPER_BACKEND=cuda` build-arg + `--gpus all` on the
  backend container (privileged).
- No breaking API changes: `audio/transcribe` and `voice/transcribe` keep their
  request/response contracts; only engine *selection* changes.
- `backend/requirements.txt` unchanged (subprocess invocation needs no new
  Python deps).

## Out of Scope
- Rewriting the host voice-bridge's session/wake-word logic or "improvements"
  beyond the STT relay.
- NVIDIA Parakeet as an alternative engine (noted as a future option).
- Streaming/real-time whisper.cpp (the local engine here is single-shot,
  matching the existing `audio/transcribe` contract).
