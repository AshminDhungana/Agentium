# Agentium Python SDK

Async-first Python client for the [Agentium](https://github.com/AshminDhungana/Agentium) AI Agent Governance platform.

## Installation

```bash
pip install agentium-sdk
```

## Quick Start

```python
import asyncio
from agentium_sdk import AgentiumClient

async def main():
    async with AgentiumClient("http://localhost:8000", api_key="your-key") as client:
        # Check health
        health = await client.health()
        print(f"Status: {health.status}")

        # List agents
        agents = await client.list_agents()
        for agent in agents:
            print(f"  {agent.agentium_id} — {agent.role} ({agent.status})")

        # Create a task
        task = await client.create_task(
            title="Summarize report",
            description="Summarize Q4 financials",
        )
        print(f"Task created: {task.id}")

asyncio.run(main())
```

## Authentication

### API Key
```python
client = AgentiumClient("http://localhost:8000", api_key="sk-...")
```

### JWT (username/password)
```python
async with AgentiumClient("http://localhost:8000") as client:
    token = await client.login("admin", "password")
    agents = await client.list_agents()
```

## Error Handling

```python
from agentium_sdk import AgentiumClient, NotFoundError, RateLimitError

async with AgentiumClient("http://localhost:8000", api_key="sk-...") as client:
    try:
        agent = await client.get_agent("99999")
    except NotFoundError:
        print("Agent not found")
    except RateLimitError as e:
        print(f"Rate limited, retry after {e.retry_after}s")
```

## Available Methods

| Method | Description |
|--------|-------------|
| `health()` | System health check |
| `login(user, pass)` | JWT authentication |
| `list_agents()` | List all agents |
| `get_agent(id)` | Get agent by ID |
| `create_agent(...)` | Create new agent |
| `list_tasks()` | List tasks |
| `get_task(id)` | Get task by ID |
| `create_task(...)` | Create new task |
| `get_constitution()` | Get active constitution |
| `update_constitution(...)` | Update constitution |
| `list_votes()` | List voting proposals |
| `cast_vote(...)` | Cast a vote |
| `send_message(...)` | Send chat message |
| `list_webhook_subscriptions()` | List webhooks |
| `create_webhook_subscription(...)` | Create webhook |
| `delete_webhook_subscription(id)` | Delete webhook |
| `test_webhook(id)` | Test webhook |

## License

AGPL-3.0 — same as the Agentium project.
