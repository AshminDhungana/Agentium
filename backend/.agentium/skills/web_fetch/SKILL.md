---
name: web_fetch
description: >-
  Fetch a URL and return its page content as clean Markdown with a token budget,
  so an agent can read a web page without burning context. Use the web_fetch tool
  when you have a specific URL and need its content (not search results). Skill
  file at backend/.agentium/skills/web_fetch/SKILL.md.
skill_type: research
domain: general
complexity: beginner
tags: [web, fetch, scraping, markdown, retrieval]
creator_tier: head
---

# Web Fetch

Retrieve the contents of a specific URL as Markdown.

## Steps
1. Call the `web_fetch` tool with `action="fetch"` and the target `url`.
2. Set `max_tokens` to keep the returned Markdown within your context budget.
3. Enable `use_cache` (default) to avoid re-fetching within 5 minutes.
4. Pass `allowed_domains` to restrict fetches to trusted hosts.

## Validation
- The tool returns `status: success` with `markdown`, `title`, and `token_count`.
- Oversized pages are truncated and flagged with `truncated: true`.
- Failures return `status: error` without raising into the agent context.
