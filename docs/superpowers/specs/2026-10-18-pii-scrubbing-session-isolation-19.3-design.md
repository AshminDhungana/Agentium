# PII Scrubbing & Session Isolation — Design Spec (19.3)

> **Status**: Design Phase — Ready for Review  
> **Date**: 2026-10-18  
> **TODO Reference**: Section 19.3 — PII Scrubbing & Session Isolation  
> **Prerequisites**: 19.1 (Constitutional Guard), 19.2 (Prompt Injection Resistance) complete

---

## 1. Problem Statement

Agentium currently lacks systematic PII detection/redaction and cross-session data isolation. This creates risks:

| Risk | Current Gap |
|------|-------------|
| **PII in logs/audit** | Structured logs, `AuditLog.metadata_json`, `before_state`/`after_state` store raw user inputs |
| **PII in LLM context** | File uploads, web search results, tool outputs flow to LLMs unsanitized |
| **PII in responses** | Agent responses may echo PII from context |
| **Credential leakage** | API keys, passwords in tool params, webhook payloads, auth headers logged in plain text |
| **Session leakage** | Redis caches (constitution, embeddings), WebSocket broadcasts, chat history not scoped to session |

**TODO 19.3 Requirements:**
- **19.3.1** — PII detection identifies names, emails, phone numbers, SSNs
- **19.3.2** — PII redacted from agent responses and logs
- **19.3.3** — User session data isolated (no cross-session leakage)
- **19.3.4** — Credential data never logged in plain text

---

## 2. Design Goals

| Goal | Approach |
|------|----------|
| **Defense in depth** | Redact at ingress, egress, logging, and audit persistence |
| **Extensible detectors** | Strategy pattern: regex now → spaCy/Presidio later |
| **Configurable redaction** | Mask, full redact, hash, tokenize, remove modes |
| **Zero false negatives for credentials** | API keys, passwords, tokens caught with high confidence |
| **Session isolation by default** | All Redis keys, WebSocket rooms, chat history scoped to `session_id` |
| **Follow existing patterns** | Mirror `PromptInjectionSanitizer`, `ResponseGuard`, `ConstitutionalGuard` service style |

---

## 3. Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                      PII SCRUBBER SERVICE                               │
│  backend/core/pii_scrubber.py                                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                    │
│  │  Detectors  │  │ Redaction   │  │ Integration │                    │
│  │ (Strategy)  │──│ Strategies  │──│ Helpers     │                    │
│  └─────────────┘  └─────────────┘  └─────────────┘                    │
└────────────────────────────────────────────────────────────────────────┘
         │                   │                   │
         ▼                   ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   INGRESS        │ │   EGRESS         │ │ LOGGING/AUDIT    │
│ ───────────────  │ │ ───────────────  │ │ ───────────────  │
│ • prompt_inject  │ │ • response_guard │ │ • StructuredLog  │
│   _sanitizer     │ │ • ChatService    │ │   Formatter      │
│ • file_processor │ │ • WS broadcast   │ │ • AuditLog.log() │
│ • knowledge_     │ │ • Tool output    │ │ • Const. Guard   │
│   assist         │ │                  │ │   context        │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

### 3.1 Session Isolation Layer

```
┌────────────────────────────────────────────────────────────────────────┐
│                    SESSION ISOLATION                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │ Redis Keys   │  │ Context Vars │  │ WebSocket    │  │ Chat DB   │  │
│  │ Namespaced   │  │ (session_id) │  │ Room Routing │  │ (session_ │  │
│  │ by session_id│  │              │  │              │  │  _id col) │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └───────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Core Component: `backend/core/pii_scrubber.py`

### 4.1 Data Structures

```python
class PIIType(str, Enum):
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    NAME = "name"
    API_KEY = "api_key"
    PASSWORD = "password"
    CREDIT_CARD = "credit_card"
    ADDRESS = "address"
    CUSTOM = "custom"

class RedactionMode(str, Enum):
    MASK = "mask"           # "john@example.com" → "j***@example.com"
    FULL_REDACT = "redact"  # "john@example.com" → "[REDACTED: email]"
    HASH = "hash"           # "john@example.com" → "[HASH: a1b2c3d4]"
    TOKENIZE = "tokenize"   # "john@example.com" → "[EMAIL_1]" (reversible)
    REMOVE = "remove"       # "john@example.com" → ""

@dataclass
class PIIMatch:
    pii_type: PIIType
    start: int
    end: int
    matched_text: str
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class DetectionResult:
    text: str
    matches: List[PIIMatch] = field(default_factory=list)
    has_pii: bool = False
```

### 4.2 Detector Interface (Strategy Pattern)

```python
class PIIDetector(ABC):
    @property
    @abstractmethod
    def pii_type(self) -> PIIType: pass
    
    @abstractmethod
    def find_matches(self, text: str) -> List[PIIMatch]: pass

class RegexDetector(PIIDetector):
    """Regex-based detector with configurable patterns."""
    def __init__(self, pii_type: PIIType, patterns: List[str], flags=re.IGNORECASE):
        self._pii_type = pii_type
        self._compiled = [re.compile(p, flags) for p in patterns]
    
    def find_matches(self, text: str) -> List[PIIMatch]: ...
```

### 4.3 Built-in Detectors (Regex Patterns)

| PII Type | Patterns | Validation |
|----------|----------|------------|
| **Email** | RFC 5322 simplified | Syntax only |
| **Phone** | E.164, US, EU, generic | Format only |
| **SSN** | `XXX-XX-XXXX`, `XXX XX XXXX`, `XXXXXXXXX` | Format + range checks |
| **API Key** | `sk-`, `pk-`, `ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`, `xai-`, `sk-ant-`, `AIza`, `AKIA`, `Bearer ` | Prefix matching |
| **Password** | `password=`, `secret=`, `api_key=`, `token=`, `Authorization:` | Assignment context |
| **Credit Card** | Visa, Mastercard, Amex, Discover | Luhn algorithm |
| **Name** | `First Last`, `First M. Last` | Capitalized words (optional, high FP) |

### 4.4 Main Service Class

```python
class PIIScrubber:
    DEFAULT_DETECTORS = {
        PIIType.EMAIL: RegexDetector(PIIType.EMAIL, EMAIL_PATTERNS),
        PIIType.PHONE: RegexDetector(PIIType.PHONE, PHONE_PATTERNS),
        PIIType.SSN: RegexDetector(PIIType.SSN, SSN_PATTERNS),
        PIIType.API_KEY: RegexDetector(PIIType.API_KEY, API_KEY_PATTERNS),
        PIIType.PASSWORD: RegexDetector(PIIType.PASSWORD, PASSWORD_PATTERNS),
        PIIType.CREDIT_CARD: RegexDetector(PIIType.CREDIT_CARD, CREDIT_CARD_PATTERNS),
        # Name detector disabled by default (high false positive rate)
    }
    
    def __init__(
        self,
        detectors: Optional[Dict[PIIType, PIIDetector]] = None,
        enabled_types: Optional[List[PIIType]] = None,
        custom_patterns: Optional[Dict[PIIType, List[str]]] = None,
        default_mode: RedactionMode = RedactionMode.FULL_REDACT,
    ): ...
    
    def detect(self, text: str, types: Optional[List[PIIType]] = None) -> DetectionResult: ...
    def redact(self, text: str, mode: RedactionMode = None, types: List[PIIType] = None, 
               custom_replacements: Dict[PIIType, str] = None) -> str: ...
    def sanitize_dict(self, data: Dict, keys: List[str] = None, mode: RedactionMode = None, 
                      recurse: bool = True) -> Dict: ...
```

### 4.5 Global Instance & Convenience Functions

```python
pii_scrubber = PIIScrubber()

def detect_pii(text: str, types: List[PIIType] = None) -> DetectionResult: ...
def redact_pii(text: str, mode: RedactionMode = RedactionMode.FULL_REDACT, 
               types: List[PIIType] = None) -> str: ...
def sanitize_dict_pii(data: Dict, keys: List[str] = None, 
                      mode: RedactionMode = RedactionMode.FULL_REDACT) -> Dict: ...
```

---

## 5. Integration Points

### 5.1 Ingress Path

| Component | Integration | Redaction Mode |
|-----------|-------------|----------------|
| `PromptInjectionSanitizer.sanitize_dict()` | Call `sanitize_dict_pii()` after prompt injection sanitization | `FULL_REDACT` |
| `file_processor.extract_pdf_text()` | Redact extracted text before return | `FULL_REDACT` |
| `knowledge_assist._synthesize_web_doc()` | Redact synthesized web content | `FULL_REDACT` |
| `knowledge_assist._format_context()` | Redact ChromaDB retrieved documents | `FULL_REDACT` |

### 5.2 Egress Path

| Component | Integration | Redaction Mode |
|-----------|-------------|----------------|
| `ResponseGuard.check_response()` | Redact PII after leakage detection | `MASK` (preserves readability) |
| `ChatService` streaming | Redact each delta chunk | `MASK` |
| WebSocket broadcast | Redact before `send_json()` | `MASK` |
| Tool output | Redact in `tool_runner.py` | `FULL_REDACT` |

### 5.3 Logging & Audit

| Component | Integration | Redaction Mode |
|-----------|-------------|----------------|
| `StructuredFormatter.format()` | Redact `record.msg` and string `extra` fields | `MASK` |
| `AuditLog.log()` factory | Redact `meta_data`, `before_state`, `after_state` | `FULL_REDACT` |
| `ConstitutionalGuard._log_decision()` | Redact `context` parameter | `FULL_REDACT` |

---

## 6. Session Isolation

### 6.1 Redis Key Namespacing

```python
# Constitutional Guard
CONSTITUTION_CACHE_KEY = "constitutional_guard:active_constitution:{session_id}"
EMBEDDING_CACHE_KEY = "constitutional_guard:semantic:{digest}:{session_id}"

# Rate Limiting (add session tier)
RATE_LIMIT_KEY = "agentium:ratelimit:{tier}:session:{session_id}:{ip_or_user}"

# MCP Tool Stats
MCP_STATS_KEY = "mcp:stats:{tool_id}:session:{session_id}"
```

### 6.2 Context Variable

```python
# In structured_logging.py
session_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("session_id", default=None)

@contextmanager
def structured_log_context(
    request_id: str = None,
    step: str = None,
    agent_id: str = None,
    task_id: str = None,
    session_id: str = None,  # NEW
): ...

# StructuredFormatter includes session_id in every log entry
```

### 6.3 WebSocket Session Routing

```python
# In websocket.py ConnectionManager
class ConnectionManager:
    def __init__(self):
        self.session_connections: Dict[str, Set[WebSocket]] = {}
        self.connection_sessions: Dict[WebSocket, str] = {}
    
    async def broadcast_to_session(self, session_id: str, message: dict):
        for ws in self.session_connections.get(session_id, set()):
            await ws.send_json(message)
```

### 6.4 Chat History Isolation

```python
# Alembic migration: add session_id column to chat_messages
# In ChatService._load_chat_history()
query = db.query(ChatMsg).filter(
    ChatMsg.user_id == user_id,
    ChatMsg.session_id == session_id,  # NEW filter
    ChatMsg.is_deleted == "N"
)
```

---

## 7. Configuration

```python
# In backend/core/config.py (Settings class)
PII_SCRUBBING_ENABLED: bool = True
PII_REDACTION_MODE: str = "redact"  # mask, redact, hash, tokenize, remove
PII_DETECTORS_ENABLED: List[str] = [
    "email", "phone", "ssn", "api_key", "password", "credit_card"
]
PII_CUSTOM_PATTERNS: Dict[str, List[str]] = {}  # Tenant-specific
PII_SESSION_ISOLATION: bool = True
```

---

## 8. Testing Strategy

| Level | Tests |
|-------|-------|
| **Unit** | Each detector (6 types) with valid/invalid/edge cases |
| **Unit** | All 5 redaction modes |
| **Unit** | `sanitize_dict()`: nested dicts, lists, mixed types, key filtering |
| **Integration** | `PromptInjectionSanitizer` + `PIIScrubber` combined pipeline |
| **Integration** | `ResponseGuard` + `PIIScrubber` on streaming/non-streaming |
| **Integration** | `StructuredFormatter` redacts PII in message + extra fields |
| **Integration** | `AuditLog.log()` persists redacted `metadata_json`/`before_state`/`after_state` |
| **Integration** | `file_processor` + `knowledge_assist` redact extracted/synthesized content |
| **E2E** | Session A data never appears in Session B logs, cache, WS, chat history |
| **E2E** | Credentials (API keys, passwords) never in plain text in any log/audit/response |

---

## 9. Migration & Deployment

1. **Alembic Migration**: Add `session_id` column to `chat_messages` table
2. **Config Flag**: `PII_SCRUBBING_ENABLED=true` (default for production)
3. **Rollout Order**:
   - Phase 1: Log/audit redaction (lowest risk)
   - Phase 2: Ingress redaction (file processor, knowledge assist)
   - Phase 3: Egress redaction (response guard, WebSocket)
   - Phase 4: Session isolation (Redis keys, WS routing, chat history)
4. **Monitoring**: Track false positive rate (especially name detector)
5. **Rollback**: Config flag disables all scrubbing instantly

---

## 10. Future Extensibility (Post-19.3)

| Enhancement | Effort | Description |
|-------------|--------|-------------|
| spaCy NER Detector | Medium | Replace name/address regex with ML NER |
| Microsoft Presidio | Medium | Enterprise-grade PII engine with 50+ entities |
| Reversible Tokenization Vault | High | GDPR-compliant token store for `[EMAIL_1]` → original mapping |
| Per-Tenant Custom Patterns | Low | Admin UI for custom regex patterns |
| PII Metrics Dashboard | Low | Detection counts, types, false positive estimates |

---

## 11. Acceptance Criteria (Maps to TODO 19.3)

| TODO Item | Verification |
|-----------|--------------|
| **19.3.1** | Unit tests: each detector catches ≥95% of synthetic test cases; <5% FP on clean text |
| **19.3.2** | Integration: agent response to "My SSN is 123-45-6789" returns `[REDACTED: ssn]`; structured logs show masked PII |
| **19.3.3** | E2E: Session A creates task, Session B cannot see it in chat history, WS events, or Redis cache keys |
| **19.3.4** | Audit: Search `AuditLog.metadata_json`, `before_state`, `after_state`, structured logs — no plain API keys, passwords, tokens |

---

## 12. File Changes Summary

### New Files
- `backend/core/pii_scrubber.py` — Core service (~400 lines)

### Modified Files
- `backend/core/prompt_injection_sanitizer.py` — Call `sanitize_dict_pii()` in `sanitize_dict()`
- `backend/core/response_guard.py` — Call `redact_pii()` in `check_response()`
- `backend/services/structured_logging.py` — Redact in `StructuredFormatter.format()`, add `session_id_var`
- `backend/models/entities/audit.py` — Redact in `AuditLog.log()` factory method
- `backend/services/file_processor.py` — Redact in `extract_pdf_text()`
- `backend/services/knowledge_assist.py` — Redact in `_synthesize_web_doc()`, `_format_context()`
- `backend/core/constitutional_guard.py` — Namespace Redis cache keys with `session_id`
- `backend/api/routes/websocket.py` — Session-scoped broadcast in `ConnectionManager`
- `backend/services/chat_service.py` — Filter chat history by `session_id`
- `backend/core/config.py` — Add PII settings
- `backend/alembic/versions/XXX_add_session_id_to_chat_messages.py` — Migration

---

## 13. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| High false positives (names) | Medium | Medium | Name detector disabled by default; configurable |
| Performance overhead | Low | Low | Regex compilation cached; <1ms per KB typical |
| Streaming response redaction | Medium | Medium | Redact per-chunk; buffer if pattern spans chunks |
| Session ID propagation gaps | Medium | High | Audit all entry points (HTTP, WS, Celery) for `session_id` context |
| Legacy log data unredacted | N/A | Low | Only affects new logs; migration not required |

---

## 14. Review Checklist

- [ ] Architecture follows existing service patterns
- [ ] All 4 TODO requirements addressed
- [ ] Integration points cover ingress, egress, logging, audit
- [ ] Session isolation covers Redis, WS, DB, context vars
- [ ] Configuration allows disable/tuning per environment
- [ ] Testing strategy covers unit, integration, E2E
- [ ] Migration path defined for `session_id` column
- [ ] Future extensibility documented (ML detectors, tokenization vault)

---

**Next Step**: Upon approval, invoke `writing-plans` skill to create implementation plan.