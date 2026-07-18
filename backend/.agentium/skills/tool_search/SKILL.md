---
name: tool_search
description: >-
  Discover registered Agentium tools by describing what you need, using the
  tool_search tool. Returns ranked tool names and descriptions scoped to your
  tier, so you can find the right tool without seeing the entire tool list. Use
  the get action to fetch one tool's full descriptor. Skill file at
  backend/.agentium/skills/tool_search/SKILL.md.
skill_type: integration
domain: ai
complexity: beginner
tags: [discovery, tools, registry, search]
creator_tier: head
---

# Tool Search

Find the right tool at runtime by capability.

## Steps
1. Call `tool_search` with `action="search"` and a `query` describing the need.
2. Read the ranked `results` to pick a tool.
3. Call `action="get"` with the chosen `name` to retrieve its full descriptor.

## Validation
- `search` returns `status: success` with ranked `results` (name, description, score).
- `get` returns the tool's `description` and `parameters`, or an error if not authorized.
- Results are always scoped to tools your tier may use.
