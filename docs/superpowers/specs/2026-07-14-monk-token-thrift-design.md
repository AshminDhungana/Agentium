# Spec: `monk` — Token-Thrift Skill for Claude Code

**Date:** 2026-07-14
**Status:** Approved design, pending implementation plan
**Author:** Ashmin (brainstorming session) + Claude

## 1. Purpose

Create a Claude Code **skill** named `monk` that, when invoked with `/monk`, makes
Claude work more token-efficiently for the **rest of the session** — reducing both
input (context) and output tokens **without harming the quality or correctness of the
work**.

The skill is purely **behavioral**: it loads a set of zero-risk operating disciplines
that Claude self-applies each turn. It changes no files, no config, and no repository
state.

### Why "monk"

Disciplined, spare, no waste. The name signals the ethos: do only what serves the work,
carry nothing superfluous.

## 2. Core Principle

> Every token in the context window is paid on **every** turn. Context is the
> fundamental constraint, and model performance degrades as it fills.

Two layers of token cost are handled by **different owners**:

- **Harness layer (NOT the skill's job):** Claude Code automatically caches the system
  prompt and stable prefixes (cache *reads* cost **0.1×** base input price) and
  auto-compacts the conversation near the context limit. `monk` does not attempt to
  manipulate caching or the harness.
- **Application layer (the skill's job):** Claude's own behavior — what it reads, how
  much it writes, which tools it calls, and whether it reuses prior work. This is where
  `monk` operates.

This division is deliberate: the skill owns only what Claude controls per-turn, keeping
it zero-risk and free of its own token overhead.

## 3. Activation & Scope

- **Trigger:** user types `/monk`. From that moment the rules apply for the remainder of
  the session (no re-invocation needed).
- **Scope:** the current Claude Code session only.
- **Auto-trigger description** (for the skill frontmatter `description`): used when the
  user wants to reduce the token cost of the current session without harming
  correctness — read ranges, batch tools, delegate verbose reads to subagents, trim
  prose, reuse context, right-size the model.
- **Out of scope:** Agentium's own agents' token usage (this is a Claude Code skill for
  the user's sessions, not a change to the Agentium system). Hard token metrics
  (transcript tokenizers) are a future optional add-on, not v1.

## 4. Operating Rules

### 4.1 Input / context rules (the biggest lever)

- **Read ranges, not whole files.** Use `offset`/`limit` when the target location is
  approximately known. Never `Read` a 2000-line file to change one function.
- **Find with `Grep`/`Glob`, never `Read`-to-find.** `Grep` returns matches with line
  numbers; dumping a file just to locate text is the #1 input waste.
- **Do not re-read.** If a file's content is already in this session's context, reference
  it. Re-reading is pure waste.
- **Cap tool output.** Use `head_limit`, glob filters, and targeted queries rather than
  dumping full logs, directory listings, or command output.
- **Delegate verbose work to subagents.** Exploration and large log/file reads run in a
  *separate* context window; only a summary returns to the main thread. This is the
  single most powerful context lever. For scans that don't need Opus, prefer a cheap
  subagent model (`CLAUDE_CODE_SUBAGENT_MODEL=haiku`) so the main context and the bill
  both stay light.
- **Right-size the model.** If currently on Opus for routine work, recommend
  `/model sonnet` (Opus output is far more expensive and unnecessary for most coding
  tasks). This is a *recommendation* the user accepts or declines — `monk` never silently
  switches the model.
- **Use built-in context controls:**
  - `/compact <instructions>` — preserve essentials during summarization.
  - `/clear` — reset between unrelated tasks so stale context stops costing tokens.
  - `/btw` — ask throwaway side-questions that should not enter conversation history.
  - `/context` — audit what is bloating turns; act on offenders.
- **Setup-once, documented (not enforced by v1):** keep `CLAUDE.md` under ~200 lines; use
  `.claudeignore`; disable unused MCP servers (CLI tools are more context-efficient than
  MCP listings). These are mentioned in the skill as durable habits, not applied per
  session.

### 4.2 Output rules (trim waste, keep insight)

- **Lead with the answer / code**; explanations follow.
- **Never restate code** just written in prose ("here is the function that…") — the block
  is self-explanatory.
- **Cut filler** ("Sure!", "Let me…", excessive qualifiers).
- **Keep the explanatory `★ Insight` blocks and the non-obvious *why*** — that is learning
  value, not waste. This is the line that respects the user's active Explanatory output
  style.
- **Prefer tables/lists over paragraphs** when denser conveys the same meaning.
- **Optionally lower `/effort` on genuinely simple tasks** — extended-thinking tokens are
  billed as output; reducing effort on trivial work cuts output cost with no quality loss.
- **Explicitly rejected as too aggressive:** "Caveman"-style silence (~65% output
  reduction) sacrifices the explanatory learning the Explanatory style exists to deliver.
  Out of scope, consistent with the conservative/zero-risk bar.

### 4.3 Tool-use & reuse rules

- **Batch** independent tool calls into one message (multiple tool-use blocks).
- **Parallelize** fan-out via subagents when it fits.
- **Do not re-derive** — reuse what was computed or discovered earlier this session.
- **Ask for a verification target up front** (test, build, screenshot). Self-verification
  prevents rework, and rework is the most expensive token waste of all. This sits *inside*
  the guardrail (§5), not against it.
- **Pick the precise tool** for the job (e.g., `vault_get_document_map` before reading a
  whole vault file; structured sources like `21st` search before web-scrape).

## 5. Zero-Risk Guardrail ("never cut")

`monk` is **forbidden** from saving tokens by:

- Skipping verification (`verification-before-completion`, running tests).
- Omitting error messages / stack traces needed to debug.
- Dropping security-relevant or audit output.
- Summarizing away content a *correct decision* depends on.
- Guessing instead of a lookup when correctness depends on that lookup.
- Removing content the user explicitly asked to keep (including Explanatory insights).
- Disabling extended thinking on *complex* tasks.
- Downgrading the model on tasks that actually need Opus.

## 6. Explanatory-Style Reconciliation

`monk` does **not** disable the user's active Explanatory output style. It trims
*redundancy* (restating code, filler, over-long prose), not *insight* (the `★ Insight`
blocks and the reasoning behind choices). If the user wants even terser output, they
switch off Explanatory separately — `monk` will not override the style setting.

## 7. Optional Power-User Hook (out of v1 core)

A ready-made `PostToolUse` hook script that filters verbose test/log output (research
shows **80–99% reduction**) before it reaches context. Shipped as an *optional reference
file*, **not enabled by default** (requires `settings.json` config). This lets the user
graduate from behavioral discipline to automatic enforcement later, without bloating v1.

The hook is a `PreToolUse`/`PostToolUse` command (e.g., grep test/log output for
`FAIL|ERROR` and return only matching lines) — analogous to the Claude Code docs example
that reduces a 10,000-line log to hundreds of tokens.

## 8. Self-Check Habit (before each response while active)

1. Did I read only what's needed (ranges, not whole files)?
2. Did I reuse prior context instead of re-fetching?
3. Did I delegate verbose reads/exploration to a subagent?
4. Is context still lean (`/context`) — any offender to trim?
5. Is the model right-sized for this task?
6. Is my output free of restatement/filler but still insightful?
7. Did I avoid every item in the "never cut" list (§5)?

## 9. SKILL.md Structure

```markdown
---
name: monk
description: On-demand discipline to cut input/output tokens in a Claude Code
  session without harming correctness — read ranges, batch tools, delegate verbose
  reads to subagents, trim prose, reuse context, right-size the model. Use when the
  user wants to reduce the token cost of the current session.
---

# monk — Token Thrift

## When to use
## Core principle (context is the constraint; harness caches, you discipline behavior)
## Operating rules
### Input / context
### Output
### Tool use & reuse
## Never cut (zero-risk guardrail)
## Explanatory-style note
## Optional hook (reference, not enabled)
## Self-check before each response
```

The file lives at `E:\Ongoing Projects\Agentium\.claude\skills\monk\SKILL.md`
(repo-local skill, available to this project).

## 10. Validation (behavioral, no metrics needed for v1)

A **behavioral acceptance checklist** rather than token counts:

- After invoking `/monk` on a sample task, confirm:
  - (a) no whole-file `Read` where a range or `Grep` sufficed;
  - (b) independent tool calls were batched;
  - (c) verbose exploration was delegated to a subagent;
  - (d) no verification step was skipped;
  - (e) no explanatory insight was dropped;
  - (f) model was right-sized or the user was offered the option.
- Hard numbers (transcript tokenizer / `/usage` delta) are the optional Approach-C
  add-on, explicitly **out of scope for v1**.

## 11. Sources (research that informed this spec)

- [Best practices for Claude Code](https://code.claude.com/docs/en/best-practices) — context is the core constraint; subagents; hooks; `/compact`, `/clear`, `/btw`; CLAUDE.md discipline.
- [Manage costs effectively (Claude Code)](https://code.claude.com/docs/en/costs) — model selection, effort/thinking tokens, MCP overhead, hook-based log filtering, subagent delegation, `/context`.
- [Prompt caching (Claude Platform)](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — cache reads at 0.1×; stable prefixes cached automatically.
- [7 practical ways to reduce Claude Code token usage (KDNuggets)](https://www.kdnuggets.com/7-practical-ways-to-reduce-claude-code-token-usage) — model-by-need, `/compact` early, specific prompts, subagents.
- [12 ways to cut token consumption in Claude Code (Firecrawl)](https://www.firecrawl.dev/blog/claude-code-token-efficiency) — subagent Haiku, PostToolUse log filters, `.claudeignore`, concise-output budgets.

## 12. Out of Scope (explicit YAGNI)

- Modifying the Agentium system or its agents.
- Hook installation/config in v1 (provided as optional reference only).
- Token-counting/measurement tooling (future add-on).
- Auto-switching the model (recommendation only).
- Any technique that risks correctness (per the conservative/zero-risk bar).
