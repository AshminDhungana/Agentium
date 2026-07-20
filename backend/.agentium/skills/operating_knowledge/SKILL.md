---
name: operating_knowledge
description: >-
  Core operating knowledge every Agentium agent should consult before acting: which
  tool or skill to use for a given intent (fetch a URL, search the web, run a
  shell command, read/write collective memory, access host files), host-system
  access patterns, and general best practices. Use it when you are unsure which
  capability applies, or before touching the host filesystem or running commands.
  Skill file at backend/.agentium/skills/operating_knowledge/SKILL.md.
skill_type: documentation
domain: general
complexity: beginner
tags: [operating-knowledge, tool-selection, best-practices, host-access, cli, rag]
creator_tier: head
chroma_collection: best_practices
---

# Agent Operating Knowledge

A quick-reference map of *what to use, when*. For step-by-step detail, follow
the linked skill — this file tells you which one. It is seeded into the
`best_practices` ChromaDB collection so any agent can retrieve it via
`search_skills` or a RAG query.

## Intent → tool/skill map
- **"How do I fetch a URL / read a specific web page?"** → use the `web_fetch`
  tool (skill: `web_fetch`). Returns the page as clean Markdown with a token
  budget.
- **"Where do I find / discover URLs on a topic?"** → use the `web_search`
  tool first, then `web_fetch` the result.
- **"I need multi-page site content / sitelinks?"** → use the `web_crawler`
  tool (skill: `web_crawling`), depth- and page-limited, robots.txt-respecting.
- **"Where should I look up X on the web?"** → consult the `web_crawling`
  skill's Major Sites Index (dataset `major_sites.md`) for category → source
  guidance before searching.
- **"What's my working directory / where do I write files?"** → you run inside a
  sandboxed Docker container. The host machine is reachable via the
  read-write bind mounts `/host_home` (the Sovereign's home: Desktop,
  Documents, Downloads) and `/host` (entire host root). Prefer writing
  generated artifacts to `/host_home/agentium-workspace/<your_agent_id>/` (use
  the `get_workspace` tool to discover your exact path) rather than the
  container filesystem. See the `agent_environment` context for the full
  grounding.
- **"Run a shell command / use grep, curl, ls, cat, etc.?"** → use the
  `ShellTool` (skill: `bash`). IMPORTANT: `ShellTool.execute(command: List[str])`
  runs **without a shell**, so pipes, redirects, `&&`, `||`, `$()`, and globs
  only work if you wrap the whole expression in `["sh", "-c", "..."]`. Common
  utilities available: `grep`/`rg`, `curl`, `wget`, `jq`, `awk`, `sed`,
  `find`, `ls`, `cat`, `git`, `pytest`, `docker`, `alembic`, `ruff`,
  `black`, `mypy`, `make`. Prefer the dedicated agent tools over raw shell
  when one exists (e.g. `vector_db` for memory, `web_fetch` for URLs).
- **"Read or write collective memory / RAG knowledge?"** → use the `vector_db`
  tool (skill: `vector_db`). Writes are restricted to a writable-collection
  allow-list.
- **"Execute arbitrary code safely?"** → use the sandboxed code-execution tool
  (not the host shell) so raw data/PII never enters agent context.

## Best practices
- **Search before acting:** before acting on unfamiliar information, query the
  knowledge base (`vector_db` / `search_skills`) first; if the knowledge isn't
  there, perform a web search and write the result back to ChromaDB before
  proceeding. If web search is unavailable, fall back to what's already in
  Chroma rather than blocking.
- **Prefer host mounts** for any artifact the Sovereign should be able to open
  on their machine (`/host_home/...`), not the container filesystem.
- **Re-read the Constitution** and your own Ethos after every task; every agent
  checks constitutionality before acting.
- **Store learnings** back into ChromaDB so institutional memory compounds.
- **Safe-bash discipline:** always wrap shell meta-characters in `sh -c`; never
  hardcode secrets; prefer the smallest-scope tool for the job.

## Validation
- A query like "how do I fetch a URL" or "what's my working directory"
  retrieves this skill via `search_skills` / RAG.
- Following the intent map leads to the correct, pre-existing tool/skill rather
  than a raw, error-prone command.
