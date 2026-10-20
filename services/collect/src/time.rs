//! UTC timestamps without a date library: RFC 3339 stamps and SigV4 dates, plus the
//! `YYYY-MM` month key the budget ledger is bucketed by.

use std::time::{SystemTime, UNIX_EPOCH};

/// Civil date/time from days-since-epoch + seconds-of-day (Howard Hinnant's algorithm).
fn civil(days: i64) -> (i64, u32, u32) {
    let z = days + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = (z - era * 146_097) as u64; // [0, 146096]
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146_096) / 365; // [0, 399]
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100); // [0, 365]
    let mp = (5 * doy + 2) / 153; // [0, 11]
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32; // [1, 31]
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32; // [1, 12]
    (y + (m <= 2) as i64, m, d)
}

/// Broken-down UTC time for `secs` since the unix epoch.
pub fn utc(secs: u64) -> (i64, u32, u32, u32, u32, u32) {
    let days = (secs / 86_400) as i64;
    let rem = (secs % 86_400) as u32;
    let (y, m, d) = civil(days);
    (y, m, d, rem / 3600, rem % 3600 / 60, rem % 60)
}

/// `YYYY-MM-DDTHH:MM:SSZ` for `secs` since the epoch.
pub fn rfc3339(secs: u64) -> String {
    let (y, m, d, hh, mm, ss) = utc(secs);
    format!("{y:04}-{m:02}-{d:02}T{hh:02}:{mm:02}:{ss:02}Z")
}

/// `YYYYMMDDTHHMMSSZ` (SigV4) for `secs` since the epoch.
pub fn sigv4_stamp(secs: u64) -> (String, String) {
    let (y, m, d, hh, mm, ss) = utc(secs);
    (
        format!("{y:04}{m:02}{d:02}T{hh:02}{mm:02}{ss:02}Z"),
        format!("{y:04}{m:02}{d:02}"),
    )
}

/// `YYYY-MM` for `secs` since the epoch.
pub fn month_of_secs(secs: u64) -> String {
    let (y, m, ..) = utc(secs);
    format!("{y:04}-{m:02}")
}

/// `YYYY-MM` from an RFC 3339 timestamp string (the Python `month_of`).
pub fn month_of(ts: &str) -> &str {
    &ts[..7.min(ts.len())]
}

/// Seconds since the unix epoch.
pub fn now_secs() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// `YYYY-MM-DDTHH:MM:SSZ` now.
pub fn stamp() -> String {
    rfc3339(now_secs())
}

/// A run id like the Python one: `<stamp>-<8 hex>`. The suffix comes from a random source
/// when available, else from the address of a stack slot and the time — it only has to be
/// unique per run on one machine.
pub fn run_id() -> String {
    let mut seed = [0u8; 8];
    let seed_ok = std::fs::File::open("/dev/urandom")
        .and_then(|mut f| {
            use std::io::Read;
            f.read_exact(&mut seed)
        })
        .is_ok();
    let suffix = if seed_ok {
        u64::from_be_bytes(seed)
    } else {
        now_secs().wrapping_mul(0x9E37_79B9_7F4A_7C15) ^ std::process::id() as u64
    };
    format!("{}-{:08x}", stamp(), suffix as u32)
}
