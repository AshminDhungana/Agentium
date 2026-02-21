# AI Developer Workflow

> A professional, repeatable pattern for building features and fixing bugs using AI agents and AI chatbots — without losing control of quality, correctness, or your codebase.

---

## Core Principles Before You Start

- **You are the architect. AI is the contractor.** AI executes; you decide.
- **Never let AI write code you don't understand.** If you can't review it, you can't own it.
- **Context is everything.** The quality of AI output is directly proportional to the context you provide.
- **One subtask at a time.** Scope creep kills AI-assisted sessions. Keep each AI interaction tightly bounded.
- **Always work on a branch.** Never let AI agents touch `main` or `production` directly.

---

## Step 1 — Identify & Prioritize the Subtask

**Goal:** Know exactly what you're working on before anything else.

Break the larger feature or bug into the smallest independently completable unit of work. A subtask should be something you can finish in one focused session — ideally under two hours.

**Ask yourself:**

- What is the single next thing that needs to exist or be fixed?
- Does this subtask have hard dependencies on unfinished work? If yes, resolve those first.
- Is this a UI change, a data/API change, a logic change, or an infrastructure change? Keep these separate where possible.

**AI tip:** Paste your full task list or backlog into a chatbot and ask it to help prioritize by dependency order and risk. AI is good at surfacing hidden dependencies you might otherwise miss.

**Output of this step:** A single, clearly scoped subtask statement.

> Example: _"Add server-side validation to the `/api/users/register` endpoint for email format and password strength, and return structured error responses."_

---

## Step 2 — Define the Expected Output

**Goal:** Know what "done" looks like before writing a single line of code.

Define the expected output concretely — what will exist, what will behave differently, and what the user or consumer of the code will experience.

**Define:**

- What is the visible or testable end result? (UI state, API response shape, database record, log output)
- What are the success criteria — what must be true for this to be considered complete?
- What is explicitly out of scope for this subtask?

**Do this yourself or with AI:** Paste your subtask statement into a chatbot and ask: _"What should the expected inputs, outputs, and observable behaviors be for this feature? Give me a concrete specification."_ Refine it until it accurately reflects your intent.

**Output of this step:** A short specification — 5 to 15 lines describing inputs, outputs, and acceptance criteria.

---

## Step 3 — Plan the Implementation & Identify Risks

**Goal:** Think before you code. Catch problems on paper, not in production.

Map out how you'll implement the subtask. This is where you think through architecture, data flow, and what could go wrong.

**Cover these areas:**

**Implementation approach:**

- Which files, modules, or services will change?
- What new code needs to be created versus what existing code needs to be modified?
- Are there existing patterns in the codebase you should follow?

**Edge cases to consider:**

- Empty inputs, null values, and very large inputs
- Concurrent requests or race conditions
- Auth and permission edge cases
- Network failures or timeouts for external calls
- Partial failure states — what happens if step 2 of 3 fails?

**Breaking change prevention:**

- What existing functionality could this change affect?
- Are there other consumers of the code you're modifying — other endpoints, components, or shared utilities?
- Do you need a feature flag to safely roll this out?
- Is a database migration involved? Is it backward compatible?

**AI tip:** Give the chatbot your current implementation and your plan, then ask: _"What edge cases am I missing? What could break in the existing system if I make these changes?"_ This is one of the highest-value uses of AI in the entire workflow.

**Output of this step:** A short risk list and a confirmed implementation approach.

---

## Step 4 — Write the Detailed Step-by-Step Plan

**Goal:** Create a concrete, ordered to-do list that you or an AI agent can execute without ambiguity.

This is your implementation blueprint. Write it out as numbered steps, specific enough that each one represents a single clear action. Include testing steps inline — don't treat testing as an afterthought.

**Template for each step:**

```
[ ] Action: <what to do>
    File(s): <which files are affected>
    Notes: <any constraints, patterns to follow, or gotchas>
    Test: <how to verify this step worked>
```

**Example plan:**

```
[ ] 1. Add Zod validation schema for registration payload
       File: src/validators/user.validator.ts
       Notes: Match the existing schema pattern in auth.validator.ts
       Test: Unit test with valid and invalid inputs

[ ] 2. Apply validator middleware to POST /api/users/register
       File: src/routes/user.routes.ts
       Notes: Use the existing validateRequest middleware wrapper
       Test: Manual curl with missing fields should return 400

[ ] 3. Update error response handler to include field-level errors
       File: src/middleware/errorHandler.ts
       Notes: Must remain backward compatible with existing error shape
       Test: Existing error handler tests still pass

[ ] 4. Write integration test for the full registration flow
       File: tests/integration/user.register.test.ts
       Test: Cover valid registration, duplicate email, invalid password, malformed JSON

[ ] 5. Update API documentation
       File: docs/api/users.md
       Test: Review only
```

**AI tip:** Give a chatbot your subtask spec and risk notes from Steps 2–3, and ask it to generate this to-do list for you. Then review and edit it — AI-generated plans often skip testing steps or assume context they don't have.

**Output of this step:** A complete, numbered implementation plan with inline test steps.

---

## Step 5 — Implement

**Goal:** Execute the plan, using AI to accelerate without losing oversight.

Work through your Step 4 plan item by item. Do not skip ahead or let AI make decisions outside the scope of the current step.

**If implementing yourself:**

- Follow the plan. If you deviate, update the plan first.
- Commit frequently with meaningful messages — one logical change per commit.

**If using an AI agent (Cursor, Copilot, Claude Code, etc.):**

- Give the agent one step at a time, not the entire plan at once.
- Always provide full context: the relevant files, the existing patterns, and exactly what you want.
- After each agent action, read the diff before accepting it. Do not blindly accept AI-generated code.
- If the agent goes off-plan, stop it, re-scope the prompt, and restart that step.

**Prompt pattern for AI agents:**

> _"Here is the current state of [file]. I need you to [specific action from plan]. Follow the pattern used in [reference file]. Do not change anything outside of [scope]. Here are the constraints: [constraints from your plan]."_

**Red flags to watch for:**

- AI removing or refactoring code outside the requested scope
- AI adding dependencies you didn't ask for
- AI "solving" a problem differently than your plan without explaining why
- AI generating code that touches shared utilities or database schemas unexpectedly

**Output of this step:** Implemented, committed code — one step at a time.

---

## Step 6 — Test All Cases

**Goal:** Verify the implementation matches the spec and hasn't broken anything else.

Testing is not optional, and it is not the last thing you do — it runs alongside every step. Here you perform a final, comprehensive pass.

**Testing checklist:**

**Unit tests:**

- Does the new logic handle all expected inputs correctly?
- Are all edge cases from Step 3 covered?
- Do existing unit tests still pass?

**Integration tests:**

- Does the full flow work end-to-end?
- Test the happy path first, then every failure and edge case path.

**Regression check:**

- Run the full test suite. Investigate any new failures — do not ignore them.
- Manually test any adjacent features that share code with your changes.

**Manual testing:**

- Verify the actual behavior in a browser or API client (Postman, curl, etc.).
- Test on realistic data, not just the minimal example that passes.

**If using AI agents for testing:**

- Ask the agent to generate test cases from your spec (Step 2) and edge cases (Step 3).
- Review every generated test — AI commonly generates tests that only cover the happy path or mock too aggressively, missing real bugs.
- Ask the agent: _"What test cases would catch regressions in the existing system caused by these changes?"_

**Output of this step:** All tests written and passing. No regressions.

---

## Step 7 — Verify & Close

**Goal:** Confirm the work is truly complete and leave a clear record of it.

Do a final structured review before marking the task done.

**Completion checklist:**

```
[ ] All items in the Step 4 plan are checked off
[ ] All tests pass (unit, integration, regression)
[ ] Code has been reviewed (self-review at minimum, peer review preferred)
[ ] No debug code, console.logs, or temporary hacks left in
[ ] Relevant documentation updated (API docs, README, inline comments)
[ ] Any TODOs or deferred items are logged in the backlog with context
[ ] Branch is clean and ready to merge or open for PR
[ ] PR description clearly states: what changed, why, and how to test it
```

**Mark completion clearly:**

- Update the ticket or issue with a summary of what was done and any decisions made.
- In your PR or commit message, reference the task and write a human-readable summary.
- If working with a team, call out anything the reviewer needs to pay special attention to.

**AI tip:** Paste your diff into a chatbot and ask: _"Review this code change. Are there any bugs, missing edge cases, security issues, or style inconsistencies? Does it match this spec: [paste spec]?"_ This is a cheap second opinion before code review.

**Output of this step:** Task closed with full documentation. Ready to move to the next priority.

---

## AI Agent Session Protocol

> A repeatable micro-workflow to apply **within each step** of the main workflow above. This governs how you structure every individual AI agent or chatbot interaction to keep sessions focused, context-accurate, and auditable.

The core rule: **one task, one session, one skill.** Every time you engage an AI agent, you are starting a bounded unit of work. This section defines exactly how to do that well.

---

### Why This Matters

AI agents degrade in quality as sessions grow longer. Context gets diluted, earlier instructions get "forgotten," and the agent starts making assumptions based on conversational drift rather than your actual codebase. The solution is not a better agent — it is a better protocol. Short sessions with explicit context handoffs outperform long sessions every time.

---

### The Per-Step Agent Loop

Apply this loop each time you engage an AI agent for any step in the main workflow.

---

#### Phase 1 — Load the Right Model

Before writing a single prompt, identify the skill or capability the task actually requires. Using the wrong tool for a step is one of the most common sources of poor AI output.

**Ask yourself:**

- Is this a **planning task**? Use a reasoning-focused chatbot (Claude, ChatGPT, Gemini).
- Is this a **code generation task**? Use an in-editor agent (Cursor, Copilot) or an agentic coding tool (Claude Code).
- Is this a **multi-file refactor**? Use an agentic tool with codebase awareness, not a plain chatbot.
- Is this a **review or QA task**? Use a chatbot with a diff or file paste — not the same agent that wrote the code.
- Is this a **documentation task**? Use a chatbot with your spec and final code as input.

Match the tool to the task. Do not use a code agent for planning, and do not use a plain chatbot for multi-file edits.

> Note: You can also choose to use a single AI provider for all tasks if that fits your workflow.

**Skill reference:**

| Task Type                                   | Recommended Tool              |
| ------------------------------------------- | ----------------------------- |
| Prioritization, spec writing, risk analysis | Claude, ChatGPT, Gemini       |
| Single-file code generation                 | Cursor, GitHub Copilot        |
| Multi-file agentic coding                   | Claude Code, Cursor Agent     |
| Code review, diff analysis                  | Claude, ChatGPT + paste       |
| Test generation                             | AI agent with spec as context |
| Documentation                               | AI chatbot with code + spec   |

---

#### Phase 2 — Execute the Step

With the right tool loaded, execute exactly one step from your implementation plan. Not two. Not "this step and the next one if there's time."

**Prompt construction checklist — include all of the following:**

```
[ ] What step you are on (e.g., "Step 3 of 5: Apply validator middleware")
[ ] The relevant file(s) in their current state
[ ] The pattern or convention to follow (with a reference file if possible)
[ ] The exact scope boundary ("do not modify anything outside X")
[ ] The success condition ("this is done when Y is true")
[ ] Known constraints or gotchas from your planning notes
```

**Use predefined skills where available, or write and save your own for reuse.** For example, if the task involves frontend development, load your frontend development skills before writing any prompts. In Claude Code, you can reference skills using `/skills`. Some AI providers will automatically load the appropriate skills for a given task type.

**Prompt template:**

> _"We are working on [subtask name]. This is step [N] of [total]: [step description]._
>
> _Current state of [file]: [paste or attach file]_
>
> _Reference pattern from [file]: [paste relevant section]_
>
> _Constraints: [list from your plan]_
>
> _Scope boundary: only modify [specific files/functions]. Do not touch [X, Y, Z]._
>
> _Done when: [success condition from plan]."_

After the agent responds, read the full output before accepting anything. Check the diff or generated code against your plan. If the agent went outside scope, reject it, clarify the boundary, and re-prompt.

---

#### Phase 3 — Create a Handoff Document _(Recommended)_

After completing the step, use the agent — or write it yourself — to produce a brief markdown handoff document. This document is your context bridge, ensuring the next session starts with full situational awareness rather than a blank slate.

**When to create one:**

- You plan to start a new session for the next step (almost always recommended)
- The step produced changes that will affect subsequent steps
- You want a lightweight audit trail of decisions made

**Handoff document template:**

```markdown
# Handoff: [Subtask Name] — Step [N] Complete

## What Was Done

[1–3 sentences describing the change made]

## Files Modified

- `path/to/file.ts` — [what changed and why]
- `path/to/other.ts` — [what changed and why]

## Decisions Made

- [Any non-obvious choices made and the reasoning behind them]

## Current State

[Brief description of where things stand — what works, what's wired up, what isn't yet]

## Next Step

**Step [N+1]:** [description from your implementation plan]

### Context Needed for Next Session

- Relevant files: [list]
- Pattern to follow: [reference file or convention]
- Constraints: [carry forward from planning notes]
- Watch out for: [any known risks or gotchas for the next step]

## Open Questions / Deferred Items

- [Anything unresolved that the next session or a future task needs to address]
```

Save this file alongside your working directory or in a `/.ai-sessions/` folder in your repo (gitignored). Name it clearly: `step-03-validator-middleware.md`.

**To generate it with AI:** After the step is complete, paste your diff and step notes into a chatbot and ask: _"Write a session handoff document for this step using this template: [paste template]."_ Review and edit before saving.

---

#### Phase 4 — Start a New Session _(Recommended for Most Steps)_

For any step that involves real code changes or significant decisions, start a fresh agent session rather than continuing in the same one.

**Why:**

- Long sessions dilute the agent's attention across earlier context
- A fresh session with a crisp handoff document outperforms a long session every time
- It forces you to re-verify your current state, which catches drift early

**When continuing in the same session is acceptable:**

- The current step is a minor follow-up (fixing a typo, adjusting a return value)
- No new files or architectural decisions are involved
- The session is still early — fewer than 10–15 exchanges

**When you must start a new session:**

- Moving to a different step in your plan
- Switching from planning to coding, or from coding to review
- The session has grown long or the agent has started making assumptions
- You are switching tool types (e.g., chatbot → code agent)

---

#### Phase 5 — Resume with Context in the New Session

If you started a new session, your first message should always be to load the appropriate skills and then a context load — not a task prompt. Do not assume the new session knows anything.

**Opening message template:**

> _"I'm continuing work on [subtask name]. Here is the current context:_
>
> _[Paste or attach the handoff document from Phase 3]_
>
> _We are now on Step [N+1]: [description]._
>
> _Please confirm you understand the current state and constraints before we proceed."_

Ask the agent to confirm its understanding before it begins. This surfaces any misinterpretation of the handoff document before it results in a bad code change.

Now, loop back to Phase 2, if you have already loaded the required skills skip that step in Phase 2.
You should continue till the task complition.
For a new task start again from Phase 1.

---

### Agent Session Anti-Patterns

These are the most common ways agent sessions go wrong. Recognize them early.

**Carrying too much context into one session.** If your session has more than 15–20 exchanges, quality is likely degrading. Start fresh with a handoff document.

**Skipping the model selection step.** Using a plain chatbot for multi-file code generation produces unfocused, often broken results. Match the tool to the task.

**Resuming a session without a context reset.** Starting your message with "continue from where we left off" relies on the agent's degraded memory of a long conversation. Always re-provide context explicitly.

**Letting the agent decide what to do next.** The agent should execute a bounded task, not choose the next step. You choose. The agent executes.

**Saving handoff documents only sometimes.** The habit only works if it's consistent. Make it automatic — every step, every session.

**Not reading the diff.** AI agents will occasionally refactor, rename, or remove adjacent code without being asked. Read every diff before accepting it, every time.

---

### Quick Reference: Per-Step Agent Checklist

```
[ ] 1. Identify the correct model or tool for this step
[ ] 2. Load the appropriate skills, then construct a scoped, context-complete prompt
[ ] 3. Execute the step — one step, one prompt, one scope
[ ] 4. Read the full diff or output before accepting
[ ] 5. Create a handoff document capturing decisions, changes, and next-step context
[ ] 6. Start a new session for the next step (unless continuation is clearly appropriate)
[ ] 7. Open the new session, load the appropriate skills and start with an explicit context load from the handoff document
[ ] 8. Ask the agent to confirm understanding before proceeding
```

---

### Folder Structure for Session Artifacts _(Optional but Recommended)_

Keep a `.ai-sessions/` folder in your working directory (gitignored) to store handoff documents and session notes. Structure it by feature or subtask.

```
.ai-sessions/
  user-registration-validation/
    step-01-zod-schema.md
    step-02-middleware.md
    step-03-error-handler.md
    step-04-integration-tests.md
    step-05-api-docs.md
```

This gives you a full audit trail of every decision made during the AI-assisted implementation — useful for code review, onboarding, and retrospectives.

---

## Quick Reference Card

| Step              | What You're Doing                   | Primary Tool     |
| ----------------- | ----------------------------------- | ---------------- |
| 1. Prioritize     | Pick the next right subtask         | You + AI chatbot |
| 2. Define Output  | Write the spec                      | You + AI chatbot |
| 3. Plan & Risk    | Map implementation, find edge cases | You + AI chatbot |
| 4. Write Plan     | Create step-by-step todo with tests | You + AI chatbot |
| 5. Implement      | Execute the plan step by step       | You + AI agent   |
| 6. Test           | Full test coverage + regression     | You + AI agent   |
| 7. Verify & Close | Final review and documentation      | You              |

**Per-step agent loop (apply within every step above):**

| Phase          | Action                                             |
| -------------- | -------------------------------------------------- |
| 1. Load Skill  | Identify and use the right tool for the task type  |
| 2. Execute     | One step, one scoped prompt, one bounded scope     |
| 3. Document    | Create a handoff markdown file                     |
| 4. New Session | Start fresh for the next step, load requied skills |
| 5. Resume      | Load context from handoff doc before proceeding    |

---

## Common Pitfalls to Avoid

**Skipping Steps 2–4 and jumping straight to coding.** This is where AI-assisted development goes wrong most often. AI agents work best when they have a tightly scoped, well-specified task. Vague prompts produce vague code.

**Giving AI agents too much context at once.** Long prompts with many files and many requirements produce unfocused results. One step, one concern, one prompt.

**Not reading AI diffs.** AI agents will sometimes quietly refactor, rename, or remove things adjacent to what you asked for. Always read the full diff.

**Treating passing tests as proof of correctness.** AI-generated tests often test the implementation rather than the requirement. Write tests against the spec, not the code.

**Letting AI accumulate context debt.** In long AI chat sessions, earlier context degrades. For longer implementations, start a fresh session per major step and re-provide context explicitly.

**Merging without a human review pass.** Even if AI wrote the code and AI tested the code, a human should read the final diff. You are responsible for what goes into your codebase.

**Skipping session handoff documents.** Without a structured handoff, every new session starts cold. Handoff docs take five minutes to write and save far more time than that in lost context and repeated mistakes.

---

## Suggested Tools by Role

| Task                        | Recommended Tools                |
| --------------------------- | -------------------------------- |
| Planning & spec writing     | Claude, ChatGPT, Gemini          |
| Code generation (in-editor) | Cursor, GitHub Copilot, Cline    |
| Agentic coding (multi-file) | Claude Code, Cursor Agent, Devin |
| Code review assistance      | Claude, ChatGPT + diff paste     |
| Test generation             | AI agent with spec as context    |
| Documentation               | AI chatbot with code + spec      |

---

Author: Ashmin Dhungana
_Last updated: February 2026_
