# WhatsApp Bridge Verification and Improvement Design

**Date**: 2026-09-20  
**Related TODO**: @docs/documents/TODO.md section 11.2 — WhatsApp Bridge  
**Status**: Ready for Implementation  

## Overview

This document outlines the verification and improvement plan for the WhatsApp Bridge subsystem (TODO items 11.2.1 through 11.2.5). The goal is to ensure that all WhatsApp bridge features work correctly, including QR code pairing, message sending/receiving, media handling, and reconnection capabilities.

## Current State Analysis

Based on code examination, the WhatsApp bridge system consists of:

1. **Node.js Bridge Server** (`bridges/whatsapp/index.js`): WebSocket server that connects to WhatsApp via Baileys library
2. **Unified WhatsApp Adapter** (`backend/services/channels/whatsapp_unified.py`): Python adapter supporting both Cloud API and Web Bridge modes
3. **Channel Manager Integration**: Routes messages through the central ChannelManager service
4. **Configuration**: Supports both official Cloud API (production) and Web Bridge (development) providers

## Design Sections

### 1. QR Code Pairing Flow (11.2.1)

**Objective**: Verify that the QR code pairing flow works end-to-end from backend request to WhatsApp authentication.

**Current Implementation Review**:
- Bridge server generates QR code when no saved credentials exist
- QR code is broadcast to connected backend clients via WebSocket
- Backend receives QR code through `_handle_bridge_message` -> stores in `BridgeConnection`
- Adapter exposes QR code through `get_status()` method
- Frontend should display QR code for user to scan

**Verification Approach**:
- Test that bridge generates QR code on startup when no credentials exist
- Verify QR code is properly formatted and includes expiration timestamp
- Confirm backend receives and stores QR code correctly
- Test that scanning QR code leads to authenticated state
- Validate that credentials are saved for subsequent connections

**Potential Enhancements**:
- Add QR code regeneration after expiration
- Improve QR code display in frontend with scanning instructions
- Add timeout handling for QR code scanning
- Implement QR code refreshing without full reconnect

### 2. Incoming Message Handling (11.2.2)

**Objective**: Verify that incoming WhatsApp messages are received and processed correctly.

**Current Implementation Review**:
- Bridge receives messages via `sock.ev.on('messages.upsert')`
- Filters out self-sent messages and broadcast lists
- Extracts text content from various message types
- Broadcasts to backend WebSocket clients with metadata
- Adapter processes bridge messages in `_handle_bridge_message` -> `_process_bridge_incoming`
- Routes through `ChannelManager.receive_message()` with proper formatting

**Verification Approach**:
- Test text message reception and content extraction
- Verify handling of different message types (image, video, document, etc.)
- Confirm proper sender ID formatting (removing @s.whatsapp.net suffix)
- Test group message detection and handling
- Validate message routing through ChannelManager
- Check timestamp conversion and formatting

**Potential Enhancements**:
- Better media message handling (download and store media)
- Improved contact name resolution
- Read receipts and typing indicators
- Message editing and deletion support

### 3. Outbound Message Handling (11.2.3)

**Objective**: Verify that agent responses are sent back via WhatsApp correctly.

**Current Implementation Review**:
- Backend sends message through ChannelManager to adapter's `send_message` method
- Adapter delegates to `_send_bridge` for Web Bridge mode
- Builds proper payload with recipient JID and message content
- Sends via WebSocket connection to bridge
- Bridge forwards to WhatsApp via Baileys `sock.sendMessage`

**Verification Approach**:
- Test text message sending through both Cloud API and Web Bridge
- Verify proper JID formatting for recipients
- Confirm message delivery receipts are handled
- Test error handling for disconnected/reconnecting states
- Validate rate limiting and retry logic (especially for Cloud API)

**Potential Enhancements**:
- Media message sending (images, documents, etc.)
- Interactive message templates (buttons, lists)
- Location and contact sharing
- Sticker and gif support

### 4. Media Message Handling (11.2.4)

**Objective**: Verify that media messages (images, audio, video, documents) are handled correctly.

**Current Implementation Review**:
- Incoming: Bridge detects media type and extracts caption or provides placeholder
- Outgoing: Adapter builds appropriate payload based on media type (Cloud API only)
- Web Bridge mode: Currently only supports text messages in `_send_bridge`

**Verification Approach**:
- Test receiving image messages and extracting captions
- Verify document message handling with filename and link
- Test video and audio message detection
- Confirm outgoing media sending works via Cloud API
- Identify gaps in Web Bridge media support

**Potential Enhancements**:
- Implement media sending for Web Bridge mode
- Add media download and storage for incoming media
- Support for different media types (stickers, contacts, etc.)
- Media message preview generation
- File size and type validation

### 5. Reconnection After Disconnect (11.2.5)

**Objective**: Verify that reconnection after disconnect works properly.

**Current Implementation Review**:
- Bridge listens for 'connection.update' events from Baileys
- Handles various disconnect reasons (loggedOut, timeout, network errors)
- Implements exponential backoff reconnect mechanism
- Preserves QR state when appropriate (timeout vs logged out)
- Sends disconnection events to backend clients
- Adapter detects disconnected state and updates channel status

**Verification Approach**:
- Test graceful disconnection (network interruption)
- Verify reconnection with same session when possible
- Test forced re-authentication (logged out scenario)
- Confirm proper state reset and QR code regeneration
- Validate channel status updates during disconnect/reconnect
- Test keepalive mechanism to prevent idle timeouts

**Potential Enhancements**:
- Improve reconnection logic with better backoff strategies
- Add connection quality monitoring and metrics
- Implement manual reconnect trigger in frontend
- Better error reporting for different failure modes
- Add connection health endpoints

## Dependencies

1. **Backend Services**:
   - ChannelManager service for message routing
   - Database for storing channel configuration and state
   - Redis for rate limiting and circuit breaker (shared with other channels)
   - Working WebSocket server for real-time communication

2. **Bridge Dependencies**:
   - Node.js `@whiskeysockets/baileys` library for WhatsApp Web implementation
   - Express.js for HTTP endpoints
   - WebSocket server for backend communication
   - Pino for logging

3. **External Services**:
   - WhatsApp Business Account (for Cloud API mode)
   - Smartphone with WhatsApp (for Web Bridge mode)
   - Stable internet connection for both bridge and client

## Testing Strategy

**Manual Verification**:
1. Start bridge server with no saved credentials
2. Verify QR code generation and display
3. Scan QR code with WhatsApp and verify authentication
4. Send test messages from WhatsApp to backend and verify reception
5. Send test messages from backend to WhatsApp and verify delivery
6. Test media messages in both directions
7. Simulate network disconnect and verify reconnection
8. Test logged out scenario and re-authentication flow
9. Verify both Cloud API and Web Bridge modes work correctly

**Automated Testing** (if tests exist or need to be created):
1. Unit tests for WhatsApp adapter methods
2. Integration tests for bridge connection lifecycle
3. API tests for webhook handling (Cloud API)
4. End-to-end tests for message flow
5. Load testing for concurrent connections

## Success Criteria

All TODO items will be considered complete when:

1. ✅ **11.2.1**: QR code pairing flow works end-to-end - users can scan QR code to authenticate WhatsApp
2. ✅ **11.2.2**: Incoming WhatsApp messages are received and processed correctly by the backend
3. ✅ **11.2.3**: Agent responses are sent back via WhatsApp and delivered to recipients
4. ✅ **11.2.4**: Media messages (images, audio, video, documents) are handled appropriately in both directions
5. ✅ **11.2.5**: Reconnection after disconnect works properly with session resumption when possible

## Open Questions

1. Should we implement richer media support for Web Bridge mode (currently limited)?
2. Should we add message reply/forwarding capabilities?
3. Should we implement end-to-end encryption verification for security-conscious users?
4. Should we add support for WhatsApp Business features like catalogs and automated greetings?
5. What level of message history synchronization should we implement on reconnect?

## Approval

This design is ready for review. Please provide feedback or approval to proceed with implementation planning.

---
*This document follows the brainstorming skill process and presents the design for user approval before proceeding to implementation planning.*