# Provider-Facing Load Test — Sustained Run Report

_Generated: 2026-07-13 15:03:39 UTC_

Driver: `python locustfile.py` (stdlib-only, no Locust service required).
The embedded `MockProviderServer` absorbs OpenAI-compatible
`/v1/chat/completions` traffic and counts requests, 429s, errors and
concurrent in-flight calls so worker stability is observable.

## Signals (Task 26)

| Signal | Value | Notes |
|--------|-------|-------|
| Provider RPS | **260.85** | requests_total=6859 over 26.3s |
| Queue depth (pending_count) | **None** | from Agentium dashboard endpoint (n/a if unreachable or erroring; populated under the Locust run that drives Agentium tasks) |
| Retry count (429s served) | **688** | provider_429_ratio=0.1003 |
| Worker stability | **STABLE** | errors=0, inflight_peak=3 |

## Interpretation
- **Provider RPS** is the load actually reaching the mock provider — the
  number the resilience layer (token bucket, concurrency cap) must absorb.
- **pending_count** shows whether the queue drained under load (it should
  stay bounded; a runaway value means workers stalled).
- **Retry count** exercises the 429 → rotate/backoff path; a flat 429 ratio
  below `PROVIDER_MAX_429_RATIO` means retries are keeping throughput up.
- **Worker stability** is STABLE when the provider reported zero errors and
  peak concurrency stayed under `PROVIDER_MAX_INFLIGHT`.
