//! Archive key layout (DATA_PIPELINE_CONTRACT §3.1, `infra/r2/README.md` §1).
//! Byte-compatible with `tools/source_archive.py` so one store verifies under both tools.

/// `objects/sha256/<aa>/<bb>/<sha256>` — the bytes; the key is the SHA-256 of the bytes.
pub fn object_key(digest: &str) -> String {
    format!(
        "objects/sha256/{}/{}/{}",
        &digest[0..2],
        &digest[2..4],
        digest
    )
}

/// `<stamp>` of an observation record: `observed_at` with everything but `[0-9TZ]` removed,
/// exactly like the Python `re.sub(r"[^0-9TZ]", "", observed_at)`.
pub fn observation_stamp(observed_at: &str) -> String {
    observed_at
        .chars()
        .filter(|c| c.is_ascii_digit() || *c == 'T' || *c == 'Z')
        .collect()
}

/// `observations/<source_id>/<stamp>_<sha256[:16]>.json`.
pub fn observation_key(source_id: &str, observed_at: &str, digest: &str) -> String {
    format!(
        "observations/{}/{}_{}.json",
        source_id,
        observation_stamp(observed_at),
        &digest[..16]
    )
}

/// Prefix + directory for a quarantined response (format validation failed): the fetched
/// bytes and their record are kept as evidence but never become an `objects/` original.
/// `quarantine/<source_id>/<stamp>_<sha256[:16]>/`.
pub fn quarantine_dir(source_id: &str, observed_at: &str, digest: &str) -> String {
    format!(
        "quarantine/{}/{}_{}",
        source_id,
        observation_stamp(observed_at),
        &digest[..16]
    )
}

/// `unacquired/<source_id>/<stamp>_<sha256[:16]>.json` — an expected document that could not
/// be secured is recorded separately, with its reason; it is never counted as acquired.
pub fn unacquired_key(source_id: &str, observed_at: &str, record_sha256: &str) -> String {
    format!(
        "unacquired/{}/{}_{}.json",
        source_id,
        observation_stamp(observed_at),
        &record_sha256[..16]
    )
}

/// The Python `SAFE_ID` rule: a store source id is `^[a-z0-9_]+$` (the `src:<org>/<channel>/<n>`
/// shape of the domain events is a different namespace; see `events`).
pub fn valid_source_id(id: &str) -> bool {
    !id.is_empty()
        && id
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
}
