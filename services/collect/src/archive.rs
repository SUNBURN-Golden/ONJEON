//! Write-once archive operations — the `put_once`/`observe`/`listing`/`verify_copy` port of
//! `tools/source_archive.py` (DATA_PIPELINE_CONTRACT §3.1).
//!
//! - Every write goes through [`put_once`]: same bytes already stored → `AlreadyPresent`
//!   (verified, not rewritten); different bytes under an existing key → [`Conflict`], nothing
//!   is overwritten and the run must stop.
//! - [`observe`] writes one `observations/…` record per fetch: source id, URL, observation
//!   time, hash, size, content type and the document role (09 P02/P03).
//! - [`put_quarantined`] isolates a fetched response that failed [`format::check`]: the bytes
//!   and a record go under `quarantine/`, never under `objects/`, and no observation is
//!   written — a failed response is not an archived original.
//! - [`record_unacquired`] records under `unacquired/` an expected document that could not
//!   be secured, with its `acquisition_status` reason — kept apart from observations.

use std::collections::BTreeMap;

use serde::Serialize;
use serde_json::{Map, Value};

use crate::digest::sha256_hex;
use crate::format::{ExpectedFormat, FormatFailure};
use crate::keys;
use crate::store::{listing_of, Exists, Store, StoreError, StoredSha};

/// The two non-error outcomes of [`put_once`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PutOutcome {
    Stored,
    AlreadyPresent,
}

impl PutOutcome {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Stored => "stored",
            Self::AlreadyPresent => "already_present",
        }
    }
}

/// A key already holds different bytes. Nothing was overwritten; the run must stop.
#[derive(Debug)]
pub struct Conflict(pub String);

impl std::fmt::Display for Conflict {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "conflict: {}", self.0)
    }
}
impl std::error::Error for Conflict {}

pub type ArchiveResult<T> = Result<T, ArchiveError>;

#[derive(Debug)]
pub enum ArchiveError {
    Conflict(Conflict),
    Store(StoreError),
    BadInput(String),
}

impl std::fmt::Display for ArchiveError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Conflict(c) => c.fmt(f),
            Self::Store(e) => e.fmt(f),
            Self::BadInput(m) => write!(f, "bad input: {m}"),
        }
    }
}
impl std::error::Error for ArchiveError {}

impl From<Conflict> for ArchiveError {
    fn from(c: Conflict) -> Self {
        Self::Conflict(c)
    }
}
impl From<StoreError> for ArchiveError {
    fn from(e: StoreError) -> Self {
        Self::Store(e)
    }
}

/// Write a key once. Same bytes already there → `AlreadyPresent`. Different bytes →
/// `Conflict`. Every write in this crate goes through here, so a re-run can never silently
/// keep an old object while reporting the hash of a new input.
pub fn put_once(
    st: &dyn Store,
    key: &str,
    body: &[u8],
    content_type: &str,
) -> ArchiveResult<PutOutcome> {
    match st.stored_sha256(key)? {
        StoredSha::Absent => {}
        stored => {
            let stored = match stored {
                StoredSha::Sha(s) => s,
                StoredSha::NoChecksum => sha256_hex(&st.get(key)?),
                StoredSha::Absent => unreachable!(),
            };
            let new = sha256_hex(body);
            if stored != new {
                return Err(Conflict(format!(
                    "{key}: stored sha256 {}… differs from new input {}…; not overwritten",
                    &stored[..16],
                    &new[..16]
                ))
                .into());
            }
            return Ok(PutOutcome::AlreadyPresent);
        }
    }
    match st.put_new(key, body, content_type) {
        Ok(()) => Ok(PutOutcome::Stored),
        Err(e) if e.kind == "exists" => {
            // Lost a create race (or the backend has no checksum): compare by downloading.
            let existing = st.get(key)?;
            let (got, new) = (sha256_hex(&existing), sha256_hex(body));
            if got != new {
                return Err(Conflict(format!(
                    "{key}: stored sha256 {}… differs from new input {}…; not overwritten",
                    &got[..16],
                    &new[..16]
                ))
                .into());
            }
            Ok(PutOutcome::AlreadyPresent)
        }
        Err(e) => Err(e.into()),
    }
}

/// Write the bytes under their own hash: `objects/sha256/<aa>/<bb>/<sha256>`.
/// Returns `(digest, outcome)`.
pub fn put_raw(
    st: &dyn Store,
    body: &[u8],
    content_type: &str,
) -> ArchiveResult<(String, PutOutcome)> {
    let digest = sha256_hex(body);
    let out = put_once(st, &keys::object_key(&digest), body, content_type)?;
    Ok((digest, out))
}

/// One fetch record (`observations/<source_id>/<stamp>_<sha16>.json`). Field order and
/// `indent=2` JSON match the Python record byte-for-byte. `doc_role` is required: a
/// preservation record must name the document kind (vocabulary axis `doc_role`).
#[derive(Debug, Clone, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Observation {
    pub source_id: String,
    pub url: String,
    pub observed_at: String,
    pub doc_role: onjeon_contracts::DocRole,
    /// The fetched format label (`samples.csv` `format`, e.g. `text_pdf`, `scanned_pdf`,
    /// `html`). Written as `format`, as the Python `extra` does.
    pub format: Option<String>,
    /// Extra flat fields (e.g. `sample_id`), serialized like the Python `extra` map.
    pub extra: BTreeMap<String, String>,
}

/// Write the object (if new) and one observation record for a fetch. Returns the object
/// digest, object outcome, observation key and observation outcome.
pub fn observe(
    st: &dyn Store,
    obs: &Observation,
    body: &[u8],
    content_type: &str,
) -> ArchiveResult<(String, PutOutcome, String, PutOutcome)> {
    if !keys::valid_source_id(&obs.source_id) {
        return Err(ArchiveError::BadInput(format!(
            "source_id must be lower snake_case: {}",
            obs.source_id
        )));
    }
    if obs.url.trim().is_empty()
        || obs.observed_at.trim().is_empty()
        || obs.extra.keys().any(|k| {
            [
                "source_id",
                "url",
                "observed_at",
                "sha256",
                "bytes",
                "content_type",
                "object_key",
                "doc_role",
                "format",
            ]
            .contains(&k.as_str())
        })
    {
        return Err(ArchiveError::BadInput(
            "missing provenance or reserved extra field".into(),
        ));
    }
    let expected = obs
        .format
        .as_deref()
        .and_then(ExpectedFormat::parse)
        .or_else(|| {
            ExpectedFormat::parse(match content_type.split(';').next().unwrap_or("").trim() {
                "application/pdf" => "pdf",
                "text/html" => "html",
                "application/json" => "json",
                _ => "binary",
            })
        })
        .unwrap();
    if let Err(failure) = crate::format::check(expected, content_type, body) {
        put_quarantined(
            st,
            &obs.source_id,
            &obs.url,
            &obs.observed_at,
            obs.doc_role,
            expected,
            content_type,
            &failure,
            body,
        )?;
        return Err(ArchiveError::BadInput(
            "response quarantined: format validation failed".into(),
        ));
    }
    let (digest, state) = put_raw(st, body, content_type)?;
    let key = keys::observation_key(&obs.source_id, &obs.observed_at, &digest);
    let rec = observation_record(
        obs,
        &digest,
        body.len(),
        content_type,
        &keys::object_key(&digest),
    );
    let rec_body = record_json(&rec);
    let ostate = put_once(st, &key, &rec_body, "application/json")?;
    Ok((digest, state, key, ostate))
}

fn observation_record(
    obs: &Observation,
    digest: &str,
    size: usize,
    content_type: &str,
    object_key: &str,
) -> Value {
    // Field order fixed to the Python record; `extra` keys are flattened after them.
    let mut rec = Map::new();
    rec.insert("source_id".into(), obs.source_id.clone().into());
    rec.insert("url".into(), obs.url.clone().into());
    rec.insert("observed_at".into(), obs.observed_at.clone().into());
    rec.insert("sha256".into(), digest.into());
    rec.insert("bytes".into(), size.into());
    rec.insert("content_type".into(), content_type.into());
    rec.insert("object_key".into(), object_key.into());
    rec.insert("doc_role".into(), obs.doc_role.as_str().into());
    if let Some(f) = &obs.format {
        rec.insert("format".into(), f.clone().into());
    }
    for (k, v) in &obs.extra {
        rec.insert(k.clone(), v.clone().into());
    }
    Value::Object(rec)
}

/// `json.dumps(rec, ensure_ascii=False, indent=2) + "\n"`.
pub fn record_json(rec: &Value) -> Vec<u8> {
    if let Some(map) = rec
        .as_object()
        .filter(|m| m.contains_key("object_key") && m.contains_key("sha256"))
    {
        let fields = [
            "source_id",
            "url",
            "observed_at",
            "sha256",
            "bytes",
            "content_type",
            "object_key",
            "doc_role",
            "format",
        ];
        let ordered = fields
            .iter()
            .filter_map(|k| map.get(*k).map(|v| (*k, v)))
            .chain(
                map.iter()
                    .filter(|(k, _)| !fields.contains(&k.as_str()))
                    .map(|(k, v)| (k.as_str(), v)),
            );
        let lines: Vec<_> = ordered
            .map(|(k, v)| {
                format!(
                    "  {}: {}",
                    serde_json::to_string(k).unwrap(),
                    serde_json::to_string(v).unwrap()
                )
            })
            .collect();
        return format!("{{\n{}\n}}\n", lines.join(",\n")).into_bytes();
    }
    let mut out = Vec::new();
    let fmt = serde_json::ser::PrettyFormatter::with_indent(b"  ");
    let mut ser = serde_json::Serializer::with_formatter(&mut out, fmt);
    rec.serialize(&mut ser).expect("record serializes");
    out.push(b'\n');
    out
}

/// `json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n"` — the listing
/// and report file format.
fn sorted_json(doc: &Value) -> Vec<u8> {
    let mut out = Vec::new();
    let fmt = serde_json::ser::PrettyFormatter::with_indent(b" ");
    let mut ser = serde_json::Serializer::with_formatter(&mut out, fmt);
    doc.serialize(&mut ser).expect("record serializes");
    out.push(b'\n');
    out
}

/// Where a format-failed response went.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct QuarantineOutcome {
    pub digest: String,
    pub body_key: String,
    pub record_key: String,
}

/// Isolate a fetched response that failed format validation. The bytes and a record
/// (source, url, observed time, hash, declared type, expected format, failure) are kept
/// under `quarantine/` — evidence preserved, but never an `objects/` original and never an
/// observation, so it cannot be counted as acquired.
#[allow(clippy::too_many_arguments)]
pub fn put_quarantined(
    st: &dyn Store,
    source_id: &str,
    url: &str,
    observed_at: &str,
    doc_role: onjeon_contracts::DocRole,
    expected: ExpectedFormat,
    declared_content_type: &str,
    failure: &FormatFailure,
    body: &[u8],
) -> ArchiveResult<QuarantineOutcome> {
    if !keys::valid_source_id(source_id) {
        return Err(ArchiveError::BadInput(format!(
            "source_id must be lower snake_case: {source_id}"
        )));
    }
    let digest = sha256_hex(body);
    let dir = keys::quarantine_dir(source_id, observed_at, &digest);
    let body_key = format!("{dir}/response");
    let record_key = format!("{dir}/record.json");
    put_once(st, &body_key, body, "application/octet-stream")?;
    let mut rec = Map::new();
    rec.insert("kind".into(), "quarantined_response".into());
    rec.insert("source_id".into(), source_id.into());
    rec.insert("url".into(), url.into());
    rec.insert("observed_at".into(), observed_at.into());
    rec.insert("doc_role".into(), doc_role.as_str().into());
    rec.insert("expected_format".into(), expected.as_str().into());
    rec.insert("sha256".into(), digest.clone().into());
    rec.insert("bytes".into(), body.len().into());
    rec.insert("declared_content_type".into(), declared_content_type.into());
    rec.insert(
        "failure".into(),
        serde_json::to_value(failure).unwrap_or_default(),
    );
    put_once(
        st,
        &record_key,
        &record_json(&Value::Object(rec)),
        "application/json",
    )?;
    Ok(QuarantineOutcome {
        digest,
        body_key,
        record_key,
    })
}

/// An expected document that was not secured. `status` is a vocabulary `acquisition_status`
/// reason (`blocked`, `failed`, `not_found`, `not_disclosed`); `archived`/`unqueried` are
/// not "unacquired" states and are refused.
#[derive(Debug, Clone)]
pub struct UnacquiredRecord {
    pub source_id: String,
    pub url: Option<String>,
    pub doc_role: Option<onjeon_contracts::DocRole>,
    pub observed_at: String,
    pub status: onjeon_contracts::AcquisitionStatus,
    /// Free-text reason, e.g. the blocked detail or the not-found evidence pointer.
    pub reason: String,
}

/// Write the record under `unacquired/`; returns its key.
pub fn record_unacquired(
    st: &dyn Store,
    rec: &UnacquiredRecord,
) -> ArchiveResult<(String, PutOutcome)> {
    use onjeon_contracts::AcquisitionStatus as A;
    if !keys::valid_source_id(&rec.source_id) {
        return Err(ArchiveError::BadInput(format!(
            "source_id must be lower snake_case: {}",
            rec.source_id
        )));
    }
    if rec.reason.trim().is_empty() || rec.observed_at.trim().is_empty() || rec.doc_role.is_none() {
        return Err(ArchiveError::BadInput(
            "unacquired record needs reason, time and document role".into(),
        ));
    }
    match rec.status {
        A::Archived | A::Unqueried => {
            return Err(ArchiveError::BadInput(format!(
                "unacquired record needs a non-acquired status, got {}",
                rec.status.as_str()
            )))
        }
        _ => {}
    }
    let mut doc = Map::new();
    doc.insert("kind".into(), "unacquired_document".into());
    doc.insert("source_id".into(), rec.source_id.clone().into());
    if let Some(u) = &rec.url {
        doc.insert("url".into(), u.clone().into());
    }
    doc.insert("observed_at".into(), rec.observed_at.clone().into());
    if let Some(r) = &rec.doc_role {
        doc.insert("doc_role".into(), r.as_str().into());
    }
    doc.insert("status".into(), rec.status.as_str().into());
    doc.insert("reason".into(), rec.reason.clone().into());
    let body = record_json(&Value::Object(doc));
    let key = keys::unacquired_key(&rec.source_id, &rec.observed_at, &sha256_hex(&body));
    Ok((key.clone(), put_once(st, &key, &body, "application/json")?))
}

/// `mimetypes.guess_type` equivalent for the names this pipeline archives.
pub fn content_type_of(name: &str, format_label: &str) -> &'static str {
    if format_label == "html" {
        return "text/html";
    }
    match name
        .rsplit('.')
        .next()
        .unwrap_or("")
        .to_ascii_lowercase()
        .as_str()
    {
        "pdf" => "application/pdf",
        "html" | "htm" => "text/html",
        "json" => "application/json",
        "xml" => "application/xml",
        "txt" => "text/plain",
        "zip" => "application/zip",
        "png" => "image/png",
        _ => "application/octet-stream",
    }
}

/// `{"listing_rule": "key-sha256-v1", "keys": n, "objects": {key: sha256}}` — the document
/// `listing` writes and `verify-copy --expected` reads (Git-pinnable; no content).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Listing {
    pub objects: BTreeMap<String, String>,
}

impl Listing {
    pub fn from_store(st: &dyn Store) -> ArchiveResult<Self> {
        Ok(Self {
            objects: listing_of(st)?,
        })
    }

    /// Bytes of the pinned listing file, byte-identical to the Python `listing` output.
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut objects = Map::new();
        for (k, v) in &self.objects {
            objects.insert(k.clone(), v.clone().into());
        }
        let mut doc = Map::new();
        doc.insert("keys".into(), self.objects.len().into());
        doc.insert("listing_rule".into(), "key-sha256-v1".into());
        doc.insert("objects".into(), Value::Object(objects));
        sorted_json(&Value::Object(doc))
    }

    /// Parse a pinned listing (`--expected` of `verify-copy`).
    pub fn parse(bytes: &[u8]) -> ArchiveResult<Self> {
        let doc: Value = serde_json::from_slice(bytes)
            .map_err(|_| ArchiveError::BadInput("listing is not JSON".into()))?;
        if doc.get("listing_rule").and_then(Value::as_str) != Some("key-sha256-v1") {
            return Err(ArchiveError::BadInput("unknown listing rule".into()));
        }
        let entries = doc
            .get("objects")
            .and_then(Value::as_object)
            .ok_or_else(|| ArchiveError::BadInput("listing lacks objects".into()))?;
        if doc.get("keys").and_then(Value::as_u64) != Some(entries.len() as u64) {
            return Err(ArchiveError::BadInput("listing key count mismatch".into()));
        }
        let mut objects = BTreeMap::new();
        for (key, value) in entries {
            let digest = value
                .as_str()
                .ok_or_else(|| ArchiveError::BadInput("invalid listing digest".into()))?;
            if digest.len() != 64
                || !digest
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
                || key
                    .split('/')
                    .any(|p| p.is_empty() || p == "." || p == "..")
            {
                return Err(ArchiveError::BadInput("invalid listing entry".into()));
            }
            objects.insert(key.clone(), digest.to_string());
        }
        Ok(Self { objects })
    }
}

/// Per-key result of [`verify_copy`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifyEntry {
    pub key: String,
    pub status: VerifyStatus,
    pub sha256_source: String,
    pub sha256_downloaded: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VerifyStatus {
    ByteIdentical,
    Missing,
    HashMismatch,
}

impl VerifyStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::ByteIdentical => "byte_identical",
            Self::Missing => "missing",
            Self::HashMismatch => "hash_mismatch",
        }
    }
}

pub struct VerifyReport {
    pub checked_at: String,
    pub source: String,
    pub destination: String,
    pub results: Vec<VerifyEntry>,
    /// Keys present only in the destination.
    pub extra_in_destination: Vec<String>,
}

impl VerifyReport {
    pub fn summary(&self) -> BTreeMap<String, usize> {
        let mut s = BTreeMap::new();
        for e in &self.results {
            *s.entry(e.status.as_str().to_string()).or_insert(0) += 1;
        }
        if !self.extra_in_destination.is_empty() {
            s.insert(
                "extra_in_destination".into(),
                self.extra_in_destination.len(),
            );
        }
        s
    }

    /// `true` iff every expected key is byte-identical and (unless `allow_extra`) the
    /// destination holds no leaked keys.
    pub fn passed(&self, allow_extra: bool) -> bool {
        !self.results.is_empty()
            && self
                .results
                .iter()
                .all(|e| e.status == VerifyStatus::ByteIdentical)
            && (allow_extra || self.extra_in_destination.is_empty())
    }

    /// The report file, same shape as the Python `verify-copy --report` output.
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut summary = Map::new();
        for (k, v) in self.summary() {
            summary.insert(k, v.into());
        }
        let mut results = Vec::new();
        for e in &self.results {
            let mut r = Map::new();
            r.insert("key".into(), e.key.clone().into());
            r.insert("status".into(), e.status.as_str().into());
            r.insert("sha256_source".into(), e.sha256_source.clone().into());
            match &e.sha256_downloaded {
                Some(s) => r.insert("sha256_downloaded".into(), s.clone().into()),
                None => r.insert("sha256_downloaded".into(), Value::Null),
            };
            results.push(Value::Object(r));
        }
        let mut doc = Map::new();
        doc.insert("checked_at".into(), self.checked_at.clone().into());
        doc.insert("source".into(), self.source.clone().into());
        doc.insert("destination".into(), self.destination.clone().into());
        doc.insert("summary".into(), Value::Object(summary));
        doc.insert(
            "extra_in_destination".into(),
            Value::Array(
                self.extra_in_destination
                    .iter()
                    .map(|k| k.clone().into())
                    .collect(),
            ),
        );
        doc.insert("results".into(), Value::Array(results));
        let out = record_json(&Value::Object(doc));
        // Python writes indent=2 for reports
        out
    }
}

/// Download every key of `dst` back and compare it with the source, byte for byte.
/// The source is a store or a pinned [`Listing`]. Keys only in the destination are reported
/// (leaked objects) and fail the check unless `allow_extra`.
pub fn verify_copy(
    expected: &Listing,
    source_label: &str,
    dst: &dyn Store,
    allow_extra: bool,
) -> ArchiveResult<VerifyReport> {
    let dst_keys: std::collections::BTreeSet<String> = dst.list("")?.into_iter().collect();
    let mut results = Vec::new();
    for (key, want) in &expected.objects {
        let (status, got) = if !dst_keys.contains(key) {
            (VerifyStatus::Missing, None)
        } else {
            let got = sha256_hex(&dst.get(key)?);
            let mut st = if got == *want {
                VerifyStatus::ByteIdentical
            } else {
                VerifyStatus::HashMismatch
            };
            if st == VerifyStatus::ByteIdentical
                && key.starts_with("objects/sha256/")
                && got != key.rsplit('/').next().unwrap_or("")
            {
                st = VerifyStatus::HashMismatch;
            }
            (st, Some(got))
        };
        results.push(VerifyEntry {
            key: key.clone(),
            status,
            sha256_source: want.clone(),
            sha256_downloaded: got,
        });
    }
    let expected_keys: std::collections::BTreeSet<&String> = expected.objects.keys().collect();
    let mut extra: Vec<String> = dst_keys
        .into_iter()
        .filter(|k| !expected_keys.contains(k))
        .collect();
    extra.sort();
    let _ = allow_extra; // extra keys are always listed; `passed` decides.
    Ok(VerifyReport {
        checked_at: crate::time::stamp(),
        source: source_label.into(),
        destination: dst.describe(),
        results,
        extra_in_destination: extra,
    })
}

/// Copy every key of `src` into `dst` without overwriting (local bundle → object store).
/// Returns counts of `stored`/`already_present`; a `Conflict` aborts the run.
pub fn copy(src: &dyn Store, dst: &dyn Store) -> ArchiveResult<BTreeMap<String, u64>> {
    let mut counts: BTreeMap<String, u64> = BTreeMap::new();
    for key in src.list("")? {
        let body = src.get(&key)?;
        if key.starts_with("objects/sha256/")
            && sha256_hex(&body) != key.rsplit('/').next().unwrap_or("")
        {
            return Err(ArchiveError::BadInput(format!(
                "source store corruption: {key}"
            )));
        }
        let ct = if key.ends_with(".json") {
            "application/json"
        } else if key.ends_with(".txt") {
            "text/plain; charset=utf-8"
        } else {
            "application/octet-stream"
        };
        *counts
            .entry(put_once(dst, &key, &body, ct)?.as_str().to_string())
            .or_insert(0) += 1;
    }
    Ok(counts)
}

#[allow(dead_code)]
fn _exists_marker(_: Exists) {} // Exists is part of the write-once protocol
