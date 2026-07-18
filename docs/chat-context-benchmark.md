# Chat Context Token Benchmark (Task 2.1)

This note documents the token savings from the token-efficient chat context
feature and how to reproduce the measurement.

## What changed

Every Sovereign↔Head chat turn previously sent the **full** chat history to
the model (capped at a hard 30-turn slice). Now:

1. **Sliding window** — only the last `chat.context_window_size` (default 10)
   turns are sent, plus the pinned **first** user message (original intent).
2. **Background summarization** — turns outside the window are condensed into
   a rolling structured summary (facts / decisions / open threads) stored in
   Redis and injected into the system prompt prefix.
3. **On-demand recovery** — the agent can call `get_full_history` /
   `search_chat_history` when the window + summary are insufficient.
4. **Prompt caching** — the stable prefix (system prompt + summary + first
   message) is cacheable (Anthropic `cache_control`, OpenAI `prompt_cache_key`),
   so repeat prefixes are billed at the cache-read rate (~10% of input).

## How to measure

`ChatService.process_message` logs an `estimated_tokens` value (and returns it
in the chat response under `metadata.estimated_tokens`) and `raw_turn_count`.

- **Before** (old behavior): tokens ≈ system_prompt + full_history. With a 55
  turn history this grows linearly with conversation length.
- **After** (new behavior): tokens ≈ system_prompt + summary + (window + 1)
  turns + current message. Bounded, independent of total conversation length.

### Reproduce

Run the integration test `backend/tests/integration/test_chat_context_compaction.py`
with the integration stack up:

```bash
make test-integration
```

It seeds 55 turns and asserts the compacted history is 11 messages (pinned
first + last 10), while the middle turn remains recoverable via
`get_full_history`.

## Example (illustrative)

For a 55-turn conversation (~40 tokens/turn ≈ 2,200 history tokens) with a
~600-token system prompt:

| Strategy            | Tokens sent / turn |
|---------------------|--------------------|
| Full history (old)  | ~2,800             |
| Window + summary    | ~1,200 (system 600 + summary 200 + 10 turns 400) |

Plus ~90% of the system-prompt prefix is served from cache on repeat turns.

Actual numbers vary by model tokenizer and message length; the logged
`estimated_tokens` is authoritative.
