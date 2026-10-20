//! robots.txt policy for enumeration — the Rust port of `tools/crawler/robots.py` semantics.
//!
//! Outcomes per host (RFC 9309 plus the project rule "when in doubt, do not fetch"):
//!
//! - 2xx robots.txt: parse; Allow/Disallow honoured for the product token; the longest
//!   matching rule wins, Allow wins a tie, `*` and a trailing `$` work.
//! - 4xx other than 401/403/429: no robots.txt → every path allowed.
//! - 401/403: host `Blocked` (`robots_forbidden`), deferred for the rest of the UTC day.
//! - 429, 5xx, network error, over-cap body without a full line, bad/cross-host redirect:
//!   host `Unverifiable` — **deferred, never fetched meanwhile** (the "robots 확인 불가
//!   호스트는 보류" rule). Deferral lasts until the end of the UTC day, as in Python.
//! - A transport `Refused` (no socket opened, e.g. network disabled) is recorded as
//!   `transport_refused` — the refusal is ours, not the host's — and still defers.
//!   The Python port raises `NetworkDisabledError`; the deferred hold is the
//!   fail-soft equivalent for an injected transport.
//!
//! Verdicts feed the manifest's `blocked`/`hold` ranges; an unverifiable host's scopes stay
//! unexplored with their hold reason — they are never counted as enumerated or acquired.

use std::collections::HashMap;

use super::fetch::{split_url, Fetch, FetchError};

/// RFC 9309: parse at least the first 500 KiB.
pub const ROBOTS_MAX_BYTES: usize = 512 * 1024;
const MAX_REDIRECTS: usize = 5;
const DAY_S: u64 = 86_400;

/// The bot token robots groups are matched against (`tools/crawler/useragent.py`).
pub const PRODUCT_TOKEN: &str = "ONJEON-SourceArchiver";

/// What robots.txt tells us for one URL.
#[derive(Debug, Clone, PartialEq)]
pub enum RobotsVerdict {
    /// Fetching is permitted (`reason`: `ok` or `robots_not_found`).
    Allow {
        reason: &'static str,
        crawl_delay: Option<f64>,
    },
    /// A Disallow rule covers the path (`robots_disallow`).
    Disallow,
    /// robots.txt could not be checked: the host is on hold for the rest of the UTC day.
    /// Reason: `robots_unreachable` | `robots_server_error` | `robots_rate_limited` |
    /// `robots_too_large` | `robots_redirect_refused` | `transport_refused` | `bad_url`.
    Unverifiable { reason: &'static str },
    /// robots.txt itself answered 401/403 (`robots_forbidden`): the host is blocked.
    Forbidden,
}

impl RobotsVerdict {
    /// `true` when the URL may be fetched under the robots rules.
    pub fn allowed(&self) -> bool {
        matches!(self, Self::Allow { .. })
    }
}

#[derive(Debug)]
struct Entry {
    fetched_at: u64,
    /// None => no robots.txt (other 4xx): allow all.
    rules: Option<Group>,
    crawl_delay: Option<f64>,
    reason: &'static str,
}

/// robots.txt fetch + cache + per-host deferral. Not a rate limiter.
pub struct RobotsGate {
    ttl_s: u64,
    entries: HashMap<(String, String, u16), Entry>,
    /// host -> (deferred_until, reason, forbidden)
    deferred: HashMap<String, (u64, &'static str, bool)>,
}

impl RobotsGate {
    pub fn new(ttl_s: u64) -> Self {
        Self {
            ttl_s,
            entries: HashMap::new(),
            deferred: HashMap::new(),
        }
    }

    /// May we fetch `url` at `now` (epoch seconds)? Fetches robots.txt once per origin per
    /// TTL through `fetch`. A deferred host answers without any request.
    pub fn check(&mut self, fetch: &dyn Fetch, url: &str, now: u64) -> RobotsVerdict {
        let (scheme, host, port, path) = match split_url(url) {
            Ok(p) => p,
            Err(_) => return RobotsVerdict::Unverifiable { reason: "bad_url" },
        };
        let host = host.to_ascii_lowercase();
        if let Some(v) = self.deferral(&host, now) {
            return v;
        }
        let origin = (scheme.to_string(), host.clone(), port);
        let stale = self
            .entries
            .get(&origin)
            .map(|e| now.saturating_sub(e.fetched_at) >= self.ttl_s)
            .unwrap_or(true);
        if stale && self.fetch_entry(scheme, &host, port, fetch, now).is_none() {
            return self
                .deferral(&host, now)
                .unwrap_or(RobotsVerdict::Unverifiable {
                    reason: "robots_unreachable",
                });
        }
        match self.entries.get(&origin) {
            Some(Entry {
                rules: None,
                reason,
                ..
            }) => RobotsVerdict::Allow {
                reason,
                crawl_delay: None,
            },
            Some(Entry {
                rules: Some(g),
                crawl_delay,
                ..
            }) => {
                if can_fetch(g, path) {
                    RobotsVerdict::Allow {
                        reason: "ok",
                        crawl_delay: *crawl_delay,
                    }
                } else {
                    RobotsVerdict::Disallow
                }
            }
            None => RobotsVerdict::Unverifiable {
                reason: "robots_unreachable",
            },
        }
    }

    fn deferral(&mut self, host: &str, now: u64) -> Option<RobotsVerdict> {
        let (until, reason, forbidden) = *self.deferred.get(host)?;
        if now >= until {
            self.deferred.remove(host);
            return None;
        }
        Some(if forbidden {
            RobotsVerdict::Forbidden
        } else {
            RobotsVerdict::Unverifiable { reason }
        })
    }

    fn defer(&mut self, host: &str, now: u64, reason: &'static str, forbidden: bool) {
        let until = (now / DAY_S + 1) * DAY_S;
        self.deferred
            .insert(host.to_string(), (until, reason, forbidden));
        self.entries.retain(|(_, h, _), _| h != host);
    }

    /// Fetch robots.txt for the origin, following at most `MAX_REDIRECTS` same-host
    /// redirects. Returns `Some(())` when a usable entry was stored, `None` when the host
    /// was deferred instead.
    fn fetch_entry(
        &mut self,
        scheme: &str,
        host: &str,
        port: u16,
        fetch: &dyn Fetch,
        now: u64,
    ) -> Option<()> {
        let default_port = if scheme == "https" { 443 } else { 80 };
        let host_part = if host.contains(':') {
            format!("[{host}]")
        } else {
            host.to_string()
        };
        let authority = if port == default_port {
            host_part
        } else {
            format!("{host_part}:{port}")
        };
        let mut url = format!("{scheme}://{authority}/robots.txt");
        let mut status = 0u16;
        let mut body = Vec::new();
        let mut truncated = false;
        for _ in 0..=MAX_REDIRECTS {
            let resp = match fetch.fetch(&url, ROBOTS_MAX_BYTES + 1) {
                Ok(r) => r,
                Err(FetchError::TooLarge) => {
                    self.defer(host, now, "robots_too_large", false);
                    return None;
                }
                Err(FetchError::BadUrl) => {
                    self.defer(host, now, "robots_redirect_refused", false);
                    return None;
                }
                Err(FetchError::Refused) => {
                    self.defer(host, now, "transport_refused", false);
                    return None;
                }
                Err(_) => {
                    self.defer(host, now, "robots_unreachable", false);
                    return None;
                }
            };
            status = resp.status;
            if (300..400).contains(&status) {
                let target = resp.header("location").unwrap_or("");
                let joined = join_url(&url, target);
                let ok = split_url(&joined)
                    .map(|(s, h, _, _)| {
                        (s == "http" || s == "https") && h.eq_ignore_ascii_case(host)
                    })
                    .unwrap_or(false);
                if !ok {
                    self.defer(host, now, "robots_redirect_refused", false);
                    return None;
                }
                url = joined;
                continue;
            }
            body = resp.body;
            truncated = resp.truncated;
            break;
        }
        if (300..400).contains(&status) {
            // Ran out of redirect budget.
            self.defer(host, now, "robots_redirect_refused", false);
            return None;
        }
        let origin = (scheme.to_string(), host.to_string(), port);
        if status == 401 || status == 403 {
            self.defer(host, now, "robots_forbidden", true);
            return None;
        }
        if status == 429 {
            self.defer(host, now, "robots_rate_limited", false);
            return None;
        }
        if (400..500).contains(&status) {
            self.entries.insert(
                origin,
                Entry {
                    fetched_at: now,
                    rules: None,
                    crawl_delay: None,
                    reason: "robots_not_found",
                },
            );
            return Some(());
        }
        if !(200..300).contains(&status) {
            self.defer(host, now, "robots_server_error", false);
            return None;
        }
        let body = strip_utf8_bom(&body);
        let text = if truncated {
            // `_read_capped` parity: an over-long body is cut at the last full line. A
            // partial trailing rule must not be parsed — a truncated `Allow:` could
            // over-allow, the unsafe direction.
            match body.iter().rposition(|b| *b == b'\n') {
                // Over the cap and not one full line: we cannot know the rules, so do
                // not fetch.
                None => {
                    self.defer(host, now, "robots_too_large", false);
                    return None;
                }
                Some(i) => String::from_utf8_lossy(&body[..i + 1]).into_owned(),
            }
        } else {
            String::from_utf8_lossy(body).into_owned()
        };
        let group = parse_group(&text);
        self.entries.insert(
            origin,
            Entry {
                fetched_at: now,
                rules: Some(group.0),
                crawl_delay: group.1,
                reason: "ok",
            },
        );
        Some(())
    }
}

/// `utf-8-sig` parity (`tools/crawler/robots.py::_parse`): a leading UTF-8 BOM is not
/// content. Without this the first line of a BOM'd file decodes as
/// `\u{feff}User-agent: …`, the field name never matches, the whole group ends up
/// with zero agents — and an empty rule set allows every path, the unsafe direction.
fn strip_utf8_bom(body: &[u8]) -> &[u8] {
    body.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(body)
}

/// `urljoin(url, target)` for the shapes robots redirects produce: absolute URLs and
/// scheme/host/path-relative references inside the same origin.
fn join_url(base: &str, target: &str) -> String {
    let t = target.trim();
    if t.starts_with("http://") || t.starts_with("https://") {
        return t.to_string();
    }
    if let Ok((scheme, host, port, _)) = split_url(base) {
        let default = if scheme == "https" { 443 } else { 80 };
        let host_part = if host.contains(':') {
            format!("[{host}]")
        } else {
            host.to_string()
        };
        let authority = if port == default {
            host_part
        } else {
            format!("{host_part}:{port}")
        };
        if let Some(rest) = t.strip_prefix("//") {
            return format!("{scheme}://{rest}");
        }
        if t.starts_with('/') {
            return format!("{scheme}://{authority}{t}");
        }
        let dir = match split_url(base).ok().and_then(|(_, _, _, p)| p.rfind('/')) {
            Some(i) => split_url(base).unwrap().3[..i + 1].to_string(),
            None => "/".to_string(),
        };
        return format!("{scheme}://{authority}{dir}{t}");
    }
    t.to_string()
}

// ---------- robots.txt parsing (RobotFileParser-compatible subset) ----------

#[derive(Debug, Default)]
struct Group {
    agents: Vec<String>,
    /// (allow, pattern)
    rules: Vec<(bool, String)>,
}

/// The group that applies to [`PRODUCT_TOKEN`] plus its `Crawl-delay` if the matching
/// entry declares one.
///
/// Selection is the CPython `RobotFileParser` pair `_add_entry` + `can_fetch` (the same
/// one `tools/crawler/robots.py::_group` delegates to): an entry carrying `*` in its
/// agents becomes the *default* entry — consulted only after every specific entry fails
/// to match, and the first default wins (later `*` entries are dropped entirely). Picking
/// the first matching entry in file order instead would let the standard layout
/// (`User-agent: *` + `Allow` first, a specific `Disallow` later) disarm the specific
/// rules — the gate would fetch what the reference parser forbids.
///
/// Entry splitting is the `RobotFileParser.parse` state machine: a *raw* empty line after
/// collected agents discards them, a raw empty line after rules closes the entry;
/// comment-only lines never split.
fn parse_group(text: &str) -> (Group, Option<f64>) {
    let mut entries: Vec<(Group, Option<f64>)> = Vec::new();
    let mut cur = Group::default();
    let mut cur_delay: Option<f64> = None;
    let mut state = 0u8; // 0 = looking for user-agent, 1 = collecting agents, 2 = rules
    for raw in text.lines() {
        if raw.is_empty() {
            if state == 1 {
                cur = Group::default();
                cur_delay = None;
                state = 2;
            } else if state == 2 {
                entries.push((std::mem::take(&mut cur), cur_delay.take()));
                state = 0;
            }
            continue;
        }
        let stripped = raw.split('#').next().unwrap_or("").trim();
        if stripped.is_empty() {
            continue;
        }
        let (field, value) = match stripped.split_once(':') {
            Some((f, v)) => (f.trim().to_ascii_lowercase(), v.trim()),
            None => continue,
        };
        match field.as_str() {
            "user-agent" => {
                if state == 2 {
                    entries.push((std::mem::take(&mut cur), cur_delay.take()));
                }
                cur.agents.push(value.to_ascii_lowercase());
                state = 1;
            }
            "crawl-delay" => {
                if state != 0 {
                    if let Ok(d) = value.parse::<f64>() {
                        cur_delay = Some(d);
                    }
                    state = 2;
                }
            }
            _ => {
                // allow/disallow and every other directive stay rule lines (as stdlib).
                if field == "allow" || field == "disallow" {
                    cur.rules.push((field == "allow", value.to_string()));
                }
                state = 2;
            }
        }
    }
    if !cur.agents.is_empty() || !cur.rules.is_empty() {
        entries.push((cur, cur_delay));
    }
    // `applies_to` parity: our token lowercased and cut at the first `/` (the product
    // token carries no `/`, but the reference splits it); a declared agent matches when
    // it is a substring of the token — an empty agent string is a substring of every
    // token, exactly as `'' in ua` is True in Python.
    let token = PRODUCT_TOKEN
        .split('/')
        .next()
        .unwrap_or(PRODUCT_TOKEN)
        .to_ascii_lowercase();
    let mut default_entry: Option<(&Group, &Option<f64>)> = None;
    for (entry, delay) in &entries {
        if entry.agents.iter().any(|a| a == "*") {
            if default_entry.is_none() {
                default_entry = Some((entry, delay));
            }
            continue;
        }
        if entry.agents.iter().any(|a| token.contains(a.as_str())) {
            return (
                Group {
                    agents: entry.agents.clone(),
                    rules: entry.rules.clone(),
                },
                *delay,
            );
        }
    }
    match default_entry {
        Some((entry, delay)) => (
            Group {
                agents: entry.agents.clone(),
                rules: entry.rules.clone(),
            },
            *delay,
        ),
        None => (Group::default(), None),
    }
}

/// RFC 9309 selection: the longest matching rule wins; Allow wins a tie.
fn can_fetch(group: &Group, path_and_query: &str) -> bool {
    let (path, query) = match path_and_query.split_once('?') {
        Some((p, q)) => (p, format!("?{q}")),
        None => (path_and_query, String::new()),
    };
    let path = format!(
        "{}{}",
        percent_decode(if path.is_empty() { "/" } else { path }),
        percent_decode(&query)
    );
    let mut best_len: i64 = -1;
    let mut allowed = true;
    for (allow, pattern) in &group.rules {
        let pattern = percent_decode(pattern);
        if pattern.is_empty() || !rule_matches(&pattern, &path) {
            continue;
        }
        // `len(pattern)` parity: Python counts characters, not bytes — on multibyte
        // rule paths a longer-bytes Allow must not outrank a longer-chars Disallow.
        let len = pattern.chars().count() as i64;
        if len > best_len || (len == best_len && *allow) {
            best_len = len;
            allowed = *allow;
        }
    }
    allowed
}

/// Prefix match with `*` wildcards and an optional trailing `$` anchor (port of
/// `_matches` in robots.py; no regex, no backtracking blowup).
fn rule_matches(pattern: &str, path: &str) -> bool {
    let (pattern, anchored) = match pattern.strip_suffix('$') {
        Some(p) => (p, true),
        None => (pattern, false),
    };
    let mut parts = pattern.split('*');
    let first = parts.next().unwrap_or("");
    if !path.starts_with(first) {
        return false;
    }
    let mut pos = first.len();
    let rest: Vec<&str> = parts.collect();
    if rest.is_empty() {
        return !anchored || pos == path.len();
    }
    for mid in &rest[..rest.len() - 1] {
        match path[pos..].find(mid) {
            Some(i) => pos += i + mid.len(),
            None => return false,
        }
    }
    let last = rest[rest.len() - 1];
    if anchored {
        path.len() >= pos + last.len() && path.ends_with(last)
    } else {
        path[pos..].find(last).is_some()
    }
}

/// Minimal percent-decoding (the `unquote` both sides get before matching).
fn percent_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let (Some(h), Some(l)) = (hex(bytes[i + 1]), hex(bytes[i + 2])) {
                out.push(h * 16 + l);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn hex(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'a'..=b'f' => Some(b - b'a' + 10),
        b'A'..=b'F' => Some(b - b'A' + 10),
        _ => None,
    }
}
