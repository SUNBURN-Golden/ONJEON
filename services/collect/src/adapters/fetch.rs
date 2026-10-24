//! Injected transport for denominator enumeration (T-DT-04).
//!
//! The same contract `tools/crawler/transport.py` imposes on the Python crawler: a `Fetch`
//! implementation performs one GET, never follows redirects (a 3xx comes back as a response
//! and the caller validates the target), reads at most `max_bytes` of body, and reports
//! errors as kinds only. Callers never see upstream messages — they can carry the endpoint.
//!
//! This crate ships no network implementation of `Fetch`: enumeration runs against an
//! injected transport (tests use fixture responses; a live run plugs in the crawler
//! transport once the execution environment exists — D-04/O17).

/// One GET response. `headers` are lowercased names; `truncated` is true when the body hit
/// `max_bytes` — a truncated body is not a full document and must not be parsed as one.
#[derive(Debug, Clone)]
pub struct FetchResponse {
    pub status: u16,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
    pub truncated: bool,
}

impl FetchResponse {
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|(k, _)| k == name)
            .map(|(_, v)| v.as_str())
    }
}

/// Fetch failure kinds. Kinds only — never the upstream message, never the endpoint.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FetchError {
    /// Connect, TLS, read, timeout — anything before a complete response.
    Network,
    /// Declared or actual length exceeded `max_bytes` before the body completed.
    TooLarge,
    /// The transport refused the request before opening a socket (e.g. network disabled).
    Refused,
    /// The URL itself was rejected (bad scheme, credentials, unparseable).
    BadUrl,
}

impl std::fmt::Display for FetchError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let kind = match self {
            Self::Network => "network",
            Self::TooLarge => "too_large",
            Self::Refused => "refused",
            Self::BadUrl => "bad_url",
        };
        write!(f, "fetch error: {kind}")
    }
}
impl std::error::Error for FetchError {}

/// The transport injected into every adapter. Implementations identify themselves to the
/// remote host with the configured honest User-Agent; rotation is not part of this trait.
pub trait Fetch {
    /// GET `url`, reading at most `max_bytes` of body. Must not follow redirects: a 3xx is
    /// returned as a normal `FetchResponse` so the caller can validate the target itself.
    fn fetch(&self, url: &str, max_bytes: usize) -> Result<FetchResponse, FetchError>;
}

/// `(scheme, host, port, path_with_query)` for absolute http(s) URLs. Credentials are
/// refused the same way the Python transport refuses them.
pub fn split_url(url: &str) -> Result<(&str, &str, u16, &str), FetchError> {
    let (scheme, rest) = url.split_once("://").ok_or(FetchError::BadUrl)?;
    if scheme != "http" && scheme != "https" {
        return Err(FetchError::BadUrl);
    }
    let (authority, path) = match rest.find('/') {
        Some(i) => (&rest[..i], &rest[i..]),
        None => (rest, "/"),
    };
    if authority.is_empty() || authority.contains('@') {
        return Err(FetchError::BadUrl);
    }
    let (host, port) = if let Some(b) = authority.strip_prefix('[') {
        let (h, p) = b.split_once(']').ok_or(FetchError::BadUrl)?;
        let port = match p.strip_prefix(':') {
            Some(p) => p.parse::<u16>().map_err(|_| FetchError::BadUrl)?,
            None if p.is_empty() => default_port(scheme),
            None => return Err(FetchError::BadUrl),
        };
        (h, port)
    } else {
        match authority.split_once(':') {
            Some((h, p)) => (h, p.parse::<u16>().map_err(|_| FetchError::BadUrl)?),
            None => (authority, default_port(scheme)),
        }
    };
    if host.is_empty() {
        return Err(FetchError::BadUrl);
    }
    Ok((scheme, host, port, path))
}

fn default_port(scheme: &str) -> u16 {
    if scheme == "https" {
        443
    } else {
        80
    }
}
