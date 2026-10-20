//! AWS Signature V4 for the S3 REST calls this crate makes, with the small primitives it
//! needs (HMAC-SHA256, base64, URI encoding) so the crate keeps its minimal dependency set.
//! HMAC is exercised against the RFC 4231 vectors and signing against the AWS documentation
//! example in `tests`.

use sha2::{Digest, Sha256};

/// HMAC-SHA256(key, msg) — RFC 2104.
pub fn hmac_sha256(key: &[u8], msg: &[u8]) -> [u8; 32] {
    let mut k = [0u8; 64];
    if key.len() > 64 {
        k[..32].copy_from_slice(&Sha256::digest(key));
    } else {
        k[..key.len()].copy_from_slice(key);
    }
    let mut inner = Sha256::new();
    for b in k.iter() {
        inner.update([b ^ 0x36]);
    }
    inner.update(msg);
    let inner = inner.finalize();
    let mut outer = Sha256::new();
    for b in k.iter() {
        outer.update([b ^ 0x5c]);
    }
    outer.update(inner);
    outer.finalize().into()
}

/// Standard base64 (for `x-amz-checksum-sha256`).
pub fn b64(data: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::new();
    for c in data.chunks(3) {
        let n = ((c[0] as u32) << 16)
            | ((*c.get(1).unwrap_or(&0) as u32) << 8)
            | *c.get(2).unwrap_or(&0) as u32;
        out.push(T[(n >> 18) as usize & 63] as char);
        out.push(T[(n >> 12) as usize & 63] as char);
        out.push(if c.len() > 1 {
            T[(n >> 6) as usize & 63] as char
        } else {
            '='
        });
        out.push(if c.len() > 2 {
            T[n as usize & 63] as char
        } else {
            '='
        });
    }
    out
}

/// RFC 3986 unreserved-only percent encoding (SigV4 canonical form).
pub fn uri_encode(s: &str) -> String {
    let mut out = String::new();
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(b as char)
            }
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

/// Encode each path segment separately, keeping `/` separators.
pub fn uri_encode_path(path: &str) -> String {
    path.split('/')
        .map(uri_encode)
        .collect::<Vec<_>>()
        .join("/")
}

/// One HTTP request to sign. `headers` are lowercased names with values; `body` is the
/// exact bytes sent.
pub struct Request {
    pub method: &'static str,
    /// `/bucket/key` path-style, unencoded.
    pub path: String,
    /// Sorted query parameters, unencoded.
    pub query: Vec<(String, String)>,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

pub struct Credentials {
    pub access_key: String,
    pub secret_key: String,
}

/// Add the SigV4 headers (`x-amz-date`, `x-amz-content-sha256`, `authorization`) to `req`.
/// `host` must already be in `req.headers`; `payload_sha256` is the hex digest of `body`.
pub fn sign(req: &mut Request, creds: &Credentials, region: &str, payload_sha256: &str, now: u64) {
    let (amz_date, date) = crate::time::sigv4_stamp(now);
    req.headers.push(("x-amz-date".into(), amz_date.clone()));
    req.headers
        .push(("x-amz-content-sha256".into(), payload_sha256.into()));
    req.headers.sort_by(|a, b| a.0.cmp(&b.0));

    let signed: Vec<&str> = req.headers.iter().map(|(k, _)| k.as_str()).collect();
    let canonical_headers: String = req
        .headers
        .iter()
        .map(|(k, v)| {
            format!(
                "{}:{}\n",
                k,
                v.split_whitespace().collect::<Vec<_>>().join(" ")
            )
        })
        .collect();
    let mut query: Vec<String> = req
        .query
        .iter()
        .map(|(k, v)| format!("{}={}", uri_encode(k), uri_encode(v)))
        .collect();
    query.sort();
    let canonical = format!(
        "{}\n{}\n{}\n{}\n{}\n{}",
        req.method,
        uri_encode_path(&req.path),
        query.join("&"),
        canonical_headers,
        signed.join(";"),
        payload_sha256
    );
    let scope = format!("{date}/{region}/s3/aws4_request");
    let to_sign = format!(
        "AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{}",
        crate::digest::sha256_hex(canonical.as_bytes())
    );
    let mut key = hmac_sha256(
        format!("AWS4{}", creds.secret_key).as_bytes(),
        date.as_bytes(),
    );
    for part in [region.as_bytes(), b"s3", b"aws4_request"] {
        key = hmac_sha256(&key, part);
    }
    let signature = crate::digest::hex(&hmac_sha256(&key, to_sign.as_bytes()));
    req.headers.push((
        "authorization".into(),
        format!(
            "AWS4-HMAC-SHA256 Credential={}/{scope}, SignedHeaders={}, Signature={signature}",
            creds.access_key,
            signed.join(";")
        ),
    ));
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::digest::hex;

    #[test]
    fn archive_hmac_matches_rfc4231() {
        // RFC 4231 test case 2.
        let got = hmac_sha256(b"Jefe", b"what do ya want for nothing?");
        assert_eq!(
            hex(&got),
            "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"
        );
        // Test case 6: key longer than the block size.
        let got = hmac_sha256(
            &[0xaa; 131],
            b"Test Using Larger Than Block-Size Key - Hash Key First",
        );
        assert_eq!(
            hex(&got),
            "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54"
        );
    }

    #[test]
    fn archive_sigv4_matches_aws_example() {
        // The S3 example of the SigV4 documentation suite (get-bucket on
        // examplebucket with AKIDEXAMPLE), fixed clock 20130524T000000Z.
        let mut req = Request {
            method: "GET",
            path: "/".into(),
            query: vec![
                ("max-keys".into(), "2".into()),
                ("prefix".into(), "J".into()),
            ],
            headers: vec![("host".into(), "examplebucket.s3.amazonaws.com".into())],
            body: vec![],
        };
        let creds = Credentials {
            access_key: "AKIDEXAMPLE".into(),
            secret_key: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY".into(),
        };
        sign(
            &mut req,
            &creds,
            "us-east-1",
            &crate::digest::sha256_hex(b""),
            1_369_353_600,
        );
        let auth = req
            .headers
            .iter()
            .find(|(k, _)| k == "authorization")
            .map(|(_, v)| v.as_str())
            .unwrap();
        assert!(auth.contains(
            "Signature=34b48302e7b5fa45bde8084f4b7868a86f0a534bc59db6670ed5711ef69dc6f7"
        ));
    }

    #[test]
    fn archive_b64() {
        assert_eq!(b64(b""), "");
        assert_eq!(b64(b"f"), "Zg==");
        assert_eq!(b64(b"foobar"), "Zm9vYmFy");
    }
}
