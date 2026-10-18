# onjeon-ai-gateway

AI gateway (T-KN-03). Provider trait, per-call records (C-19), JSON Schema output check with retry limit → `unresolved`, monthly and per-user daily cost caps → `ONJ-AP-L-020` with `degraded = true`.

- Records hold only: family label, model-ref hash, prompt/schema version, cost, latency, run id, attempt, status. Never prompt, output or user document text.
- No real provider adapter exists yet (provider choice is D-02). `fixture_only` is test-only.
- Operating rule 7: review roles (author/approver/red team) live in `review_policy.json`, unrelated to the development role table; this crate reads neither.
- Not done here: persistence of caps/records (in-memory), evaluation harness, quote-match check for model-generated amounts/dates (§29), provider retention settings.
- Tests: `cargo test -p onjeon-ai-gateway` (includes `provider_sdk_only_here`).
