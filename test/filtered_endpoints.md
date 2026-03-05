# Endpoint Analysis

Total disconnected endpoints: 203
Backend-only/System endpoints: 38
Truly missing frontend endpoints: 29

## Truly Missing User-Facing Endpoints

These endpoints exist in the backend and represent user-facing functionality that appears to be missing from the React frontend.

### `api\routes\api_keys.py`

- `DELETE /{key_id}`
- `GET /{key_id}/spend-history`
- `POST /test-failover`

### `api\routes\auth.py`

- `GET /verify-session`

### `api\routes\browser.py`

- `POST /check-url`
- `POST /scrape`
- `POST /screenshot`

### `api\routes\checkpoints.py`

- `GET /{checkpoint_id}`

### `api\routes\files.py`

- `DELETE /{filename}`

### `api\routes\mcp_tools.py`

- `GET /{tool_id}`

### `api\routes\monitoring_routes.py`

- `GET /agents/{agent_id}/reasoning-traces`
- `GET /reasoning-traces/validation-failures`
- `GET /tasks/{task_id}/reasoning-trace`
- `GET /tasks/{task_id}/reasoning-trace/summary`

### `api\routes\provider_analytics.py`

- `GET /latency-percentiles`

### `api\routes\remote_executor.py`

- `DELETE /sandboxes/{sandbox_id}`
- `GET /executions/{execution_id}`
- `GET /sandboxes`
- `POST /sandboxes`

### `api\routes\skills.py`

- `GET /{skill_id}`

### `api\routes\tasks.py`

- `GET /{task_id}`
- `PATCH /{task_id}`

### `api\routes\tool_creation.py`

- `POST /marketplace/{tool_name}/update-listing`

### `api\routes\user_preferences.py`

- `DELETE /{key}`
- `GET /{key}`
- `PUT /{key}`

### `api\routes\voice.py`

- `GET /enhanced-status`

### `main.py`

- `POST /api/v1/genesis/country-name`
