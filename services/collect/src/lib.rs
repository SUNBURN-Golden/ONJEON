//! Source preservation client (T-DT-01, DATA_PIPELINE_CONTRACT §3.1, ADR-0015/0016/0017).
//!
//! Port of `tools/source_archive.py` to Rust, keeping the same on-disk / on-wire layout so a
//! store written by one tool verifies byte-for-byte with the other:
//!
//! ```text
//! objects/sha256/<aa>/<bb>/<sha256>                    immutable original, key = SHA-256 of bytes
//! observations/<source_id>/<stamp>_<sha256[:16]>.json  one record per fetch
//! quarantine/<source_id>/<stamp>_<sha256[:16]>/        a fetched response that failed format
//!                                                      validation: bytes + record, never an
//!                                                      `objects/` original, never `archived`
//! unacquired/<source_id>/<stamp>_<sha256[:16]>.json    an expected document that could not be
//!                                                      secured, with its reason (09 P02·P03:
//!                                                      an unacquired document is recorded apart
//!                                                      and is not counted as acquired)
//! ```
//!
//! Rules enforced by the client (see `infra/r2/` for the Cloudflare R2 storage controls):
//! - a key is written once; an existing key is never overwritten (`If-None-Match: *` on S3,
//!   an atomic link on `file://`). Re-archiving identical bytes is a verified no-op.
//! - a changed document at the same URL is a new object plus a new observation; the old
//!   object and its observations stay.
//! - there is no delete operation in this crate.
//! - personal policy, health, family history or DNA data never enter these stores.
//!
//! Targets: `file:///abs/dir` or `s3://bucket[/prefix]`. S3-compatible endpoints speak the
//! S3 REST API over plain HTTP (the local Compose object store and test emulators).
//! Remote calls are disabled in this crate. Its budget session has no public constructor and
//! its archive store supports only loopback HTTP. Budgeted R2 runs use the Python tool.

pub mod archive;
pub mod budget;
pub mod digest;
pub mod format;
pub mod http;
pub mod keys;
pub mod s3;
pub mod s3xml;
pub mod sigv4;
pub mod store;
pub mod time;

pub use archive::{
    content_type_of, observe, put_once, put_quarantined, put_raw, record_unacquired, verify_copy,
    Conflict, Listing, Observation, PutOutcome, QuarantineOutcome, UnacquiredRecord, VerifyReport,
    VerifyStatus,
};
pub use store::{Exists, LocalStore, S3Store, Store, StoreError};
