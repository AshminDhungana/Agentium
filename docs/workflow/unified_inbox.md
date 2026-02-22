# 🏛️ Agentium -- Unified Inbox Implementation Task (Done) [Verify at the End]

---

# 🎯 Objective

Design and implement a **Unified Inbox Architecture** that guarantees:

- One user → One canonical conversation state
- Full synchronization across all channels
- No duplicate notifications
- Media consistency (images, video, files)
- Clean and non-intrusive user experience
- Constitutional alignment with Agentium Governance

If partially implemented, refactor to enforce full unification.

---

# 🧠 Core Principle

> A user's conversation is sovereign and channel-agnostic.

Channels are merely transport layers. Conversation state must never
diverge per channel.

---

# 🏗️ I. Architectural Decision

## 🔷 Canonical Authority

The **Web Interface Inbox** becomes the Primary Conversation Authority.

All messages:

- Flow through backend first
- Persist in PostgreSQL
- Broadcast through Redis Event Bus
- Reflected across all channels

Channels do NOT maintain independent histories.

---

# 📦 II. Unified Conversation Model

## 1️⃣ Database Schema (PostgreSQL -- Source of Truth)

```sql
Conversation {
    id: UUID
    user_id: UUID
    created_at
    updated_at
    is_active: boolean
}

Message {
    id: UUID
    conversation_id: UUID
    sender_type: user | system | agent
    sender_channel: web | whatsapp | telegram | slack | api
    message_type: text | image | video | audio | file
    content: TEXT (nullable)
    media_url: TEXT (nullable)
    metadata: JSONB
    silent_delivery: boolean
    created_at
}
```

---

# 🔄 III. Message Flow Architecture

## A. Incoming Message (Any Channel)

Example: Telegram image

Flow:

1.  Telegram Webhook → Channel Manager
2.  Normalize payload to internal Message format
3.  Store in PostgreSQL
4.  Emit Redis Event: `MESSAGE_CREATED`
5.  WebSocket Hub broadcasts to:
    - Web Dashboard
    - All connected channel sessions

Result: - Image appears in web inbox instantly - Stored permanently - No
duplication - No re-notification on same channel

---

## B. Outgoing Message (System → User)

When system replies:

1.  Message saved to PostgreSQL
2.  Web interface updated immediately
3.  Channel Manager broadcasts to:
    - All active channels of user
4.  Respect `silent_delivery` rules

---

# 🔕 IV. Silent Sync Logic (Critical UX Rule)

Problem: If user chats on web, they should NOT receive the same reply as
a disruptive mobile notification.

## Solution:

When message origin = web: - Mark `silent_delivery = true` for external
channels

Channel adapters must:

- Use silent flags (where API supports it)
- Suppress push notification when applicable
- Still sync conversation content

This ensures: - WhatsApp/Telegram history updated - No annoying
notification - Seamless continuity

---

# 📷 V. Media Handling Standard

All media must:

1.  Be downloaded and stored in secure object storage
2.  Generate persistent URL
3.  Be normalized across channels

Example: - User sends image from Telegram - Stored in system storage -
Displayed identically in web dashboard - If user later opens WhatsApp →
same image visible

Media must never remain channel-dependent.

---

# 🔁 VI. Broadcast Strategy Options

## Option A -- Full Broadcast (Recommended)

System responses are: - Stored once - Broadcast to all active channels -
Visible everywhere

Pros: - Perfect synchronization - No context loss - Cross-device
continuity

Cons: - Must carefully manage notification noise

---

## Option B -- Web-Primary Mode (Alternative)

System responses: - Always visible in web - Only sent to last-active
channel - Other channels sync silently

Recommended Hybrid: - Broadcast to all - Silent for non-active channels

---

# 🧩 VII. Channel Manager Requirements

Channel Manager must:

- Maintain user-channel mapping
- Track active sessions
- Store last_active_channel
- Apply silent policy rules
- Prevent message duplication loops

Loop Prevention: If message originated from Telegram: → Do NOT re-send
same message back to Telegram.

---

# 📡 VIII. Event-Driven Synchronization

Use Redis Pub/Sub:

Events:

- MESSAGE_CREATED
- MESSAGE_UPDATED
- MEDIA_UPLOADED
- CONVERSATION_ACTIVATED

WebSocket Hub subscribes and pushes to dashboard.

Channels subscribe selectively.

---

# 🧠 IX. UX Design Principles

1.  Zero duplication
2.  Zero channel divergence
3.  Media consistent everywhere
4.  No double notifications
5.  Smooth cross-device transition
6.  Always show full history in web

---

# 👤 X. Multi-User Isolation

Each user must have:

- Independent Conversation ID
- Independent Channel Mapping
- Strict data isolation
- JWT-bound access

One user's inbox must NEVER intersect with another.

---

# 🧪 XI. Edge Cases to Handle

- User connected to multiple channels simultaneously
- User disconnects channel
- Media upload fails
- WebSocket reconnect
- Channel rate limits
- Message edit/delete sync
- Long-running streaming responses

All must remain unified.

---

# 🔐 XII. Governance Alignment

Unified Inbox must respect:

- Audit logging (every message stored)
- Constitutional Guard (content checks)
- Critic visibility (if needed)
- No channel-level bypass

Messages are constitutional artifacts.

---

# 🚀 XIII. Implementation Checklist

- [ ] Create Conversation + Message tables
- [ ] Normalize channel payloads
- [ ] Implement Redis event publishing
- [ ] WebSocket broadcast integration
- [ ] Silent delivery logic
- [ ] Media normalization service
- [ ] Loop prevention logic
- [ ] Channel activity tracking
- [ ] Full inbox UI unification
- [ ] Notification control logic
- [ ] Multi-device testing
- [ ] Audit log verification

---

# 🏁 Final Mandate

Agentium must behave as:

> A sovereign communication layer where conversation is unified,
> constitutional, and channel-independent.

Users must feel:

- Seamless continuity
- Zero friction
- Zero duplication
- Absolute consistency

---

**One User.\
One Conversation.\
Everywhere.**
