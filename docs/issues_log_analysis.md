# 📊 Agentium Log Analysis - Issues Summary

**Date:** 2026-03-01\
**Source:** Docker Compose Logs\
**Severity:** 🔴 Critical \| 🟠 Warning \| 🟡 Info

---

### 0. Voice Bridge is not working in windows

## 🔴 Critical Issues (Require Immediate Attention)

**Log Evidence:**

```plain
Error in resource_rebalancing loop: 'coroutine' object has no attribute 'get'
Error in vector_db_optimization: No module named 'backend.core.vector_db'
Skill search failed: Expected where to have exactly one operator, got {...}
```

---

## 🟠 Warnings (Should Be Addressed)

### 3. Database Migration Issues

---

Issue Details

---

Stale `votes` table reference Migration 005 created
`db_maintenance_config` but hardcoded
references to `votes` table still exist

Transaction cascade failure One SQL error causes subsequent
`ANALYZE` commands to be skipped

---

**Log Evidence:**

```plain
ERROR: relation "votes" does not exist
STATEMENT: ANALYZE votes
WARNING: ANALYZE skipped for constitutions: current transaction is aborted
```

---

### 4. Configuration Issues

---

Issue Component Severity

---

Missing S3/MinIO Media storage High -- File uploads will
credentials fail

Trust PostgreSQL Medium -- Security risk
authentication  
 enabled

No system locales PostgreSQL Low -- Warning only

---

**Log Evidence:**

```plain
Error ensuring bucket agentium-media exists: Unable to locate credentials
initdb: warning: enabling "trust" authentication for local connections
WARNING: no usable system locales were found
```

---

### 5. Voice/Audio System Issues

---

Issue Cause Impact

---

No ALSA capture device Container environment Voice input unavailable

apt not available Container restrictions Cannot install system
deps

PyAudio install failed Missing portaudio Python voice capture
fails

---

**Log Evidence:**

```plain
[WARN] No ALSA capture device found - voice capture may fail at runtime
[WARN] apt update failed (exit 127) - continuing
[WARN] install PyAudio failed (exit 1) - continuing
```

---

## 🟡 Minor Issues (Low Priority)

### 6. Idle Governance Errors

JSON serialization error when processing idle tasks\
Affected Agents: 00001, 10001, 10002

**Log Evidence:**

```plain
Idle work error for 00001: the JSON object must be str, bytes or bytearray, not list
```

---

### 7. WhatsApp Bridge Connection

Repeated QR code generation (connection timeout 408)\
Status: loggedOut: false (waiting for scan)

**Log Evidence:**

```plain
WARN (1): [Bridge] Connection closed
    statusCode: 408
    loggedOut: false
```

---

### 8. Vector Store Maintenance

Unknown collection key `critic_case_law` referenced but not in valid
keys list

**Log Evidence:**

```plain
Could not check critic_case_law: Unknown collection key 'critic_case_law'.
Valid keys: ['constitution', 'ethos', 'council_memory', ...]
```

---

# 📈 Summary Statistics

Category Count Priority

---

Database Schema 3 🔴 Critical
Runtime Errors 4 🔴 Critical
Configuration 4 🟠 High
Migration 2 🟠 High
Voice/Audio 3 🟠 Medium
Idle Governance 1 🟡 Low
WhatsApp Bridge 1 🟡 Low
Vector Store 1 🟡 Low

Total: 19 Distinct Issues

---

# ✅ Recommended Actions

## 🗄 Database

- Run migration to add `updated_at` to `individual_votes`
- Fix `experiment_status` enum to include `COMPLETED` or align code
  with existing enum values
- Replace stale `votes` table references with `individual_votes`
- Fix transaction handling in `db_maintenance`

## 💻 Code

- Fix async/await handling in `resource_rebalancing`
- Add missing `backend.core.vector_db` module or correct import path
- Fix ChromaDB `where` query syntax (ensure single operator per
  condition)
- Resolve JSON serialization issue in idle governance tasks

## ⚙️ Configuration

- Set S3/MinIO credentials via environment variables
- Replace `trust` authentication with password-based or md5 auth in
  PostgreSQL
- Configure proper system locales in PostgreSQL container

## 🎙 Voice System

- Use Web Speech API fallback (frontend-based capture)
- Avoid container-based ALSA/PyAudio unless running privileged audio
  containers

## 🔧 Maintenance

- Review Migration 005 implementation thoroughly
- Fix transaction cascade behavior in maintenance scripts
- Remove or register unknown vector collection keys
