# `monk` Token-Thrift Skill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repo-local Claude Code skill named `monk` that, when invoked with `/monk`, makes Claude apply zero-risk token-efficiency disciplines for the rest of the session.

**Architecture:** A single `SKILL.md` (Markdown + YAML frontmatter) that loads operating rules into context on invocation — pure instruction, no runtime code. Plus one optional, *not-enabled-by-default* Bash hook reference script for verbose-log filtering, shipped with a runnable test. The harness owns prompt caching/auto-compaction; `monk` owns only Claude's per-turn application-layer behavior.

**Tech Stack:** Claude Code skill format (`.claude/skills/<name>/SKILL.md` with `name` + `description` frontmatter). Optional hook is POSIX `bash`. Dev-time validation uses Python's `yaml` (already available in the project's Python env) and `grep`.

## Global Constraints

- Skill name `monk`; its `SKILL.md` lives at `E:\Ongoing Projects\Agentium\.claude\skills\monk\SKILL.md`.
- Activation: user types `/monk`; rules apply for the **rest of the session**. Behavioral only — no repo/config changes in v1.
- **Zero-risk guardrail (never cut):** no skipping verification; no omitting errors/stack traces; no dropping security/audit output; no summarizing away decision-critical content; no guessing instead of a needed lookup; no removing explicitly-requested content (incl. Explanatory insights); no disabling thinking on complex tasks; no downgrading the model on tasks that need Opus.
- Harness owns caching and auto-compaction; the skill must not attempt to manipulate them.
- Explanatory output style is respected — trim redundancy, never insight.
- Optional hook is shipped as a **reference file only**; it is **not** wired into `settings.json` in v1.
- YAGNI / out of scope: modifying Agentium's agents; hook installation; token-counting metrics; auto-switching the model (recommendation only); any correctness-risking technique.

---

### Task 1: Scaffold skill directory and frontmatter

**Files:**
- Create: `.claude/skills/monk/SKILL.md`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: a valid, discoverable `SKILL.md` with correct frontmatter and an append marker that later tasks replace

- [ ] **Step 1: Create the skill directory and frontmatter file**

Write `.claude/skills/monk/SKILL.md` with this exact content (note the `<!-- APPEND -->` marker — later tasks replace it):

```markdown
---
name: monk
description: On-demand discipline to cut input/output tokens in a Claude Code
  session without harming correctness — read ranges, batch tools, delegate verbose
  reads to subagents, trim prose, reuse context, right-size the model. Use when the
  user wants to reduce the token cost of the current session.
---

# monk — Token Thrift

<!-- APPEND -->
```

- [ ] **Step 2: Validate frontmatter (parses, name matches directory, description present)**

Run (from repo root):

```bash
python - <<'PY'
import yaml, sys
p = ".claude/skills/monk/SKILL.md"
text = open(p, encoding="utf-8").read()
assert text.startswith("---"), "missing frontmatter delimiters"
fm = yaml.safe_load(text.split("---", 2)[1])
assert fm.get("name") == "monk", f"name must be 'monk', got {fm.get('name')!r}"
assert fm.get("description") and len(fm["description"]) > 20, "description missing/too short"
print("frontmatter OK:", fm["name"])
PY
```

Expected: `frontmatter OK: monk`

- [ ] **Step 3: Commit**

```bash
git add -f .claude/skills/monk/SKILL.md
git commit -m "feat(monk): scaffold skill with valid frontmatter"
```

---

### Task 2: Write "When to use" and "Core principle" sections

**Files:**
- Modify: `.claude/skills/monk/SKILL.md` (replace the `<!-- APPEND -->` marker)

**Interfaces:**
- Consumes: the `<!-- APPEND -->` marker produced in Task 1
- Produces: the two opening sections; re-emits the `<!-- APPEND -->` marker for Task 3

- [ ] **Step 1: Insert the two sections before the marker**

Replace the line `<!-- APPEND -->` with:

```markdown
## When to use

Invoke `/monk` when you want the current session to cost fewer tokens without
sacrificing the quality or correctness of the work. Once invoked, these disciplines
apply to every turn for the rest of the session — no re-invocation needed. This is a
behavioral aid only: it changes no files, no configuration, and no repository state.

## Core principle

Every token in the context window is paid on **every** turn. Context is the fundamental
constraint, and model performance degrades as it fills.

Two layers of token cost have different owners:

- **Harness layer (not this skill's job):** Claude Code automatically caches the system
  prompt and stable prefixes — cache *reads* cost **0.1×** base input price — and
  auto-compacts the conversation near the context limit. `monk` does not touch caching
  or compaction.
- **Application layer (this skill's job):** Claude's own behavior — what it reads, how
  much it writes, which tools it calls, and whether it reuses prior work.

`monk` operates only on the application layer, which keeps it zero-risk and free of its
own token overhead.

<!-- APPEND -->
```

- [ ] **Step 2: Validate both headings exist**

```bash
grep -q '^## When to use$' .claude/skills/monk/SKILL.md && grep -q '^## Core principle$' .claude/skills/monk/SKILL.md && echo "sections OK"
```

Expected: `sections OK`

- [ ] **Step 3: Commit**

```bash
git add -f .claude/skills/monk/SKILL.md
git commit -m "feat(monk): add when-to-use and core-principle sections"
```

---

### Task 3: Write "Operating rules — Input / context"

**Files:**
- Modify: `.claude/skills/monk/SKILL.md` (replace the `<!-- APPEND -->` marker)

**Interfaces:**
- Consumes: the `<!-- APPEND -->` marker
- Produces: the `## Operating rules` header + `### Input / context` subsection; re-emits marker

- [ ] **Step 1: Insert the Operating rules header and Input/context subsection**

Replace `<!-- APPEND -->` with:

```markdown
## Operating rules

### Input / context (the biggest lever)

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
  subagent model (`CLAUDE_CODE_SUBAGENT_MODEL=haiku`) so both the main context and the
  bill stay light.
- **Right-size the model.** If currently on Opus for routine work, recommend `/model
  sonnet` (Opus output is far more expensive and unnecessary for most coding tasks). This
  is a *recommendation* the user accepts or declines — never switch the model silently.
- **Use built-in context controls:**
  - `/compact <instructions>` — preserve essentials during summarization.
  - `/clear` — reset between unrelated tasks so stale context stops costing tokens.
  - `/btw` — ask throwaway side-questions that should not enter conversation history.
  - `/context` — audit what is bloating turns; act on offenders.
- **Setup-once habits (documented, not enforced here):** keep `CLAUDE.md` under ~200
  lines; use `.claudeignore`; disable unused MCP servers (CLI tools are more
  context-efficient than MCP listings).

<!-- APPEND -->
```

- [ ] **Step 2: Validate the subsection heading exists**

```bash
grep -q '^### Input / context' .claude/skills/monk/SKILL.md && echo "input section OK"
```

Expected: `input section OK`

- [ ] **Step 3: Commit**

```bash
git add -f .claude/skills/monk/SKILL.md
git commit -m "feat(monk): add input/context operating rules"
```

---

### Task 4: Write "Operating rules — Output"

**Files:**
- Modify: `.claude/skills/monk/SKILL.md` (replace the `<!-- APPEND -->` marker)

**Interfaces:**
- Consumes: the `<!-- APPEND -->` marker
- Produces: the `### Output` subsection; re-emits marker

- [ ] **Step 1: Insert the Output subsection**

Replace `<!-- APPEND -->` with:

```markdown
### Output (trim waste, keep insight)

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

<!-- APPEND -->
```

- [ ] **Step 2: Validate the subsection heading exists**

```bash
grep -q '^### Output' .claude/skills/monk/SKILL.md && echo "output section OK"
```

Expected: `output section OK`

- [ ] **Step 3: Commit**

```bash
git add -f .claude/skills/monk/SKILL.md
git commit -m "feat(monk): add output operating rules"
```

---

### Task 5: Write "Operating rules — Tool use & reuse"

**Files:**
- Modify: `.claude/skills/monk/SKILL.md` (replace the `<!-- APPEND -->` marker)

**Interfaces:**
- Consumes: the `<!-- APPEND -->` marker
- Produces: the `### Tool use & reuse` subsection; re-emits marker

- [ ] **Step 1: Insert the Tool use & reuse subsection**

Replace `<!-- APPEND -->` with:

```markdown
### Tool use & reuse

- **Batch** independent tool calls into one message (multiple tool-use blocks).
- **Parallelize** fan-out via subagents when it fits.
- **Do not re-derive** — reuse what was computed or discovered earlier this session.
- **Ask for a verification target up front** (test, build, screenshot). Self-verification
  prevents rework, and rework is the most expensive token waste of all. This sits *inside*
  the guardrail, not against it.
- **Pick the precise tool** for the job (e.g., `vault_get_document_map` before reading a
  whole vault file; structured sources like `21st` search before web-scrape).

<!-- APPEND -->
```

- [ ] **Step 2: Validate the subsection heading exists**

```bash
grep -q '^### Tool use & reuse$' .claude/skills/monk/SKILL.md && echo "tooluse section OK"
```

Expected: `tooluse section OK`

- [ ] **Step 3: Commit**

```bash
git add -f .claude/skills/monk/SKILL.md
git commit -m "feat(monk): add tool-use and reuse operating rules"
```

---

### Task 6: Write the "Never cut" zero-risk guardrail

**Files:**
- Modify: `.claude/skills/monk/SKILL.md` (replace the `<!-- APPEND -->` marker)

**Interfaces:**
- Consumes: the `<!-- APPEND -->` marker
- Produces: the `## Never cut (zero-risk guardrail)` section; re-emits marker

- [ ] **Step 1: Insert the guardrail section**

Replace `<!-- APPEND -->` with:

```markdown
## Never cut (zero-risk guardrail)

`monk` is **forbidden** from saving tokens by:

- Skipping verification (`verification-before-completion`, running tests).
- Omitting error messages / stack traces needed to debug.
- Dropping security-relevant or audit output.
- Summarizing away content a *correct decision* depends on.
- Guessing instead of a lookup when correctness depends on that lookup.
- Removing content the user explicitly asked to keep (including Explanatory insights).
- Disabling extended thinking on *complex* tasks.
- Downgrading the model on tasks that actually need Opus.

<!-- APPEND -->
```

- [ ] **Step 2: Validate the guardrail heading exists**

```bash
grep -q '^## Never cut (zero-risk guardrail)$' .claude/skills/monk/SKILL.md && echo "guardrail OK"
```

Expected: `guardrail OK`

- [ ] **Step 3: Commit**

```bash
git add -f .claude/skills/monk/SKILL.md
git commit -m "feat(monk): add zero-risk guardrail section"
```

---

### Task 7: Write Explanatory note, Optional hook note, and Self-check

**Files:**
- Modify: `.claude/skills/monk/SKILL.md` (replace the final `<!-- APPEND -->` marker)

**Interfaces:**
- Consumes: the last `<!-- APPEND -->` marker
- Produces: the closing three sections; the marker is consumed (no re-emit — file complete)

- [ ] **Step 1: Insert the final three sections and consume the marker**

Replace `<!-- APPEND -->` with:

```markdown
## Explanatory-style note

`monk` does **not** disable the user's active Explanatory output style. It trims
*redundancy* (restating code, filler, over-long prose), not *insight* (the `★ Insight`
blocks and the reasoning behind choices). If the user wants even terser output, they
switch off Explanatory separately — `monk` will not override the style setting.

## Optional hook (reference, not enabled)

A ready-made `PostToolUse` hook script can filter verbose test/log output (research shows
**80–99% reduction**) before it reaches context. It ships at
`reference/filter-verbose-output.sh` as a *reference only* and is **not** wired into
`settings.json` in v1. To enable later, add a `PostToolUse` hook in
`.claude/settings.json` that pipes Bash tool output through that script.

## Self-check before each response (while active)

1. Did I read only what's needed (ranges, not whole files)?
2. Did I reuse prior context instead of re-fetching?
3. Did I delegate verbose reads/exploration to a subagent?
4. Is context still lean (`/context`) — any offender to trim?
5. Is the model right-sized for this task?
6. Is my output free of restatement/filler but still insightful?
7. Did I avoid every item in the "never cut" list?
```

- [ ] **Step 2: Validate the marker is gone and all three headings exist**

```bash
grep -q '<!-- APPEND -->' .claude/skills/monk/SKILL.md && { echo "ERROR: marker remains"; exit 1; }
grep -q '^## Explanatory-style note$' .claude/skills/monk/SKILL.md && grep -q '^## Optional hook (reference, not enabled)$' .claude/skills/monk/SKILL.md && grep -q '^## Self-check before each response' .claude/skills/monk/SKILL.md && echo "closing sections OK"
```

Expected: `closing sections OK`

- [ ] **Step 3: Full frontmatter + structure re-validation**

```bash
python - <<'PY'
import yaml
text = open(".claude/skills/monk/SKILL.md", encoding="utf-8").read()
fm = yaml.safe_load(text.split("---", 2)[1])
required = ["When to use","Core principle","Operating rules","Never cut (zero-risk guardrail)",
            "Explanatory-style note","Optional hook (reference, not enabled)","Self-check before each response"]
missing = [h for h in required if f"## {h}" not in text]
assert not missing, f"missing sections: {missing}"
assert fm["name"] == "monk"
print("SKILL.md complete:", len(text), "bytes,", len(required), "sections present")
PY
```

Expected: `SKILL.md complete: <n> bytes, 7 sections present`

- [ ] **Step 4: Commit**

```bash
git add -f .claude/skills/monk/SKILL.md
git commit -m "feat(monk): add explanatory note, hook reference, self-check"
```

---

### Task 8: Optional hook reference script + test (not enabled)

**Files:**
- Create: `.claude/skills/monk/reference/filter-verbose-output.sh`
- Create: `.claude/skills/monk/reference/test_filter.sh`

**Interfaces:**
- Consumes: nothing (standalone reference)
- Produces: a runnable, tested log-filtering helper referenced by the "Optional hook" section; intentionally **not** registered in `settings.json`

- [ ] **Step 1: Write the failing test first (TDD)**

Write `.claude/skills/monk/reference/test_filter.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
dir="$(cd "$(dirname "$0")" && pwd)"
script="$dir/filter-verbose-output.sh"

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; echo "got: [$2]"; exit 1; }

# Test 1: keeps only failure/error lines, drops PASS lines
out="$(printf 'PASS test_a\nFAIL test_b\nERROR: boom\nPASS test_c\n' | bash "$script")"
expected="$(printf 'FAIL test_b\nERROR: boom')"
[ "$out" = "$expected" ] || fail "drops PASS lines" "$out"
pass "drops PASS lines"

# Test 2: no matches -> single summary line
out="$(printf 'PASS test_a\nPASS test_b\n' | bash "$script")"
[ "$out" = "[no failures/errors detected in output]" ] || fail "no-match summary" "$out"
pass "no-match summary"

# Test 3: caps at max_lines
big="$(seq 1 50 | sed 's/^/ERROR line /')"
out="$(printf '%s\n' "$big" | bash "$script" 10 | wc -l)"
[ "$out" = "10" ] || fail "max_lines cap" "$out"
pass "max_lines cap"

echo "ALL HOOK TESTS PASSED"
```

- [ ] **Step 2: Run test to verify it fails (script not written yet)**

```bash
cd "E:/Ongoing Projects/Agentium" && bash .claude/skills/monk/reference/test_filter.sh
```

Expected: FAIL — `bash: .../filter-verbose-output.sh: No such file or directory`

- [ ] **Step 3: Write the minimal filter script**

Write `.claude/skills/monk/reference/filter-verbose-output.sh`:

```bash
#!/usr/bin/env bash
# Reference hook helper: shrink verbose command output to failure/error lines.
# Intended for a Claude Code PostToolUse hook that filters Bash tool output.
# Usage: <command-output> | ./filter-verbose-output.sh [max_lines]
# Prints lines matching failure/error patterns, capped at max_lines (default 100).
# If nothing matches, prints a single summary line so context still gets a signal.
set -euo pipefail
max_lines="${1:-100}"
matched="$(grep -E -i 'FAIL|ERROR|error:|Exception|Traceback|✗' || true)"
if [ -z "$matched" ]; then
  echo "[no failures/errors detected in output]"
else
  printf '%s\n' "$matched" | head -n "$max_lines"
fi
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd "E:/Ongoing Projects/Agentium" && bash .claude/skills/monk/reference/test_filter.sh
```

Expected: `PASS: ...` for all three, then `ALL HOOK TESTS PASSED`

- [ ] **Step 5: Confirm the hook is NOT wired into settings.json**

```bash
grep -rn "filter-verbose-output" ".claude/settings.json" ".claude/settings.local.json" 2>/dev/null && { echo "ERROR: hook must NOT be enabled in v1"; exit 1; } || echo "hook not enabled (correct)"
```

Expected: `hook not enabled (correct)`

- [ ] **Step 6: Commit (reference + test only, no settings change)**

```bash
git add -f .claude/skills/monk/reference/filter-verbose-output.sh .claude/skills/monk/reference/test_filter.sh
git commit -m "feat(monk): add optional, not-enabled verbose-output filter hook + test"
```

---

### Task 9: Behavioral validation in a real session + final commit

**Files:**
- No new files. Validates the assembled skill end-to-end.

**Interfaces:**
- Consumes: the complete `SKILL.md` (Tasks 1–7) and optional hook (Task 8)
- Produces: confirmation the skill loads and the acceptance checklist holds; a final review commit if any wording fix is needed

- [ ] **Step 1: Start a fresh session and confirm `/monk` is discoverable**

In a new Claude Code session at the repo root, run `/monk`. Expected: Claude acknowledges the token-thrift disciplines are now active for the session (the skill's frontmatter `description` should have matched and loaded it).

- [ ] **Step 2: Run a sample task while `/monk` is active**

Prompt, e.g.: *"Add input validation to the login function in `backend/api/routes/auth.py`. Show me the change."* Then observe Claude's behavior against the acceptance checklist:

  - [ ] (a) No whole-file `Read` where a range or `Grep` would have sufficed.
  - [ ] (b) Independent tool calls were batched into single messages.
  - [ ] (c) Any verbose exploration was delegated to a subagent.
  - [ ] (d) No verification step was skipped (tests/build still run or offered).
  - [ ] (e) No explanatory `★ Insight` was dropped.
  - [ ] (f) Model was right-sized, or the user was offered `/model sonnet`.

- [ ] **Step 3: Run the hook test once more to confirm the repo is green**

```bash
cd "E:/Ongoing Projects/Agentium" && bash .claude/skills/monk/reference/test_filter.sh
```

Expected: `ALL HOOK TESTS PASSED`

- [ ] **Step 4: If any wording fix was needed during validation, commit it; otherwise confirm done**

```bash
git status --short
```

Expected: clean (or only the reviewed fix staged and committed). Do **not** leave uncommitted changes.

---

## Self-Review Notes (run by planner)

- **Spec coverage:** §1 purpose → Task 1–7; §2 core principle → Task 2; §3 activation/scope → Task 1 + Global Constraints; §4 operating rules → Tasks 3–5; §5 guardrail → Task 6; §6 explanatory note → Task 7; §7 optional hook → Task 8 (reference, not enabled, per Global Constraints); §8 self-check → Task 7; §9 SKILL.md structure → all tasks assemble that exact structure; §10 validation → Task 9 acceptance checklist; §11 sources → captured in the spec, not duplicated here; §12 YAGNI → enforced via Global Constraints (no Agentium changes, no settings wiring, no metrics).
- **Placeholder scan:** no TBD/TODO; every step shows actual content or command.
- **Type consistency:** `'<!-- APPEND -->'` marker is the single handoff token across Tasks 1–7; `name: monk` asserted consistently; hook script path `reference/filter-verbose-output.sh` matches the path named in the SKILL.md "Optional hook" section (Task 7) and the test (Task 8). No naming drift.
