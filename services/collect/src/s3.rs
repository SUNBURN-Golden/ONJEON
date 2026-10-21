//! `s3://bucket[/prefix]` store over the S3 REST API (port of `source_archive.S3Store`).
//!
//! Provider rules (unchanged from the reference):
//! - no endpoint: AWS S3 (ap-northeast-2, SSE-S3 header sent);
//! - `https://*.r2.cloudflarestorage.com`: Cloudflare R2 — region `auto`, `R2_*` credentials
//!   only, no SSE header (R2 encrypts at rest and rejects it), and **refuses to build without
//!   an open [`budget::Session`]** (job file + ledger);
//! - any other endpoint: an emulator/local S3-compatible store (the Compose object store,
//!   `tools/tests/s3_stub.py`); no budget required.
//!
//! This crate's transport is plain HTTP only. `https://` endpoints therefore fail at
//! construction *after* the budget check: nothing is sent to AWS or R2 — with or without a
//! job — until a TLS transport lands (post-D-04). Real R2 runs keep using the Python tool.

use std::sync::Arc;

use crate::budget::{Meter, Role};
use crate::digest::sha256_hex;
use crate::http::{parse_endpoint, send, Response};
pub use crate::sigv4::Credentials;
use crate::sigv4::{sign, Request};
use crate::store::{Exists, Store, StoreError, StoredSha};

pub const R2_HOST_SUFFIX: &str = ".r2.cloudflarestorage.com";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Provider {
    Aws,
    R2,
    /// Any other endpoint — the local Compose object store or a test stub.
    Emulator,
}

impl Provider {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Aws => "aws",
            Self::R2 => "r2",
            Self::Emulator => "emulator",
        }
    }
}

/// `provider_of` port: endpoint URL → provider. An R2 host over http is refused outright;
/// a lookalike host (`*.r2.cloudflarestorage.com.evil`) is only an emulator.
pub fn provider_of(endpoint: Option<&str>) -> Result<Provider, StoreError> {
    let ep = match endpoint {
        None | Some("") => return Ok(Provider::Aws),
        Some(e) => e,
    };
    let host = host_of(ep);
    if host.ends_with(R2_HOST_SUFFIX) {
        if !ep.starts_with("https://") {
            return Err(StoreError {
                kind: "endpoint_not_tls",
                message: "R2 endpoint must be https".into(),
            });
        }
        return Ok(Provider::R2);
    }
    Ok(Provider::Emulator)
}

/// Host part of an `http(s)://` URL (no port, no path). Lowercased; "" if unparsable.
fn host_of(url: &str) -> String {
    let rest = url
        .strip_prefix("https://")
        .or_else(|| url.strip_prefix("http://"))
        .unwrap_or("");
    rest.split(['/', '?', '#'])
        .next()
        .unwrap_or("")
        .split('@')
        .next_back()
        .unwrap_or("")
        .split(':')
        .next()
        .unwrap_or("")
        .to_ascii_lowercase()
}

/// The wire one transport sends: a fully signed request.
pub trait S3Transport: Send + Sync {
    fn send(&self, req: &SignedRequest) -> Result<Response, StoreError>;
}

pub struct SignedRequest {
    pub method: &'static str,
    pub path: String,
    pub query: Vec<(String, String)>,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

/// Plain-HTTP transport for `http://host[:port][/base]` endpoints.
pub struct HttpTransport {
    host: String,
    port: u16,
    base: String,
}

impl HttpTransport {
    pub fn new(endpoint: &str) -> Result<Self, StoreError> {
        let (host, port, base) = parse_endpoint(endpoint).map_err(|e| StoreError {
            kind: "bad_endpoint",
            message: format!("bad_endpoint: {}", e.0),
        })?;
        Ok(Self { host, port, base })
    }
}

impl S3Transport for HttpTransport {
    fn send(&self, req: &SignedRequest) -> Result<Response, StoreError> {
        send(
            &self.host,
            self.port,
            &self.base,
            req.method,
            &req.path,
            &req.query,
            &req.headers,
            &req.body,
        )
        .map_err(|e| {
            StoreError::remote(match e.0 {
                "connect" | "resolve" => "connect",
                _ => "io",
            })
        })
    }
}

/// Marker for the "endpoint needs TLS" failure. Constructed (and always failing) for
/// `https://` endpoints, so the gate error is reached before the transport error.
struct NoTlsTransport;

impl S3Transport for NoTlsTransport {
    fn send(&self, _req: &SignedRequest) -> Result<Response, StoreError> {
        Err(StoreError::remote("tls_unsupported"))
    }
}

pub struct S3Store {
    pub bucket: String,
    pub prefix: String,
    pub provider: Provider,
    creds: Credentials,
    transport: Box<dyn S3Transport>,
    /// `Some((meter, role))` on a budgeted store; every call is checked and charged first.
    meter: Option<(Arc<Meter>, Role)>,
    region: &'static str,
    host: String,
}

impl S3Store {
    /// `s3://bucket[/prefix]` + endpoint + credentials. `session` is mandatory for
    /// `aws`/`r2` providers — the acceptance rule "no R2 call without job file and ledger"
    /// is enforced here, before a transport is even selected. `transport` `None` selects
    /// the endpoint-matched transport (plain HTTP for `http://`, the always-failing
    /// `NoTlsTransport` for `https://`).
    pub fn new(
        url: &str,
        endpoint: Option<&str>,
        creds: Credentials,
        session: Option<&crate::budget::Session>,
        transport: Option<Box<dyn S3Transport>>,
    ) -> Result<Self, StoreError> {
        let rest = url.strip_prefix("s3://").ok_or_else(|| StoreError {
            kind: "bad_target",
            message: format!("target must be s3://bucket[/prefix], got {url}"),
        })?;
        let (bucket, prefix) = match rest.split_once('/') {
            Some((b, p)) => (b.to_string(), p.trim_matches('/').to_string()),
            None => (rest.to_string(), String::new()),
        };
        if bucket.is_empty() {
            return Err(StoreError {
                kind: "bad_target",
                message: "s3:// target needs a bucket".into(),
            });
        }
        let provider = provider_of(endpoint)?;
        if matches!(provider, Provider::Aws | Provider::R2) && session.is_none() {
            return Err(StoreError {
                kind: "budget_required",
                message: format!(
                    "{} access needs a budget job (--job infra/r2/jobs/<job>.json); nothing was sent",
                    provider.as_str()
                ),
            });
        }
        let host = if provider == Provider::Emulator {
            let (host, port, base) = parse_endpoint(endpoint.unwrap_or(""))
                .map_err(|_| StoreError::remote("bad_endpoint"))?;
            if !matches!(host.as_str(), "localhost" | "127.0.0.1") || !base.is_empty() {
                return Err(StoreError::remote("local_endpoint_required"));
            }
            format!("{host}:{port}")
        } else {
            host_of(endpoint.unwrap_or(""))
        };
        let transport: Box<dyn S3Transport> = match transport {
            Some(t) => t,
            None => match endpoint {
                Some(e) if e.starts_with("http://") => Box::new(HttpTransport::new(e)?),
                _ => Box::new(NoTlsTransport),
            },
        };
        Ok(Self {
            bucket,
            prefix,
            provider,
            host,
            creds,
            transport,
            meter: session.map(|s| (s.meter(), Role::Archive)),
            region: match provider {
                Provider::R2 => "auto",
                _ => "ap-northeast-2",
            },
        })
    }

    /// Test/extension entry: same gate, explicit transport.
    pub fn with_transport(
        url: &str,
        endpoint: Option<&str>,
        creds: Credentials,
        session: Option<&crate::budget::Session>,
        transport: Box<dyn S3Transport>,
    ) -> Result<Self, StoreError> {
        Self::new(url, endpoint, creds, session, Some(transport))
    }

    /// Same store shape for the ledger bucket (role `ledger`, own credentials). Still
    /// bound by the provider gate — the ledger bucket lives on the same R2 account.
    pub fn ledger(
        url: &str,
        endpoint: Option<&str>,
        creds: Credentials,
        session: &crate::budget::Session,
        transport: Option<Box<dyn S3Transport>>,
    ) -> Result<Self, StoreError> {
        let mut s = Self::new(url, endpoint, creds, Some(session), transport)?;
        s.meter = Some((session.meter(), Role::Ledger));
        Ok(s)
    }

    fn key(&self, key: &str) -> String {
        if self.prefix.is_empty() {
            key.to_string()
        } else {
            format!("{}/{}", self.prefix, key)
        }
    }

    /// One S3 call: meter `check_call` before the request exists, `on_send` per attempt
    /// (this transport makes exactly one attempt — a failure is an error, not a retry).
    fn call(
        &self,
        op: &'static str,
        key: Option<&str>,
        query: Vec<(String, String)>,
        extra_headers: Vec<(String, String)>,
        body: &[u8],
    ) -> Result<Response, StoreError> {
        if let Some((m, role)) = &self.meter {
            m.check_call(
                op,
                *role,
                &self.bucket,
                key,
                if op == "PutObject" { Some(body) } else { None },
            )
            .map_err(|e| StoreError {
                kind: "budget",
                message: e.to_string(),
            })?;
        }
        let payload_sha = sha256_hex(body);
        let mut headers = vec![
            ("content-length".to_string(), body.len().to_string()),
            ("host".to_string(), self.host.clone()),
        ];
        headers.extend(extra_headers);
        let mut req = Request {
            method: match op {
                "PutObject" => "PUT",
                "HeadObject" => "HEAD",
                _ => "GET",
            },
            path: match key {
                Some(k) => format!("/{}/{}", self.bucket, self.key(k)),
                None => format!("/{}", self.bucket),
            },
            query,
            headers,
            body: body.to_vec(),
        };
        sign(
            &mut req,
            &self.creds,
            self.region,
            &payload_sha,
            crate::time::now_secs(),
        );
        if let Some((m, _)) = &self.meter {
            m.on_send(req.body.len() as u64).map_err(|e| StoreError {
                kind: "budget",
                message: e.to_string(),
            })?;
        }
        let resp = self.transport.send(&SignedRequest {
            method: req.method,
            path: req.path,
            query: req.query,
            headers: req.headers,
            body: req.body,
        })?;
        if (400..=599).contains(&resp.status) {
            return Err(self.s3_error(&resp));
        }
        Ok(resp)
    }

    /// Map an S3 error response to a typed error. The upstream `<Message>` is never echoed
    /// (it can carry the endpoint / account id); only the `<Code>` or the status is kept.
    fn s3_error(&self, r: &Response) -> StoreError {
        let code = crate::s3xml::text(std::str::from_utf8(&r.body).unwrap_or(""), "Code");
        match (r.status, code.as_deref()) {
            (404, _) | (_, Some("NoSuchKey") | Some("NotFound")) => StoreError::remote("not_found"),
            (412, _) | (_, Some("PreconditionFailed") | Some("ConditionalRequestConflict")) => {
                StoreError::remote("precondition_failed")
            }
            _ => StoreError {
                kind: "s3_status",
                message: format!("s3 status {}", r.status),
            },
        }
    }
}

impl Store for S3Store {
    fn put_new(&self, key: &str, body: &[u8], content_type: &str) -> Result<(), StoreError> {
        use sha2::Digest;
        let mut headers = vec![
            ("content-type".to_string(), content_type.to_string()),
            // never overwrite (AWS: the bucket policy also denies writes without it)
            ("if-none-match".to_string(), "*".to_string()),
            (
                "x-amz-checksum-sha256".to_string(),
                crate::sigv4::b64(&sha2::Sha256::digest(body)),
            ),
        ];
        if self.provider == Provider::Aws {
            // R2 encrypts at rest itself and rejects this header.
            headers.push(("x-amz-server-side-encryption".into(), "AES256".into()));
        }
        match self.call("PutObject", Some(key), vec![], headers, body) {
            Ok(_) => Ok(()),
            Err(e) if e.kind == "precondition_failed" => Err(Exists(key.into()).into()),
            Err(e) => Err(e),
        }
    }

    fn get(&self, key: &str) -> Result<Vec<u8>, StoreError> {
        let r = self.call("GetObject", Some(key), vec![], vec![], &[])?;
        if let Some((m, _)) = &self.meter {
            let n = r
                .header("content-length")
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(0);
            m.charge_get_bytes(n).map_err(|e| StoreError {
                kind: "budget",
                message: e.to_string(),
            })?;
        }
        Ok(r.body)
    }

    fn stored_sha256(&self, key: &str) -> Result<StoredSha, StoreError> {
        match self.call(
            "HeadObject",
            Some(key),
            vec![],
            vec![("x-amz-checksum-mode".into(), "ENABLED".into())],
            &[],
        ) {
            Ok(r) => match r.header("x-amz-checksum-sha256") {
                Some(v) if !v.contains('-') => {
                    let raw = base64_decode(v).ok_or_else(|| StoreError {
                        kind: "bad_checksum",
                        message: "head checksum header not base64".into(),
                    })?;
                    if raw.len() != 32 {
                        return Err(StoreError::remote("bad_checksum"));
                    }
                    Ok(StoredSha::Sha(crate::digest::hex(&raw)))
                }
                _ => Ok(StoredSha::NoChecksum),
            },
            Err(e) if e.kind == "not_found" => Ok(StoredSha::Absent),
            Err(e) => Err(e),
        }
    }

    fn exists(&self, key: &str) -> Result<bool, StoreError> {
        match self.call("HeadObject", Some(key), vec![], vec![], &[]) {
            Ok(_) => Ok(true),
            Err(e) if e.kind == "not_found" => Ok(false),
            Err(e) => Err(e),
        }
    }

    fn list(&self, prefix: &str) -> Result<Vec<String>, StoreError> {
        let mut out = Vec::new();
        let mut token: Option<String> = None;
        loop {
            let mut q = vec![
                ("list-type".to_string(), "2".to_string()),
                ("prefix".to_string(), self.key(prefix)),
            ];
            if let Some(t) = &token {
                q.push(("continuation-token".into(), t.clone()));
            }
            let r = self.call("ListObjectsV2", None, q, vec![], &[])?;
            let xml = String::from_utf8_lossy(&r.body);
            for mut k in crate::s3xml::texts(&xml, "Key") {
                if !self.prefix.is_empty() {
                    k = k
                        .strip_prefix(&format!("{}/", self.prefix))
                        .unwrap_or(&k)
                        .to_string();
                }
                out.push(k);
            }
            if crate::s3xml::text(&xml, "IsTruncated").as_deref() != Some("true") {
                out.sort();
                return Ok(out);
            }
            token = crate::s3xml::text(&xml, "NextContinuationToken");
            if token.is_none() {
                return Err(StoreError::remote("bad_list_response"));
            }
        }
    }

    fn describe(&self) -> String {
        format!(
            "{}:{}{}",
            self.provider.as_str(),
            self.bucket,
            if self.prefix.is_empty() {
                String::new()
            } else {
                format!("/{}", self.prefix)
            }
        )
    }
}

fn base64_decode(s: &str) -> Option<Vec<u8>> {
    let mut out = Vec::new();
    let mut acc = 0u32;
    let mut bits = 0u32;
    for c in s.bytes() {
        let v = match c {
            b'A'..=b'Z' => c - b'A',
            b'a'..=b'z' => c - b'a' + 26,
            b'0'..=b'9' => c - b'0' + 52,
            b'+' => 62,
            b'/' => 63,
            b'=' => break,
            _ => return None,
        };
        acc = (acc << 6) | v as u32;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((acc >> bits) as u8);
        }
    }
    Some(out)
}

/// `file://` → [`LocalStore`], `s3://` → [`S3Store`] (provider gate applies).
/// `session` is required for aws/r2 targets; ignored for file:// and emulator targets.
pub fn open(
    target: &str,
    endpoint: Option<&str>,
    creds: Option<Credentials>,
    session: Option<&crate::budget::Session>,
) -> Result<Box<dyn Store>, StoreError> {
    if let Some(dir) = target.strip_prefix("file://") {
        return Ok(Box::new(crate::store::LocalStore::new(dir)));
    }
    if target.starts_with("s3://") {
        let creds = creds.ok_or_else(|| StoreError {
            kind: "no_credentials",
            message: "s3:// target needs credentials".into(),
        })?;
        return Ok(Box::new(S3Store::new(
            target, endpoint, creds, session, None,
        )?));
    }
    Err(StoreError {
        kind: "bad_target",
        message: format!("target must be file:///dir or s3://bucket[/prefix], got {target}"),
    })
}
