---
name: code_execution
description: >-
  Run code in an isolated Docker sandbox via the code_execution tool. Raw data
  never leaves the sandbox; you receive only a structured summary. Use for safe
  computation, data transforms, or running untrusted snippets. Restricted to
  0xxxx/1xxxx/2xxxx tiers. Skill file at
  backend/.agentium/skills/code_execution/SKILL.md.
skill_type: automation
domain: backend
complexity: intermediate
tags: [code, sandbox, execution, docker, computation]
creator_tier: head
---

# Code Execution

Execute code safely inside the existing Docker sandbox.

## Steps
1. Call the `code_execution` tool with `action="execute"` and your `code`.
2. Set `language` (default python) and `dependencies` for pip packages.
3. Pass `input_data` to make data available to the code as `input_data`.
4. Enable `network_access` only when the snippet must reach the network.

## Validation
- The tool returns the sandbox summary (`status`, `summary`, `execution_time_ms`).
- Disallowed or insecure code is blocked by the execution guard (`status: blocked`).
- Raw output never enters agent context.
