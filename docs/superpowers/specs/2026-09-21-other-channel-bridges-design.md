# Other Channel Bridges Verification Design

**Date**: 2026-09-21  
**Related TODO**: @docs/documents/TODO.md section 11.3 — Other Channel Bridges  
**Status**: Ready for Implementation  

## Overview

This document outlines the verification plan for the Other Channel Bridges subsystem (TODO items 11.3.1 through 11.3.6). The goal is to verify that all remaining channel bridges (Slack, Telegram, Discord, Email, SMS/Twilio, Signal, Google Chat, Teams, Matrix, iMessage, and Zalo) can send and receive messages correctly.

## Current State Analysis

Based on code examination, the channel bridge system appears to have the following implementations:

1. **Slack Adapter** (`backend/services/channels/slack.py`): Implements Slack Web API integration
2. **Telegram Adapter**: Not found in current codebase - needs verification
3. **Discord Adapter**: Not found in current codebase - needs verification  
4. **Email Adapter**: Not found in current codebase - needs verification
5. **SMS/Twilio Adapter**: Not found in current codebase - needs verification (though Twilio references exist in config and voice files)
6. **Signal Adapter**: Not found in current codebase - needs verification
7. **Google Chat Adapter**: Not found in current codebase - needs verification
8. **Teams Adapter**: Not found in current codebase - needs verification
9. **Matrix Adapter**: Not found in current codebase - needs verification
10. **iMessage Adapter**: Not found in current codebase - needs verification (macOS-only)
11. **Zalo Adapter**: Not found in current codebase - needs verification

The Slack adapter is the only one confirmed to exist in the codebase. The others either need to be verified as existing or may need to be implemented.

## Design Sections

### 1. Slack Integration Verification (11.3.1)

**Objective**: Verify that Slack integration sends and receives messages correctly.

**Verification Criteria**:
- Slack adapter can send messages via Web API
- Slack adapter can receive messages via Events API or RTM
- Message formatting is correct for both directions
- Error handling works for invalid tokens, rate limits, etc.
- Channel/subscription management works correctly

**Current Implementation Review**:
From examining `backend/services/channels/slack.py`:
- Uses `chat.postMessage` endpoint for sending messages
- Has `send_message()` instance method and `send_plain_message()` class method
- Validates configuration requires `bot_token`
- Proper error handling with logging

**Verification Approach**:
- Test message sending with valid/invalid configurations
- Verify message receipt through event handling (if implemented)
- Check that message content is properly formatted
- Validate error cases return appropriate responses

### 2. Telegram Bot Integration Verification (11.3.2)

**Objective**: Verify that Telegram bot integration works for sending/receiving messages.

**Verification Criteria**:
- Telegram adapter can send messages via Bot API
- Telegram adapter can receive messages via long polling or webhooks
- Message formatting supports text, media, etc.
- Bot token validation works correctly
- Webhook setup and management functions properly

**Implementation Status**: Not found in current codebase - needs verification of existence or implementation.

### 3. Discord Gateway Integration Verification (11.3.3)

**Objective**: Verify that Discord gateway integration works for sending/receiving messages.

**Verification Criteria**:
- Discord adapter can send messages via REST API
- Discord adapter can receive messages via Gateway/WebSocket
- Message formatting supports embeds, attachments, etc.
- Bot token validation works correctly
- Rate limit handling implements Discord's rate limit system

**Implementation Status**: Not found in current codebase - needs verification of existence or implementation.

### 4. Email (IMAP/SMTP) Send/Receive Verification (11.3.4)

**Objective**: Verify that Email integration works for both sending (SMTP) and receiving (IMAP) messages.

**Verification Criteria**:
- Email adapter can send messages via SMTP
- Email adapter can receive messages via IMAP
- Message formatting supports plain text, HTML, attachments
- TLS/SSL connection handling works correctly
- Authentication mechanisms (plain, login, etc.) function properly
- Folder selection and message marking works for IMAP

**Implementation Status**: Not found in current codebase - needs verification of existence or implementation.

### 5. SMS (Twilio) Integration Verification (11.3.5)

**Objective**: Verify that SMS/Twilio integration works for sending/receiving messages.

**Verification Criteria**:
- SMS adapter can send messages via Twilio API
- SMS adapter can receive messages via Twilio webhooks
- Message formatting supports text messages
- Account SID and Auth Token validation works correctly
- Webhook signature validation prevents spoofing
- Status callbacks track message delivery status

**Implementation Status**: Twilio references found in config and voice files, but no dedicated SMS adapter found in channel services.

### 6. Signal / Google Chat / Teams / Matrix / iMessage / Zalo Status Verification (11.3.6)

**Objective**: Verify the status of remaining channel bridges as documented in TODO.

**Verification Criteria per Channel**:
- **Signal**: Verify signal-cli JSON-RPC daemon integration works
- **Google Chat**: Verify Bot API integration works (webhook-based)
- **Teams**: Verify Incoming Webhook or Bot Framework integration works
- **Matrix**: Verify Client-Server API integration works
- **iMessage**: Verify macOS-only AppleScript or BlueBubbles integration works
- **Zalo**: Verify Official Account API integration works

For each channel:
- Confirm adapter implementation exists
- Verify message sending capability
- Verify message receiving capability (if applicable)
- Check authentication mechanism works
- Validate error handling and edge cases

## Hybrid Testing Approach

As selected in the brainstorming session, we will use a hybrid approach combining:

1. **Unit Tests**: For adapter logic, configuration validation, and message formatting
2. **Selective Integration Tests**: Using test/sandbox credentials where available
3. **Manual Verification**: For channels requiring real service accounts
4. **Documentation Review**: For channels where implementation exists but needs verification

## Components and Data Flow

### Common Architecture
All channel bridges follow a similar pattern:
1. **Adapter Layer**: Channel-specific implementation in `backend/services/channels/`
2. **Channel Manager**: Routes messages to appropriate adapter (`backend/services/channel_manager.py`)
3. **API Layer**: Endpoints for channel management and messaging (`backend/api/routes/`)
4. **Storage**: Channel configurations and message history in database
5. **Frontend**: UI for channel configuration and message viewing

### Data Flow for Outbound Messages
1. User sends message via frontend/API
2. Message goes to ChannelManager
3. ChannelManager looks up channel configuration
4. ChannelManager delegates to appropriate channel adapter
5. Adapter formats message for specific platform API
6. Adapter sends message via platform's API/webhook
7. Platform delivers message to end user
8. Any response/error is captured by adapter and reported back

### Data Flow for Inbound Messages
1. Platform sends message to webhook/API endpoint
2. Backend receives and validates incoming request
3. Request is routed to appropriate channel adapter
4. Adapter parses platform-specific message format
5. Adapter converts to internal ExternalMessage format
6. Message is stored in database and forwarded to appropriate agent
7. Agent processes message and may send response
8. Response follows outbound message flow above

## Error Handling and Edge Cases

### Common Error Handling
- **Authentication Failures**: Invalid tokens/credentials return appropriate errors
- **Rate Limiting**: Respect platform rate limits with exponential backoff
- **Network Issues**: Retry mechanisms for transient failures
- **Invalid Message Content**: Validate and sanitize before sending
- **Webhook Security**: Verify signatures for incoming webhooks where applicable
- **Configuration Errors**: Missing or invalid config values caught early

### Channel-Specific Considerations
- **Slack**: Handle event verification, rate limits (1 msg/sec), message formatting blocks
- **Telegram**: Handle long polling vs webhooks, message size limits, markdown formatting
- **Discord**: Handle rate limits (5 req/5s), embed limits, message formatting
- **Email**: Handle connection timeouts, TLS negotiation, attachment MIME types
- **SMS/Twilio**: Handle media messages, status callbacks, opt-out management
- **Signal**: Handle encryption/decryption, device registration, message timing
- **Google Chat**: Handle bot vs webhook modes, card formatting, async processing
- **Teams**: Handle Bot Framework vs webhook, activity types, adaptive cards
- **Matrix**: Handle room membership, event types, encryption, syncing
- **iMessage**: Handle AppleScript execution, BlueBubbles connectivity, message formatting
- **Zalo**: Handle OA API rates, message templates, multimedia messages

## Testing Strategy

### Unit Tests
Each channel adapter should have tests for:
- Configuration validation (required fields, formats)
- Message formatting for outbound messages
- Message parsing for inbound messages
- Error handling for common failure scenarios
- Edge cases specific to each platform

### Integration Tests
Where test/sandbox credentials are available:
- Slack: Use test workspace with limited scopes
- Telegram: Use botfather test bot or local testing
- Email: Use test SMTP/IMAP server (e.g., MailHog)
- Others: Use platform-provided sandbox/test environments when available

### Manual Verification
For channels requiring real service accounts:
- Create test accounts/configurations in controlled environment
- Verify end-to-end message flow
- Test error conditions and recovery
- Validate security considerations

### Verification Checklist per Channel
1. [ ] Adapter implementation exists and follows base adapter pattern
2. [ ] Configuration validation works correctly
3. [ ] Outbound message sending works with valid configuration
4. [ ] Outbound message error handling works correctly
5. [ ] Inbound message reception works (if applicable)
6. [ ] Inbound message parsing works correctly
7. [ ] Message formatting matches platform expectations
8. [ ] Security considerations implemented (token handling, webhook validation)
9. [ ] Rate limiting handled appropriately
10. [ ] Integration with ChannelManager verified

## Dependencies

### Backend Services
- Database (PostgreSQL) for channel and message persistence
- Redis for rate limiting and temporary state
- Working adapter services for each channel type
- HTTP client for outgoing requests (httpx)

### Frontend Dependencies
- Channel configuration forms in ChannelsPage
- Message display components
- Health monitoring displays

### External Services (for full testing)
- Slack: Slack workspace with bot token
- Telegram: Telegram bot token from BotFather
- Discord: Discord application with bot token
- Email: Valid SMTP/IMAP email account
- SMS/Twilio: Twilio Account SID and Auth Token
- Signal: signal-cli installed and registered
- Google Chat: Google Cloud project with Bot API enabled
- Teams: Microsoft Azure application with Bot Framework credentials
- Matrix: Matrix homeserver access and access token
- iMessage: macOS server with Messages.app or BlueBubbles
- Zalo: Zalo Official Account with OA ID and access token

## Success Criteria

All TODO items will be considered complete when:

1. ✅ **11.3.1**: Slack integration sends/receives messages correctly
2. ✅ **11.3.2**: Telegram bot integration works for sending/receiving messages
3. ✅ **11.3.3**: Discord gateway integration works for sending/receiving messages
4. ✅ **11.3.4**: Email (IMAP/SMTP) send/receive works correctly
5. ✅ **11.3.5**: SMS (Twilio) integration works for sending/receiving messages
6. ✅ **11.3.6**: Signal / Google Chat / Teams / Matrix / iMessage / Zalo status verified as per @docs/documents/TODO.md

## Open Questions

1. Which channel adapters currently exist in the codebase versus need to be implemented?
2. What level of testing is feasible for each channel given credential availability?
3. Should we prioritize certain channels over others based on user needs?
4. Are there any platform-specific limitations or special considerations we need to account for?
5. How should we handle channels that require special hardware/OS (like iMessage requiring macOS)?

## Approval

This design is ready for review. Please provide feedback or approval to proceed with implementation planning.

---
*This document follows the brainstorming skill process and presents the design for user approval before proceeding to implementation planning.*