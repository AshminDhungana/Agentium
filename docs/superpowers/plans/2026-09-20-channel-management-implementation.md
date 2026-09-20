# Channel Management Verification and Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement verification and improvements for channel management features per TODO items 11.1.1 through 11.1.4, ensuring channel listing endpoint works correctly, channel creation works for all types, health status accurately reflects connectivity, and frontend displays appropriate health indicators.

**Architecture:** This implementation focuses on verification of existing functionality and targeted enhancements where gaps are identified. We'll leverage the existing channel manager service, API routes, and frontend components, adding tests and minor improvements to ensure complete coverage of the TODO requirements.

**Tech Stack:** Python (FastAPI/Starlette), TypeScript/React, PostgreSQL, Redis, React Query

## Global Constraints

- Maintain backward compatibility with existing channel management functionality
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

### Task 1: Verify GET /api/v1/channels Endpoint Functionality

**Files:**
- Modify: `backend/api/routes/channels.py:1-50` (verify existing implementation)
- Create: `tests/backend/api/test_channels_list.py`

**Interfaces:**
- Consumes: ChannelManager service dependency
- Produces: JSON array of channel objects with id, name, type, status, configuration (sanitized), stats, timestamps

- [ ] **Step 1: Examine existing GET /api/v1/channels implementation**

```python
# Read the existing channels API route to understand current implementation
# Focus on the list_channels function
```

- [ ] **Step 2: Write test to verify endpoint returns HTTP 200 for authenticated users**

```python
def test_list_channels_returns_200_for_authenticated_user(client, auth_headers):
    response = client.get("/api/v1/channels", headers=auth_headers)
    assert response.status_code == 200
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/backend/api/test_channels_list.py::test_list_channels_returns_200_for_authenticated_user -v`
Expected: PASS (if endpoint is already implemented correctly)

- [ ] **Step 4: Write test to verify response includes all channels regardless of status/type**

```python
def test_list_channels_includes_all_channels(client, auth_headers, test_channels):
    response = client.get("/api/v1/channels", headers=auth_headers)
    data = response.json()
    assert len(data) == len(test_channels)
    # Verify each test channel is in the response
    channel_ids = [ch["id"] for ch in data]
    for test_channel in test_channels:
        assert test_channel.id in channel_ids
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/backend/api/test_channels_list.py::test_list_channels_includes_all_channels -v`
Expected: PASS

- [ ] **Step 6: Write test to verify response includes pagination/status filtering capabilities**

```python
def test_list_channels_supports_pagination_and_filtering(client, auth_headers, test_channels):
    # Test pagination
    response = client.get("/api/v1/channels?limit=2", headers=auth_headers)
    data = response.json()
    assert len(data) <= 2
    
    # Test status filtering (if implemented)
    response = client.get("/api/v1/channels?status=active", headers=auth_headers)
    data = response.json()
    # All returned channels should have status=active
    for channel in data:
        assert channel["status"] == "active"
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/backend/api/test_channels_list.py::test_list_channels_supports_pagination_and_filtering -v`
Expected: PASS

- [ ] **Step 8: Write test to verify channel data includes essential fields**

```python
def test_list_channels_response_includes_essential_fields(client, auth_headers, test_channel):
    response = client.get("/api/v1/channels", headers=auth_headers)
    data = response.json()
    channel = next((ch for ch in data if ch["id"] == test_channel.id), None)
    assert channel is not None
    assert "id" in channel
    assert "name" in channel
    assert "type" in channel
    assert "status" in channel
    assert "configuration" in channel  # Should be sanitized
    assert "stats" in channel
    assert "created_at" in channel
    assert "updated_at" in channel
```

- [ ] **Step 9: Run test to verify it passes**

Run: `python -m pytest tests/backend/api/test_channels_list.py::test_list_channels_response_includes_essential_fields -v`
Expected: PASS

- [ ] **Step 10: Write test to verify error handling for unauthorized access**

```python
def test_list_channels_returns_401_for_unauthorized(client):
    response = client.get("/api/v1/channels")
    assert response.status_code == 401
```

- [ ] **Step 11: Run test to verify it passes**

Run: `python -m pytest tests/backend/api/test_channels_list.py::test_list_channels_returns_401_for_unauthorized -v`
Expected: PASS

- [ ] **Step 12: Commit**

```bash
git add tests/backend/api/test_channels_list.py
git commit -m "feat: add tests for GET /api/v1/channels endpoint verification"
```

### Task 2: Verify Channel Creation for All Types

**Files:**
- Modify: `backend/api/routes/channels.py:51-150` (verify existing create implementation)
- Modify: `frontend/src/pages/ChannelsPage.tsx:200-300` (verify form handling for all types)
- Create: `tests/backend/api/test_channels_create.py`
- Create: `tests/frontend/testChannelsPageCreate.test.tsx` (if frontend tests exist)

**Interfaces:**
- Consumes: Channel creation request with type-specific configuration
- Produces: Created channel object with agentium_id, webhook URL, etc.

- [ ] **Step 1: Examine existing POST /api/v1/channels implementation**

```python
# Read the existing create channel endpoint to understand current implementation
# Focus on the create_channel function
```

- [ ] **Step 2: Write test to verify WhatsApp channel creation (cloud_api provider)**

```python
def test_create_whatsapp_channel_cloud_api(client, auth_headers):
    channel_data = {
        "name": "Test WhatsApp Cloud API",
        "type": "whatsapp",
        "provider": "cloud_api",
        "configuration": {
            "phone_number_id": "123456789",
            "access_token": "test_token",
            "verify_token": "test_verify",
            "webhook_url": "https://example.com/webhook"
        }
    }
    response = client.post("/api/v1/channels", json=channel_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "whatsapp"
    assert data["provider"] == "cloud_api"
    assert data["agentium_id"].startswith("CH")
    # Webhook URL should be generated
    assert "webhook_url" in data
    assert data["webhook_url"] is not None
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/backend/api/test_channels_create.py::test_create_whatsapp_channel_cloud_api -v`
Expected: PASS

- [ ] **Step 4: Write test to verify WhatsApp channel creation (web_bridge provider)**

```python
def test_create_whatsapp_channel_web_bridge(client, auth_headers, monkeypatch):
    # Mock environment variable substitution
    monkeypatch.setenv("WHATSAPP_WEB_BRIDGE_TOKEN", "test_token")
    channel_data = {
        "name": "Test WhatsApp Web Bridge",
        "type": "whatsapp",
        "provider": "web_bridge",
        "configuration": {
            "jid": "123456789@s.whatsapp.net",
            "token": "${WHATSAPP_WEB_BRIDGE_TOKEN}",
            "webhook_url": "https://example.com/webhook"
        }
    }
    response = client.post("/api/v1/channels", json=channel_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "whatsapp"
    assert data["provider"] == "web_bridge"
    # Token should have environment variable substituted
    assert data["configuration"]["token"] == "test_token"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/backend/api/test_channels_create.py::test_create_whatsapp_channel_web_bridge -v`
Expected: PASS

- [ ] **Step 6: Write test to verify Slack channel creation**

```python
def test_create_slack_channel(client, auth_headers):
    channel_data = {
        "name": "Test Slack",
        "type": "slack",
        "configuration": {
            "bot_token": "xoxb-test-token",
            "signing_secret": "test-secret",
            "webhook_url": "https://example.com/webhook"
        }
    }
    response = client.post("/api/v1/channels", json=channel_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "slack"
    assert data["agentium_id"].startswith("CH")
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/backend/api/test_channels_create.py::test_create_slack_channel -v`
Expected: PASS

- [ ] **Step 8: Write test to verify Telegram channel creation**

```python
def test_create_telegram_channel(client, auth_headers):
    channel_data = {
        "name": "Test Telegram",
        "type": "telegram",
        "configuration": {
            "bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            "webhook_url": "https://example.com/webhook"
        }
    }
    response = client.post("/api/v1/channels", json=channel_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "telegram"
    assert data["agentium_id"].startswith("CH")
```

- [ ] **Step 9: Run test to verify it passes**

Run: `python -m pytest tests/backend/api/test_channels_create.py::test_create_telegram_channel -v`
Expected: PASS

- [ ] **Step 10: Write test to verify Email channel creation**

```python
def test_create_email_channel(client, auth_headers):
    channel_data = {
        "name": "Test Email",
        "type": "email",
        "configuration": {
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "imap_user": "test@example.com",
            "imap_pass": "test_password",
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_user": "test@example.com",
            "smtp_pass": "test_password",
            "webhook_url": "https://example.com/webhook"
        }
    }
    response = client.post("/api/v1/channels", json=channel_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "email"
    assert data["agentium_id"].startswith("CH")
    # Passwords should not be returned in response
    assert "imap_pass" not in str(data)
    assert "smtp_pass" not in str(data)
```

- [ ] **Step 11: Run test to verify it passes**

Run: `python -m pytest tests/backend/api/test_channels_create.py::test_create_email_channel -v`
Expected: PASS

- [ ] **Step 12: Write test to verify Discord channel creation**

```python
def test_create_discord_channel(client, auth_headers):
    channel_data = {
        "name": "Test Discord",
        "type": "discord",
        "configuration": {
            "bot_token": "MjM4NTY5NjczMTQ4NDQwMAAA.test_token",
            "webhook_url": "https://example.com/webhook"
        }
    }
    response = client.post("/api/v1/channels", json=channel_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "discord"
    assert data["agentium_id"].startswith("CH")
```

- [ ] **Step 13: Run test to verify it passes**

Run: `python -m pytest tests/backend/api/test_channels_create.py::test_create_discord_channel -v`
Expected: PASS

- [ ] **Step 14: Write test to verify default values are applied appropriately**

```python
def test_create_channel_applies_default_values(client, auth_headers):
    channel_data = {
        "name": "Test Defaults",
        "type": "slack",
        "configuration": {
            "bot_token": "xoxb-test",
            "signing_secret": "test",
            "webhook_url": "https://example.com/webhook"
            # Not providing auto_create_tasks or require_approval
        }
    }
    response = client.post("/api/v1/channels", json=channel_data, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    # Check that defaults are applied
    assert data["configuration"]["auto_create_tasks"] == True
    assert data["configuration"]["require_approval"] == False
```

- [ ] **Step 15: Run test to verify it passes**

Run: `python -m pytest tests/backend/api/test_channels_create.py::test_create_channel_applies_default_values -v`
Expected: PASS

- [ ] **Step 16: Write test to verify agentium_id is generated sequentially**

```python
def test_create_channel_sequential_agentium_ids(client, auth_headers):
    # Create first channel
    channel_data1 = {
        "name": "First Channel",
        "type": "slack",
        "configuration": {
            "bot_token": "xoxb-test1",
            "signing_secret": "test1",
            "webhook_url": "https://example.com/webhook"
        }
    }
    response1 = client.post("/api/v1/channels", json=channel_data1, headers=auth_headers)
    data1 = response1.json()
    
    # Create second channel
    channel_data2 = {
        "name": "Second Channel",
        "type": "slack",
        "configuration": {
            "bot_token": "xoxb-test2",
            "signing_secret": "test2",
            "webhook_url": "https://example.com/webhook"
        }
    }
    response2 = client.post("/api/v1/channels", json=channel_data2, headers=auth_headers)
    data2 = response2.json()
    
    # Verify sequential IDs
    assert data1["agentium_id"] == "CH0001"
    assert data2["agentium_id"] == "CH0002"
```

- [ ] **Step 17: Run test to verify it passes**

Run: `python -m pytest tests/backend/api/test_channels_create.py::test_create_channel_sequential_agentium_ids -v`
Expected: PASS

- [ ] **Step 18: Write test to verify error handling for invalid configurations**

```python
def test_create_channel_returns_400_for_invalid_configuration(client, auth_headers):
    channel_data = {
        "name": "Invalid Channel",
        "type": "whatsapp",
        # Missing required phone_number_id for cloud_api
        "provider": "cloud_api",
        "configuration": {
            "access_token": "test_token",
            "webhook_url": "https://example.com/webhook"
        }
    }
    response = client.post("/api/v1/channels", json=channel_data, headers=auth_headers)
    assert response.status_code == 400
    assert "phone_number_id" in response.json()["detail"]
```

- [ ] **Step 19: Run test to verify it passes**

Run: `python -m pytest tests/backend/api/test_channels_create.py::test_create_channel_returns_400_for_invalid_configuration -v`
Expected: PASS

- [ ] **Step 20: Commit**

```bash
git add tests/backend/api/test_channels_create.py
git commit -m "feat: add tests for channel creation verification for all types"
```

### Task 3: Verify Channel Health Status Accuracy

**Files:**
- Modify: `backend/services/channel_manager.py:200-300` (verify health monitoring)
- Modify: `backend/api/routes/channels.py:200-250` (verify health endpoint)
- Create: `tests/backend/services/test_channel_manager_health.py`
- Create: `tests/backend/api/test_channels_health.py`

**Interfaces:**
- Consumes: Channel metrics and status updates
- Produces: Health status data including circuit breaker state, success rate, error counts, etc.

- [ ] **Step 1: Examine existing ChannelManager.get_channel_health() implementation**

```python
# Read the existing health monitoring implementation in channel_manager.py
```

- [ ] **Step 2: Write test to verify circuit breaker state reporting**

```python
def test_channel_manager_reports_circuit_breaker_state(channel_manager):
    # Simulate channel with CLOSED circuit breaker (normal state)
    health = channel_manager.get_channel_health("test_channel_id")
    assert health["circuit_breaker"]["state"] in ["CLOSED", "OPEN", "HALF_OPEN"]
    
    # Simulate failures to trigger OPEN state
    for _ in range(5):  # Assuming threshold is 5
        channel_manager.record_failure("test_channel_id", Exception("Test failure"))
    
    health = channel_manager.get_channel_health("test_channel_id")
    assert health["circuit_breaker"]["state"] == "OPEN"
    assert health["circuit_breaker"]["consecutive_failures"] >= 5
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_channel_manager_health.py::test_channel_manager_reports_circuit_breaker_state -v`
Expected: PASS

- [ ] **Step 4: Write test to verify success rate calculation accuracy**

```python
def test_channel_manager_calculates_success_rate_accurately(channel_manager):
    # Record some successes and failures
    for _ in range(7):
        channel_manager.record_success("test_channel_id")
    for _ in range(3):
        channel_manager.record_failure("test_channel_id", Exception("Test failure"))
    
    health = channel_manager.get_channel_health("test_channel_id")
    # Success rate should be 7/(7+3) = 70%
    assert health["metrics"]["success_rate"] == 70.0
    assert health["metrics"]["total_requests"] == 10
    assert health["metrics"]["successful_requests"] == 7
    assert health["metrics"]["failed_requests"] == 3
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_channel_manager_health.py::test_channel_manager_calculates_success_rate_accurately -v`
Expected: PASS

- [ ] **Step 6: Write test to verify error counts increment correctly**

```python
def test_channel_manager_tracks_error_counts(channel_manager):
    # Record some failures
    for _ in range(4):
        channel_manager.record_failure("test_channel_id", Exception("Test failure"))
    
    health = channel_manager.get_channel_health("test_channel_id")
    assert health["metrics"]["failed_requests"] == 4
    assert health["metrics"]["consecutive_failures"] == 4
    
    # Record a success to reset consecutive failures
    channel_manager.record_success("test_channel_id")
    
    health = channel_manager.get_channel_health("test_channel_id")
    assert health["metrics"]["consecutive_failures"] == 0
    assert health["metrics"]["failed_requests"] == 4  # Total should remain
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_channel_manager_health.py::test_channel_manager_tracks_error_counts -v`
Expected: PASS

- [ ] **Step 8: Write test to verify health status transitions properly**

```python
def test_channel_manager_health_status_transitions(channel_manager):
    # Start with healthy state (few failures)
    for _ in range(2):
        channel_manager.record_failure("test_channel_id", Exception("Test"))
    for _ in range(8):
        channel_manager.record_success("test_channel_id")
    
    health = channel_manager.get_channel_health("test_channel_id")
    # Should be healthy with 80% success rate
    assert health["status"] == "healthy"
    assert health["metrics"]["success_rate"] == 80.0
    
    # Add failures to reach warning threshold
    for _ in range(3):
        channel_manager.record_failure("test_channel_id", Exception("Test"))
    
    health = channel_manager.get_channel_health("test_channel_id")
    # Should be warning with ~67% success rate
    assert health["status"] == "warning"
    assert health["metrics"]["success_rate"] == 40.0  # 8/12
    
    # Add more failures to reach critical threshold
    for _ in range(4):
        channel_manager.record_failure("test_channel_id", Exception("Test"))
    
    health = channel_manager.get_channel_health("test_channel_id")
    # Should be critical with low success rate
    assert health["status"] == "critical"
    assert health["metrics"]["success_rate"] == 30.0  # 8/16
```

- [ ] **Step 9: Run test to verify it passes**

Run: `python -m pytest tests/backend/services/test_channel_manager_health.py::test_channel_manager_health_status_transitions -v`
Expected: PASS

- [ ] **Step 10: Write test to verify channel health endpoint returns correct data**

```python
def test_channel_health_endpoint_returns_correct_data(client, auth_headers, test_channel):
    response = client.get(f"/api/v1/channels/{test_channel.id}/health", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    
    # Verify basic structure
    assert "status" in data
    assert "circuit_breaker" in data
    assert "statistics" in data
    assert "rate_limits" in data
    
    # Verify circuit breaker data
    assert "state" in data["circuit_breaker"]
    assert "metrics" in data["circuit_breaker"]
    
    # Verify statistics
    assert "total_messages" in data["statistics"]
    assert "error_count" in data["statistics"]
    assert "error_count_24h" in data["statistics"]
    assert "last_message_at" in data["statistics"]
    
    # Verify rate limits
    assert "current_usage" in data["rate_limits"]
    assert "utilization_percentage" in data["rate_limits"]
    assert "limit" in data["rate_limits"]
```

- [ ] **Step 11: Run test to verify it passes**

Run: `python -m pytest tests/backend/api/test_channels_health.py::test_channel_health_endpoint_returns_correct_data -v`
Expected: PASS

- [ ] **Step 12: Commit**

```bash
git add tests/backend/services/test_channel_manager_health.py tests/backend/api/test_channels_health.py
git commit -m "feat: add tests for channel health status accuracy verification"
```

### Task 4: Enhance ChannelsPage Health Indicators Display

**Files:**
- Modify: `frontend/src/pages/ChannelsPage.tsx:100-200` (enhance health display if needed)
- Modify: `frontend/src/utils/healthUtils.ts` (create/update health utility functions)
- Create: `tests/frontend/testChannelsPageHealth.test.tsx`

**Interfaces:**
- Consumes: Channel metrics data from batched query
- Produces: Enhanced health visualization with tooltips, trend indicators, etc.

- [ ] **Step 1: Examine existing ChannelsPage health status display implementation**

```python
# Read the existing health status display in ChannelsPage.tsx
# Focus on getHealthBadgeProps usage and health indicator rendering
```

- [ ] **Step 2: Write test to verify health status colors correspond to metric values**

```typescript
// Test for getHealthBadgeProps utility function
import { getHealthBadgeProps } from '@/utils/healthUtils';

describe('getHealthBadgeProps', () => {
  it('returns correct props for healthy status', () => {
    const props = getHealthBadgeProps({
      successRate: 95,
      failureCount: 2,
      circuitState: 'CLOSED'
    });
    expect(props.color).toBe('green');
    expect(props.label).toBe('healthy');
  });

  it('returns correct props for warning status', () => {
    const props = getHealthBadgeProps({
      successRate: 70,
      failureCount: 10,
      circuitState: 'CLOSED'
    });
    expect(props.color).toBe('yellow');
    expect(props.label).toBe('warning');
  });

  it('returns correct props for critical status', () => {
    const props = getHealthBadgeProps({
      successRate: 40,
      failureCount: 25,
      circuitState: 'OPEN'
    });
    expect(props.color).toBe('red');
    expect(props.label).toBe('critical');
  });
});
```

- [ ] **Step 3: Run test to verify it passes**

Run: `npm test -- tests/frontend/testChannelsPageHealth.test.tsx::getHealthBadgeProps -t`
Expected: PASS

- [ ] **Step 4: Enhance health utility to include trend indicators**

```typescript
// Modify frontend/src/utils/healthUtils.ts
export function getHealthBadgeProps(metrics: ChannelMetrics) {
  // Existing logic...
  
  // Add trend calculation if we have historical data
  const trend = calculateHealthTrend(metrics.channelId, metrics.timestamp);
  
  return {
    // ...existing props
    trend, // 'improving', 'degrading', or 'stable'
    tooltip: generateHealthTooltip(metrics)
  };
}

function calculateHealthTrend(channelId: string, currentTimestamp: number): 'improving' | 'degrading' | 'stable' {
  // Fetch historical metrics and compare
  // Simplified implementation
  return 'stable'; // Placeholder
}

function generateHealthTooltip(metrics: ChannelMetrics): string {
  return `
    Success Rate: ${metrics.successRate}%
    Failure Count: ${metrics.failureCount}
    Circuit State: ${metrics.circuitState}
    Rate Limit Hits: ${metrics.rateLimitHits}
    Consecutive Failures: ${metrics.consecutiveFailures}
  `;
}
```

- [ ] **Step 5: Write test to verify enhanced health utility functions**

```typescript
describe('getHealthBadgeProps with enhancements', () => {
  it('includes trend indicator', () => {
    const props = getHealthBadgeProps({
      successRate: 85,
      failureCount: 5,
      circuitState: 'CLOSED',
      channelId: 'test_123',
      timestamp: Date.now()
    });
    expect(props.trend).toBeDefined();
    expect(['improving', 'degrading', 'stable']).toContain(props.trend);
  });

  it('includes tooltip with metric details', () => {
    const props = getHealthBadgeProps({
      successRate: 80,
      failureCount: 10,
      circuitState: 'CLOSED',
      channelId: 'test_123',
      timestamp: Date.now()
    });
    expect(props.tooltip).toContain('Success Rate: 80%');
    expect(props.tooltip).toContain('Failure Count: 10');
  });
});
```

- [ ] **Step 6: Run test to verify it passes**

Run: `npm test -- tests/frontend/testChannelsPageHealth.test.tsx::getHealthBadgeProps -t`
Expected: PASS

- [ ] **Step 7: Modify ChannelsPage to display enhanced health indicators**

```typescript
// Modify frontend/src/pages/ChannelsPage.tsx
import { getHealthBadgeProps } from '@/utils/healthUtils';

// In the channel card rendering:
{channel.metrics && (
  <div className="space-y-2">
    <div className="flex items-center space-x-3">
      <div
        className={`w-3 h-3 rounded-full ${getHealthBadgeProps(channel.metrics).color}`}
        title={getHealthBadgeProps(channel.metrics).tooltip}
      />
      <span className="text-sm font-medium">
        {getHealthBadgeProps(channel.metrics).label.toUpperCase()}
        {getHealthBadgeProps(channel.metrics).trend && (
          <span className="ml-1 text-xs">
            {getHealthBadgeProps(channel.metrics).trend === 'improving' ? '↑' : 
             getHealthBadgeProps(channel.metrics).trend === 'degrading' ? '↓' : '→'}
          </span>
        )}
      </span>
    </div>
    
    {/* Enhanced metrics display with tooltips */}
    <div className="text-xs text-muted-foreground">
      <div className="flex space-x-4">
        <span title="Success rate of message deliveries">
          ✓ {channel.metrics.successRate}%
        </span>
        <span title="Total failed requests">
          ✗ {channel.metrics.failureCount}
        </span>
        <span title="Rate limit hits">
          ⚠ {channel.metrics.rateLimitHits}
        </span>
        <span title="Consecutive failures">
          ↻ {channel.metrics.consecutiveFailures}
        </span>
      </div>
    </div>
  )}
```

- [ ] **Step 8: Write test to verify ChannelsPage displays enhanced health indicators**

```typescript
describe('ChannelsPage health indicators', () => {
  it('displays health status with correct color and tooltip', () => {
    render(<ChannelsPage />);
    // Wait for data to load
    await waitForElementToBeRemoved(() => screen.getByText(/loading/i));
    
    const healthIndicator = screen.getByRole('status'); // Assuming the dot has role status
    expect(healthIndicator).toHaveClass('bg-green-500'); // For healthy channel
    expect(healthIndicator).toHaveAttribute('title', expect.stringContaining('Success Rate:'));
  });

  it('displays trend indicator when health is changing', () => {
    // Mock data with improving trend
    render(<ChannelsPage />);
    await waitForElementToBeRemoved(() => screen.getByText(/loading/i));
    
    const trendIndicator = screen.getByText(/↑|↓|→/); // One of the trend arrows
    expect(trendIndicator).toBeInTheDocument();
  });
});
```

- [ ] **Step 9: Run test to verify it passes**

Run: `npm test -- tests/frontend/testChannelsPageHealth.test.tsx::ChannelsPage -t`
Expected: PASS

- [ ] **Step 10: Enhance circuit breaker display with better visual feedback**

```typescript
// Modify frontend/src/pages/ChannelsPage.tsx - circuit breaker section
{channel.metrics && channel.metrics.circuitState === 'OPEN' && (
  <div className="bg-red-50 border border-red-200 rounded-md p-3 mb-4">
    <div className="flex items-start space-x-3">
      <div className="flex-shrink-0">
        <AlertTriangle className="h-5 w-5 text-red-400" />
      </div>
      <div className="space-y-1">
        <h3 className="text-sm font-medium text-red-800">
          Circuit Breaker Open
        </h3>
        <p className="text-sm text-red-600">
          Message delivery is temporarily paused due to repeated failures.
          The circuit breaker will automatically attempt to recover after 
          the cooldown period.
        </p>
        <button
          onClick={() => resetCircuitBreaker(channel.id)}
          className="btn btn-sm btn-outline btn-primary"
        >
          Reset Circuit Breaker
        </button>
      </div>
    </div>
  </div>
)}
```

- [ ] **Step 11: Write test to verify circuit breaker display and reset functionality**

```typescript
describe('ChannelsPage circuit breaker handling', () => {
  it('displays circuit breaker open warning with reset button', () => {
    render(<ChannelsPage />);
    await waitForElementToBeRemoved(() => screen.getByText(/loading/i));
    
    const circuitWarning = screen.getByText(/circuit breaker open/i);
    expect(circuitWarning).toBeInTheDocument();
    
    const resetButton = screen.getByRole('button', { name: /reset circuit breaker/i });
    expect(resetButton).toBeInTheDocument();
  });

  it('resets circuit breaker when button is clicked', async () => {
    render(<ChannelsPage />);
    await waitForElementToBeRemoved(() => screen.getByText(/loading/i));
    
    const resetButton = screen.getByRole('button', { name: /reset circuit breaker/i });
    await userEvent.click(resetButton);
    
    // Verify reset function was called (would need mocking)
    expect(resetCircuitBreaker).toHaveBeenCalledWith(testChannelId);
  });
});
```

- [ ] **Step 12: Run test to verify it passes**

Run: `npm test -- tests/frontend/testChannelsPageHealth.test.tsx::circuit breaker -t`
Expected: PASS

- [ ] **Step 13: Commit**

```bash
git add frontend/src/pages/ChannelsPage.tsx frontend/src/utils/healthUtils.ts tests/frontend/testChannelsPageHealth.test.tsx
git commit -m "feat: enhance ChannelsPage health indicators display with tooltips and trend indicators"
```

### Task 5: Implement End-to-End Verification Flow

**Files:**
- Create: `tests/e2e/testChannelManagementFlow.cy.js` (if using Cypress) or similar

**Interfaces:**
- Consumes: Full channel management workflow
- Produces: Verified end-to-end functionality

- [ ] **Step 1: Create end-to-end test for complete channel lifecycle**

```javascript
describe('Channel Management End-to-End Flow', () => {
  it('creates channel, verifies health status, and displays correctly in UI', () => {
    // Login
    cy.login();
    
    // Navigate to channels page
    cy.visit('/channels');
    
    // Click add channel button
    cy.contains('Add Channel').click();
    
    // Fill out form for Slack channel
    cy.get('#name').type('E2E Test Slack');
    cy.get('#type').select('slack');
    cy.get('#configuration\\.bot_token').type('xoxb-test-token');
    cy.get('#configuration\\.signing_secret').type('test-secret');
    cy.get('#configuration\\.webhook_url').type('https://example.com/webhook');
    
    // Submit form
    cy.contains('Create Channel').click();
    
    // Verify channel was created successfully
    cy.contains('E2E Test Slack').should('be.visible');
    
    // Verify channel appears in list
    cy.get('[data-testid="channel-list-item"]').should('have.length.greater.than', 0);
    
    // Simulate some message activity to affect health
    cy.intercept('POST', '/api/v1/channels/*/messages', {
      statusCode: 200
    }).as('sendMessage');
    
    // Send a few successful messages
    for (let i = 0; i < 5; i++) {
      cy.sendMessageToChannel('E2E Test Slack', `Test message ${i}`);
      cy.wait('@sendMessage');
    }
    
    // Send a few failed messages to affect health
    cy.intercept('POST', '/api/v1/channels/*/messages', {
      statusCode: 500
    }).as('failedMessage');
    
    for (let i = 0; i < 2; i++) {
      cy.sendMessageToChannel('E2E Test Slack', `Failed message ${i}`);
      cy.wait('@failedMessage');
    }
    
    // Wait for health metrics to update
    cy.wait(3000); // Wait for batched query refresh
    
    // Verify health status reflects the activity
    cy.get('[data-testid="channel-health-status"]').should('contain', 'healthy');
    // Or warning depending on threshold
    
    // Verify metrics are displayed
    cy.get('[data-testid="success-rate"]').should('contain', '71'); // 5/7 ≈ 71%
    cy.get('[data-testid="failure-count"]').should('contain', '2');
    
    // Test channel deletion
    cy.get('[data-testid="channel-actions-menu"]').click();
    cy.get('[data-testid="delete-channel"]').click();
    cy.get('[data-testid="confirm-delete"]').click();
    
    // Verify channel is removed from list
    cy.contains('E2E Test Slack').should('not.exist');
  });
});
```

- [ ] **Step 2: Run end-to-end test to verify it passes**

Run: `npx cypress run --spec tests/e2e/testChannelManagementFlow.cy.js`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/testChannelManagementFlow.cy.js
git commit -m "feat: add end-to-end test for channel management verification flow"
```

### Task 6: Review and Finalize Implementation

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
1. ✅ **11.1.1**: GET /api/v1/channels returns all configured channels with correct data structure
2. ✅ **11.1.2**: Channel creation works for all supported types with proper configuration
3. ✅ **11.1.3**: Channel health status metrics accurately reflect actual connectivity
4. ✅ **11.1.4**: ChannelsPage displays comprehensive health indicators that update correctly

- [ ] **Step 3: Commit final changes**

```bash
git add .
git commit -m "feat: complete channel management verification and improvement implementation"
```

</system-reminder>