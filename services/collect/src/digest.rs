//! SHA-256 helpers (sha2). The archive keys objects by the hex digest of their bytes.

use sha2::{Digest, Sha256};

/// Lowercase hex SHA-256 of `body` (64 chars).
pub fn sha256_hex(body: &[u8]) -> String {
    let mut h = Sha256::new();
    h.update(body);
    hex(&h.finalize())
}

/// Lowercase hex of raw digest bytes.
pub fn hex(bytes: &[u8]) -> String {
    const D: &[u8; 16] = b"0123456789abcdef";
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        s.push(D[(b >> 4) as usize] as char);
        s.push(D[(b & 0xf) as usize] as char);
    }
    s
}

/// SHA-256 of a file's bytes.
pub fn sha256_file(path: &std::path::Path) -> std::io::Result<String> {
    Ok(sha256_hex(&std::fs::read(path)?))
}
