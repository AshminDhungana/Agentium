# Design Document: Section 5.1 Model Configuration Verification

**Date**: 2026-08-28  
**Status**: Approved  
**Scope**: Automated test suite verifying TODO items 5.1.1–5.1.5

---

## 1. Purpose

Create an automated test suite (pytest + Playwright) that verifies all 5 TODO items in section 5.1 "Model Configuration" of `docs/documents/TODO.md` are working correctly. The implementation appears complete; this effort validates and checks off each item.

---

## 2. Requirements Verification Matrix

| TODO | Description | Test Type | Test File |
|------|-------------|-----------|-----------|
| 5.1.1 | `POST /api/v1/models/configs` creates config (API key + provider) | API | `tests/api/test_models_config.py` |
| 5.1.2 | `GET /api/v1/models/configs` returns user's configs | API | `tests/api/test_models_config.py` |
| 5.1.3 | API keys stored encrypted (verify `api_key_manager.py`) | API + DB | `tests/api/test_models_config.py` |
| 5.1.4 | Supported providers: OpenAI, Anthropic, Google, Groq, DeepSeek, Mistral, OpenRouter, xAI, local | Unit + API | `tests/unit/test_provider_enum.py`, `tests/api/test_models_config.py` |
| 5.1.5 | `ModelsPage.tsx` add/edit/delete UI works | E2E | `tests/e2e/test_models_page.spec.ts` |

---

## 3. Test Architecture

```
tests/
├── api/
│   └── test_models_config.py          # 5.1.1, 5.1.2, 5.1.3, 5.1.4
├── e2e/
│   └── test_models_page.spec.ts       # 5.1.5
├── unit/
│   └── test_provider_enum.py          # 5.1.4 enum validation
└── conftest.py                        # Shared fixtures
```

---

## 4. Test Cases Detail

### 4.1 API Tests (`tests/api/test_models_config.py`)

**5.1.1 — Create Config**
- Valid create for each provider (OpenAI, Anthropic, Google, Groq, DeepSeek, Mistral, OpenRouter, xAI, Local, Custom)
- Invalid provider → 422
- Missing required fields (provider, config_name, default_model) → 422
- Duplicate config_name → 409
- API key encryption verified in DB (`api_key_encrypted` is ciphertext, not plaintext)

**5.1.2 — List Configs**
- Returns all configs for authenticated user
- Empty list when none exist
- Response matches `ModelConfigResponse` schema
- `api_key_masked` present (format `...xxxx`), `api_key` absent

**5.1.3 — Encryption**
- Raw key not in DB (`api_key_encrypted` is Fernet ciphertext)
- Round-trip: `decrypt_api_key(encrypt_api_key(key)) == key`
- Wrong ENCRYPTION_KEY → decrypt returns `None`
- Masked version (`...xxxx`) stored in `api_key_masked`

**5.1.4 — Providers**
- `/models/providers` returns all with correct metadata:
  - `requires_api_key`, `default_base_url`, `popular_models`

### 4.2 Unit Tests (`tests/unit/test_provider_enum.py`)

- `ProviderType` enum contains: OPENAI, ANTHROPIC, GEMINI, GROQ, DEEPSEEK, MISTRAL, OPENROUTER, XAI, LOCAL, CUSTOM
- No duplicate values
- Values are uppercase strings

### 4.3 E2E Tests (`tests/e2e/test_models_page.spec.ts`)

**5.1.5 — ModelsPage UI**
- Add: form opens → fill → submit → card appears in grid
- Edit: click edit → modify fields → save → card updates
- Delete: click delete → confirm → card removed from grid
- Test Connection button calls `/configs/{id}/test` endpoint, shows result toast
- Fetch Models button populates available_models dropdown
- Default badge moves correctly when "Set Default" clicked
- Empty state shows when no configs exist
- Error banner displays on API failure with retry button

---

## 5. Fixtures (`tests/conftest.py`)

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `db_session` | function | SQLAlchemy session with transaction rollback |
| `auth_client` | function | `AsyncClient` with valid JWT for "sovereign" user |
| `model_config_factory` | function | Factory creating configs with various providers |
| `test_db` | session | Docker PostgreSQL for integration tests |

---

## 6. CI Integration

- `make test-models` target runs full suite
- GitHub Actions workflow runs on PR against `docker-compose.test.yml` stack
- Parallel execution: API/unit tests first, E2E after services healthy

---

## 7. Success Criteria

All tests pass → TODO items 5.1.1–5.1.5 marked `[x]` in `docs/documents/TODO.md`

---

## 8. Out of Scope

- Testing provider API connectivity (requires real keys)
- Load/performance testing
- Mobile/responsive UI variations
- Voice bridge integration

---

## 9. Dependencies

- pytest, pytest-asyncio, httpx, faker
- Playwright (Chromium) for E2E
- Docker Compose test stack (postgres, redis, backend, frontend)

---

*Design approved by user on 2026-08-28. Proceeding to implementation plan.*