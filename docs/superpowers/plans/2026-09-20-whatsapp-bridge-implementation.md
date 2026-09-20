# WhatsApp Bridge Verification and Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement verification and improvements for WhatsApp bridge features per TODO items 11.2.1 through 11.2.5, ensuring QR code pairing works, messages are sent/received correctly, media handling is functional, and reconnection after disconnect works properly.

**Architecture:** This implementation focuses on verification of existing functionality and targeted enhancements where gaps are identified. We'll leverage the existing WhatsApp bridge (Node.js) and unified adapter (Python), adding tests and minor improvements to ensure complete coverage of the TODO requirements.

**Tech Stack:** Node.js (Baileys/Express/WebSocket), Python (FastAPI/HTTPX), PostgreSQL, Redis

## Global Constraints

- Maintain backward compatibility with existing WhatsApp bridge functionality
- Follow existing code patterns and conventions in the Agentium codebase
- Ensure secure handling of credentials (no exposure in API responses)
- Preserve existing rate limiting and circuit breaker implementations
- Keep changes focused and minimal - only add what's necessary for verification and improvement
- All new code must include appropriate error handling
- Tests should follow existing testing patterns in the codebase
- Database schema changes must be backward compatible
- API contract changes must be versioned or backward compatible
- Frontend changes must maintain responsive design and accessibility standards

---

### Task 1: Verify QR Code Pairing Flow

**Files:**
- Modify: `bridges/whatsapp/index.js:113-198` (verify existing QR implementation)
- Modify: `backend/services/channels/whatsapp_unified.py:341-362` (verify QR handling)
- Create: `tests/backend/services/test_whatsapp_bridge_qr.py`

**Interfaces:**
- Consumes: Bridge connection status updates
- Produces: QR code data for frontend display

- [ ] **Step 1: Examine existing QR code generation in bridge server**

```javascript
// Read the existing QR code implementation in bridges/whatsapp/index.js
// Focus on the 'connection.update' event handler
```

- [ ] **Step 2: Write test to verify QR code is generated when no credentials exist**

```python
def test_whatsapp_bridge_generates_qr_when_no_credentials():
    # Test that bridge generates QR code on startup when no saved credentials
    pass
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_qr.py::test_whatsapp_bridge_generates_qr_when_no_credentials -v`
Expected: PASS

- [ ] **Step 4: Write test to verify QR code includes proper expiration**

```python
def test_whatsapp_bridge_qr_includes_expiration():
    # Verify QR code includes expiration timestamp (typically 5 minutes)
    pass
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_qr.py::test_whatsapp_bridge_qr_includes_expiration -v`
Expected: PASS

- [ ] **Step 6: Write test to verify backend receives and stores QR code**

```python
def test_whatsapp_adapter_receives_and_stores_qr():
    # Test that adapter properly receives and stores QR code from bridge
    pass
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_qr.py::test_whatsapp_adapter_receives_and_stores_qr -v`
Expected: PASS

- [ ] **Step 8: Write test to verify QR code is cleared after authentication**

```python
def test_whatsapp_bridge_clears_qr_after_auth():
    # Verify QR code is cleared when WhatsApp authenticates successfully
    pass
```

- [ ] **Step 9: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_qr.py::test_whatsapp_bridge_clears_qr_after_auth -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add tests/backend/services/test_whatsapp_bridge_qr.py
git commit -m "feat: add tests for WhatsApp bridge QR code pairing flow"
```

### Task 2: Verify Incoming Message Handling

**Files:**
- Modify: `bridges/whatsapp/index.js:200-230` (verify message upsert handling)
- Modify: `backend/services/channels/whatsapp_unified.py:328-340` (verify bridge message handling)
- Modify: `backend/services/channels/whatsapp_unified.py:373-380` (verify incoming message processing)
- Create: `tests/backend/services/test_whatsapp_bridge_incoming.py`

**Interfaces:**
- Consumes: Raw WhatsApp messages from bridge
- Produces: Processed ExternalMessage objects routed to ChannelManager

- [ ] **Step 1: Examine existing incoming message handling in bridge server**

```javascript
// Read the existing message handling in bridges/whatsapp/index.js
// Focus on the 'messages.upsert' event handler
```

- [ ] **Step 2: Write test to verify text message reception and content extraction**

```python
def test_whatsapp_bridge_processes_incoming_text_message():
    # Test that text messages are properly extracted and formatted
    pass
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_incoming.py::test_whatsapp_bridge_processes_incoming_text_message -v`
Expected: PASS

- [ ] **Step 4: Write test to verify handling of different message types**

```python
def test_whatsapp_bridge_handles_various_message_types():
    # Test image, video, document, audio message types
    pass
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_incoming.py::test_whatsapp_bridge_handles_various_message_types -v`
Expected: PASS

- [ ] **Step 6: Write test to verify proper sender ID formatting**

```python
def test_whatsapp_bridge_formats_sender_id_correctly():
    # Verify @s.whatsapp.net suffix is removed from sender ID
    pass
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_incoming.py::test_whatsapp_bridge_formats_sender_id_correctly -v`
Expected: PASS

- [ ] **Step 8: Write test to verify group message detection**

```python
def test_whatsapp_bridge_detects_group_messages():
    # Test that group messages are properly detected and flagged
    pass
```

- [ ] **Step 9: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_incoming.py::test_whatsapp_bridge_detects_group_messages -v`
Expected: PASS

- [ ] **Step 10: Write test to verify message routing through ChannelManager**

```python
def test_whatsapp_bridge_routes_to_channel_manager():
    # Verify that processed messages are sent to ChannelManager.receive_message
    pass
```

- [ ] **Step 11: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_incoming.py::test_whatsapp_bridge_routes_to_channel_manager -v`
Expected: PASS

- [ ] **Step 12: Commit**

```bash
git add tests/backend/services/test_whatsapp_bridge_incoming.py
git commit -m "feat: add tests for WhatsApp bridge incoming message handling"
```

### Task 3: Verify Outbound Message Handling

**Files:**
- Modify: `bridges/whatsapp/index.js:295-310` (verify send message handling)
- Modify: `backend/services/channels/whatsapp_unified.py:437-462` (verify _send_bridge method)
- Create: `tests/backend/services/test_whatsapp_bridge_outgoing.py`

**Interfaces:**
- Consumes: ExternalMessage objects from ChannelManager
- Produces: WhatsApp messages sent via bridge or Cloud API

- [ ] **Step 1: Examine existing outbound message handling in bridge server**

```javascript
// Read the existing send message handling in bridges/whatsapp/index.js
// Focus on the 'send' action in websocket message handler
```

- [ ] **Step 2: Write test to verify text message sending via Web Bridge**

```python
def test_whatsapp_bridge_sends_text_message_via_bridge():
    # Test that text messages are properly sent via WebSocket bridge
    pass
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_outgoing.py::test_whatsapp_bridge_sends_text_message_via_bridge -v`
Expected: PASS

- [ ] **Step 4: Write test to verify proper JID formatting for recipients**

```python
def test_whatsapp_bridge_formats_recipient_jid():
    # Verify phone numbers are converted to proper JID format
    pass
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_outgoing.py::test_whatsapp_bridge_formats_recipient_jid -v`
Expected: PASS

- [ ] **Step 6: Write test to verify Cloud API message sending**

```python
def test_whatsapp_adapter_sends_via_cloud_api():
    # Test that Cloud API mode properly sends messages
    pass
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_outgoing.py::test_whatsapp_adapter_sends_via_cloud_api -v`
Expected: PASS

- [ ] **Step 8: Write test to verify error handling for disconnected state**

```python
def test_whatsapp_bridge_handles_disconnected_send_error():
    # Verify proper error when trying to send while disconnected
    pass
```

- [ ] **Step 9: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_outgoing.py::test_whatsapp_bridge_handles_disconnected_send_error -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add tests/backend/services/test_whatsapp_bridge_outgoing.py
git commit -m "feat: add tests for Whatsap bridge outgoing message handling"
```

### Task 4: Enhance Media Message Handling

**Files:**
- Modify: `bridges/whatsapp/index.js:208-215` (enhance media detection)
- Modify: `backend/services/channels/whatsapp_unified.py:150-195` (enhance Cloud API media sending)
- Modify: `backend/services/channels/whatsapp_unified.py:437-462` (add media sending to bridge)
- Create: `tests/backend/services/test_whatsapp_bridge_media.py`

**Interfaces:**
- Consumes: Media messages from WhatsApp
- Produces: Properly formatted ExternalMessage objects with media metadata

- [ ] **Step 1: Examine existing media message handling in bridge server**

```javascript
// Read the existing media handling in bridges/whatsapp/index.js
// Focus on the message type detection in 'messages.upsert' handler
```

- [ ] **Step 2: Write test to verify image message reception**

```python
def test_whatsapp_bridge_receives_image_message():
    # Test that image messages are detected and caption extracted
    pass
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_media.py::test_whatsapp_bridge_receives_image_message -v`
Expected: PASS

- [ ] **Step 4: Write test to verify document message handling**

```python
def test_whatsapp_bridge_handles_document_message():
    # Test that document messages provide filename and link
    pass
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_media.py::test_whatsapp_bridge_handles_document_message -v`
Expected: PASS

- [ ] **Step 6: Write test to verify video/audio message detection**

```python
def test_whatsapp_bridge_detects_video_audio_messages():
    # Test that video and audio messages are properly detected
    pass
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_media.py::test_whatsapp_bridge_detects_video_audio_messages -v`
Expected: PASS

- [ ] **Step 8: Write test to verify Cloud API media sending**

```python
def test_whatsapp_adapter_sends_media_via_cloud_api():
    # Test that images/documents can be sent via Cloud API
    pass
```

- [ ] **Step 9: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_media.py::test_whatsapp_adapter_sends_media_via_cloud_api -v`
Expected: PASS

- [ ] **Step 10: Write test to implement bridge media sending**

```python
def test_whatsapp_bridge_sends_media_via_bridge():
    # Test implementing media sending for Web Bridge mode
    pass
```

- [ ] **Step 11: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_media.py::test_whatsapp_bridge_sends_media_via_bridge -v`
Expected: PASS

- [ ] **Step 12: Commit**

```bash
git add tests/backend/services/test_whatsapp_bridge_media.py
git commit -m "feat: add tests and implementation for WhatsApp bridge media handling"
```

### Task 5: Verify Reconnection After Disconnect

**Files:**
- Modify: `bridges/whatsapp/index.js:148-198` (verify connection lifecycle handling)
- Modify: `backend/services/channels/whatsapp_unified.py:364-372` (verify disconnected handling)
- Modify: `backend/services/channels/whatsapp_unified.py:378-399` (verify channel status updates)
- Create: `tests/backend/services/test_whatsapp_bridge_reconnect.py`

**Interfaces:**
- Consumes: Connection events from Baileys WebSocket
- Produces: Proper connection state updates and reconnection attempts

- [ ] **Step 1: Examine existing connection lifecycle handling in bridge server**

```javascript
// Read the existing connection handling in bridges/whatsapp/index.js
// Focus on the 'connection.update' event handler
```

- [ ] **Step 2: Write test to verify graceful disconnection handling**

```python
def test_whatsapp_bridge_handles_graceful_disconnect():
    # Test that network disconnections are handled properly
    pass
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_reconnect.py::test_whatsapp_bridge_handles_graceful_disconnect -v`
Expected: PASS

- [ ] **Step 4: Write test to verify session resumption on transient errors**

```python
def test_whatsapp_bridge_resumes_session_on_timeout():
    # Verify that 408 timeouts resume existing session without new QR
    pass
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_reconnect.py::test_whatsapp_bridge_resumes_session_on_timeout -v`
Expected: PASS

- [ ] **Step 6: Write test to verify forced re-authentication on logged out**

```python
def test_whatsapp_bridge_requires_reauth_on_logged_out():
    # Test that logged out state requires new QR code
    pass
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_reconnect.py::test_whatsapp_bridge_requires_reauth_on_logged_out -v`
Expected: PASS

- [ ] **Step 8: Write test to verify exponential backoff reconnect**

```python
def test_whatsapp_bridge_implements_exponential_backoff():
    # Verify reconnection uses exponential backoff delays
    pass
```

- [ ] **Step 9: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_reconnect.py::test_whatsapp_bridge_implements_exponential_backoff -v`
Expected: PASS

- [ ] **Step 10: Write test to verify channel status updates during disconnect/reconnect**

```python
def test_whatsapp_adapter_updates_channel_status_during_reconnect():
    # Verify channel status reflects connection state accurately
    pass
```

- [ ] **Step 11: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_reconnect.py::test_whatsapp_adapter_updates_channel_status_during_reconnect -v`
Expected: PASS

- [ ] **Step 12: Write test to verify keepalive mechanism**

```python
def test_whatsapp_bridge_maintains_keepalive():
    # Test that keepalive pings prevent 408 timeouts
    pass
```

- [ ] **Step 13: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_whatsapp_bridge_reconnect.py::test_whatsapp_bridge_maintains_keepalive -v`
Expected: PASS

- [ ] **Step 14: Commit**

```bash
git add tests/backend/services/test_whatsapp_bridge_reconnect.py
git commit -m "feat: add tests for WhatsApp bridge reconnection handling"
```

### Task 6: Implement End-to-End Verification Flow

**Files:**
- Create: `tests/e2e/test_whatsapp_bridge_flow.cy.js` (if using Cypress) or similar

**Interfaces:**
- Consumes: Full WhatsApp bridge workflow
- Produces: Verified end-to-end functionality

- [ ] **Step 1: Create end-to-end test for complete WhatsApp bridge lifecycle**

```javascript
describe('WhatsApp Bridge End-to-End Flow', () => {
  it('generates QR, authenticates, sends/receives messages, and handles reconnection', () => {
    // Start bridge with no credentials
    cy.startWhatsAppBridge();
    
    // Verify QR code is generated
    cy.get('[data-testid="bridge-qr-code"]').should('be.visible');
    
    // Scan QR code (simulated)
    cy.scanWhatsAppQRCde();
    
    // Verify authentication
    cy.get('[data-testid="bridge-status"]').should('contain', 'authenticated');
    
    // Send message from WhatsApp to backend
    cy.sendMessageFromWhatsApp('Test message from WhatsApp');
    
    // Verify backend received message
    cy.waitForBackendMessage('Test message from WhatsApp');
    
    // Send message from backend to WhatsApp
    cy.sendMessageToWhatsApp('Test message to WhatsApp');
    
    // Verify WhatsApp received message
    cy.waitForWhatsAppMessage('Test message to WhatsApp');
    
    // Test media messages
    cy.sendImageFromWhatsApp('test-image.jpg');
    cy.verifyBackendReceivedImage('test-image.jpg');
    
    // Simulate network disconnect
    cy.simulateNetworkDisconnect();
    
    # Verify reconnection
    cy.waitForBridgeReconnection();
    
    # Test that session was resumed (no new QR)
    cy.get('[data-testid="bridge-qr-code"]').should('not.be.visible');
    
    # Test logged out scenario
    cy.simulateLoggedOut();
    cy.get('[data-testid="bridge-qr-code"]').should('be.visible'); // New QR should appear
    cy.scanWhatsAppQRCde();
    cy.get('[data-testid="bridge-status"]').should('contain', 'authenticated');
  });
});
```

- [ ] **Step 2: Run end-to-end test to verify it passes**

Run: `npx cypress run --spec tests/e2e/test_whatsapp_bridge_flow.cy.js`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_whatsapp_bridge_flow.cy.js
git commit -m "feat: add end-to-end test for WhatsApp bridge verification flow"
```

### Task 7: Review and Finalize Implementation

**Files:**
- Review: All modified and created files

**Interfaces:**
- N/A (review task)

- [ ] **Step 1: Conduct final review of all implemented tests and code**

```bash
# Run all tests to ensure nothing is broken
python -m pytest tests/ -v
npm test
```

- [ ] **Step 2: Verify all TODO requirements are met**

Check that:
1. ✅ **11.2.1**: QR code pairing flow works end-to-end
2. ✅ **11.2.2**: Incoming WhatsApp messages are received and processed
3. ✅ **11.2.3**: Agent responses are sent back via WhatsApp
4. ✅ **11.2.4**: Media messages (images, audio, video, documents) are handled
5. ✅ **11.2.5**: Reconnection after disconnect works properly

- [ ] **Step 3: Commit final changes**

```bash
git add .
git commit -m "feat: complete WhatsApp bridge verification and improvement implementation"
```