//! Minimal HTTP/1.1 client over `std::net::TcpStream` — plain HTTP only. The archive uses it
//! for S3-compatible endpoints on `http://` (the local Compose object store, test emulators).
//! `https://` is refused: TLS is not built into this crate, and the only TLS endpoint the
//! design names is R2, whose calls wait on D-04 anyway.
//!
//! Errors carry the kind only (`connect`, `io`, `status`, `bad_response`); upstream messages
//! can embed the endpoint, and the endpoint can identify an account — never echoed.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpStream;
use std::time::Duration;

pub const CONNECT_TIMEOUT: Duration = Duration::from_secs(10);
pub const READ_TIMEOUT: Duration = Duration::from_secs(120); // same values as r2_budget.py

#[derive(Debug)]
pub struct Response {
    pub status: u16,
    pub headers: Vec<(String, String)>, // lowercased names
    pub body: Vec<u8>,
}

impl Response {
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|(k, _)| k == name)
            .map(|(_, v)| v.as_str())
    }
}

#[derive(Debug)]
pub struct HttpError(pub &'static str);

impl std::fmt::Display for HttpError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "http error: {}", self.0)
    }
}
impl std::error::Error for HttpError {}

/// Split `http://host[:port][/base]` into (host, port, base path). Refuses https and
/// anything with userinfo, query or fragment — this client only ever talks to a store.
pub fn parse_endpoint(endpoint: &str) -> Result<(String, u16, String), HttpError> {
    let rest = endpoint
        .strip_prefix("http://")
        .ok_or(HttpError("endpoint must be http://"))?;
    let rest = rest.trim_end_matches('/');
    let (authority, base) = match rest.split_once('/') {
        Some((a, b)) => (a, format!("/{b}")),
        None => (rest, String::new()),
    };
    if authority.is_empty() || authority.contains('@') || authority.contains('?') {
        return Err(HttpError("bad authority"));
    }
    let (host, port) = match authority.split_once(':') {
        Some((h, p)) => (h.to_string(), p.parse().map_err(|_| HttpError("bad port"))?),
        None => (authority.to_string(), 80),
    };
    Ok((host, port, base))
}

/// Send one request; reads Content-Length or chunked bodies. `req` is a signed sigv4::Request
/// plus the Host already set. Returns the response; non-2xx is a normal `Response`, not an error.
#[allow(clippy::too_many_arguments)]
pub fn send(
    host: &str,
    port: u16,
    base: &str,
    method: &str,
    path: &str,
    query: &[(String, String)],
    headers: &[(String, String)],
    body: &[u8],
) -> Result<Response, HttpError> {
    let addr = format!("{host}:{port}");
    let resolved = if let Ok(a) = addr.parse::<std::net::SocketAddr>() {
        a
    } else {
        use std::net::ToSocketAddrs;
        addr.to_socket_addrs()
            .ok()
            .and_then(|mut it| it.next())
            .ok_or(HttpError("resolve"))?
    };
    let mut sock =
        TcpStream::connect_timeout(&resolved, CONNECT_TIMEOUT).map_err(|_| HttpError("connect"))?;
    sock.set_read_timeout(Some(READ_TIMEOUT)).ok();
    sock.set_write_timeout(Some(CONNECT_TIMEOUT)).ok();

    let mut target = format!("{base}{}", crate::sigv4::uri_encode_path(path));
    if !query.is_empty() {
        target.push('?');
        target.push_str(
            &query
                .iter()
                .map(|(k, v)| {
                    format!(
                        "{}={}",
                        crate::sigv4::uri_encode(k),
                        crate::sigv4::uri_encode(v)
                    )
                })
                .collect::<Vec<_>>()
                .join("&"),
        );
    }
    let mut head =
        format!("{method} {target} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n");
    for (k, v) in headers {
        if k.contains(['\r', '\n']) || v.contains(['\r', '\n']) {
            return Err(HttpError("bad_request_header"));
        }
        if !k.eq_ignore_ascii_case("host") {
            head.push_str(&format!("{k}: {v}\r\n"));
        }
    }
    head.push_str("\r\n");
    sock.write_all(head.as_bytes())
        .and_then(|_| sock.write_all(body))
        .map_err(|_| HttpError("send"))?;

    let mut r = BufReader::new(sock);
    let mut line = String::new();
    r.read_line(&mut line).map_err(|_| HttpError("io"))?;
    let status: u16 = line
        .split_whitespace()
        .nth(1)
        .and_then(|s| s.parse().ok())
        .ok_or(HttpError("bad_status_line"))?;
    let mut hdrs = Vec::new();
    let mut chunked = false;
    let mut len = None;
    loop {
        line.clear();
        r.read_line(&mut line).map_err(|_| HttpError("io"))?;
        let t = line.trim();
        if t.is_empty() {
            break;
        }
        let (k, v) = t.split_once(':').ok_or(HttpError("bad_header"))?;
        let (k, v) = (k.trim().to_ascii_lowercase(), v.trim().to_string());
        if k == "transfer-encoding" && v.contains("chunked") {
            chunked = true;
        }
        if k == "content-length" {
            len = v.parse().ok();
        }
        hdrs.push((k, v));
    }
    let body = if method == "HEAD" || status == 204 || status == 304 {
        Vec::new()
    } else if chunked {
        read_chunked(&mut r)?
    } else if let Some(n) = len {
        let mut b = vec![0u8; n];
        r.read_exact(&mut b).map_err(|_| HttpError("io"))?;
        b
    } else {
        let mut b = Vec::new();
        r.read_to_end(&mut b).map_err(|_| HttpError("io"))?;
        b
    };
    Ok(Response {
        status,
        headers: hdrs,
        body,
    })
}

fn read_chunked(r: &mut BufReader<TcpStream>) -> Result<Vec<u8>, HttpError> {
    let mut out = Vec::new();
    loop {
        let mut line = String::new();
        r.read_line(&mut line).map_err(|_| HttpError("io"))?;
        let n = usize::from_str_radix(line.trim().split(';').next().unwrap_or(""), 16)
            .map_err(|_| HttpError("bad_chunk"))?;
        if n == 0 {
            let mut t = String::new();
            r.read_line(&mut t).map_err(|_| HttpError("io"))?;
            break;
        }
        let mut buf = vec![0u8; n];
        r.read_exact(&mut buf).map_err(|_| HttpError("io"))?;
        out.extend_from_slice(&buf);
        let mut crlf = [0u8; 2];
        r.read_exact(&mut crlf).map_err(|_| HttpError("io"))?;
    }
    Ok(out)
}
