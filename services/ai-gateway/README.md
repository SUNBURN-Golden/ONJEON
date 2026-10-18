# onjeon-ai-gateway

AI gateway (T-KN-03). Provider trait, per-call records (C-19), JSON Schema output check with retry limit → `unresolved`, monthly and per-user daily cost caps → `ONJ-AP-L-020` with `degraded = true`.

- Records hold only: family label, model-ref hash, prompt/schema version, cost, latency, run id, attempt, status. Never prompt, output or user document text.
- No real provider adapter exists yet (provider choice is D-02). `fixture_only` is test-only.
- Operating rule 7: review roles (author/approver/red team) live in `review_policy.json`, unrelated to the development role table; this crate reads neither.
- Not done here: persistence of caps/records (in-memory), evaluation harness, quote-match check for model-generated amounts/dates (§29), provider retention settings.
- Tests: `cargo test -p onjeon-ai-gateway` (includes `provider_sdk_only_here`).

## Known limits

- Caps are checked before each attempt and cost is recorded after it; concurrent
  calls can overshoot a cap by the cost of the calls in flight (no reservation).
- Calls with `user_id: None` are anonymous/system work and count toward the
  monthly cap only.
- A provider error has no model ref; its record carries the SHA-256 of the empty
  ref (`NO_MODEL_REF`) so `model_ref_hash` always matches `Sha256Hex`.
- `prompt_version` must be non-empty without whitespace (`ModelVersion` pattern).
- `provider_sdk_only_here` checks a curated list of SDK crate names; an SDK
  under a name not on the list (or vendored) is not detected.
- The schema validator ignores malformed keyword values and compares numeric
  bounds as `f64`.
