//! List-page classification and item extraction for enumeration (T-DT-04).
//!
//! A 200 response is not an enumeration success by itself (DATA_PIPELINE_CONTRACT §2, §8;
//! Masterplan §24.2): a list URL that answers a login form, an error page, a JS shell or a
//! truncated body has produced no items. [`classify`] decides which case a response is; a
//! `LoginPage` records a `blocked` range, never an item count.
//!
//! Item extraction is declarative ([`ListParser`]) so each institution adapter configures
//! the shape its site actually publishes instead of sharing one guessed selector.

use serde::Serialize;

/// How a fetched list response should be treated.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PageClass {
    /// Parseable list content (may hold zero items — that is an empty page, not a failure).
    List,
    /// 200 but the body is a login/authentication form — never a successful list.
    LoginPage,
    /// An error page (non-2xx status, or 200 HTML the parser cannot see as a list).
    ErrorPage,
    /// The body cannot be list content at all (truncated, binary for an HTML plan, empty).
    NotListContent,
}

/// Classify one response for a list plan that expects `expect_json` content.
pub fn classify(
    status: u16,
    content_type: &str,
    body: &[u8],
    truncated: bool,
    expect_json: bool,
) -> PageClass {
    if !(200..300).contains(&status) {
        return PageClass::ErrorPage;
    }
    if truncated || body.is_empty() {
        return PageClass::NotListContent;
    }
    let ct = content_type.to_ascii_lowercase();
    if expect_json {
        return if serde_json::from_slice::<serde_json::Value>(body).is_ok() {
            PageClass::List
        } else if looks_like_login(body) {
            PageClass::LoginPage
        } else {
            PageClass::NotListContent
        };
    }
    // A body must look like markup (or be declared HTML) to be list content — a 200
    // with no Content-Type and a non-markup body is `NotListContent`, not an empty list.
    if ct.starts_with("text/html") || body_is_markup(body) {
        return if looks_like_login(body) {
            PageClass::LoginPage
        } else {
            PageClass::List
        };
    }
    PageClass::NotListContent
}

fn body_is_markup(body: &[u8]) -> bool {
    // A leading UTF-8 BOM is not markup text — tolerate it before the first tag.
    let body = body.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(body);
    body.iter()
        .position(|b| !b.is_ascii_whitespace())
        .map(|i| body[i] == b'<')
        .unwrap_or(false)
}

/// True when the body carries the markers of a login/credential form rather than a public
/// list. Conservative on purpose: a password input or a login-named form action is enough;
/// plain marketing text saying "로그인" without a form does not classify.
///
/// Case-insensitive ASCII scan over tags and attributes.
pub fn looks_like_login(body: &[u8]) -> bool {
    let html = String::from_utf8_lossy(body).to_ascii_lowercase();
    // `type = "password"` — whitespace around `=` inside a tag is legal HTML, so the
    // attribute markers are checked on a whitespace-free copy as well.
    let squashed: String = html.split_whitespace().collect();
    if squashed.contains("type=\"password\"")
        || squashed.contains("type='password'")
        || squashed.contains("type=password")
    {
        return true;
    }
    // Field names/ids sites give credential inputs.
    for marker in [
        "name=\"pwd\"",
        "name='pwd'",
        "id=\"pwd\"",
        "id='pwd'",
        "name=\"passwd\"",
        "name=\"password\"",
        "id=\"password\"",
        "name=\"userpw\"",
        "name=\"loginpw\"",
        "name=\"mb_password\"",
    ] {
        if html.contains(marker) || squashed.contains(marker) {
            return true;
        }
    }
    // A form whose action posts to a login endpoint.
    let mut rest = html.as_str();
    while let Some(i) = rest.find("<form") {
        let tail = &rest[i..];
        let tag_end = tail.find('>').map(|e| e + 1).unwrap_or(tail.len());
        let tag = &tail[..tag_end.min(tail.len())];
        if (tag.contains("action")
            && (tag.contains("login")
                || tag.contains("logon")
                || tag.contains("signin")
                || tag.contains("member")))
            || tag.contains("onsubmit") && tag.contains("login")
        {
            return true;
        }
        rest = &tail[tag_end..];
    }
    false
}

/// A discovered item in a list page.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ListItem {
    /// Stable id the adapter derived for the row (link key or JSON field value).
    pub id: String,
}

/// What a parsed page yielded.
#[derive(Debug, Clone, Default)]
pub struct ParsedPage {
    pub item_ids: Vec<String>,
    /// The total the page advertises, when it advertises one.
    pub advertised_total: Option<u64>,
    /// The next cursor the page itself yields, when the endpoint reports one.
    pub next_cursor: Option<String>,
}

/// Declarative extraction, configured per institution adapter.
#[derive(Debug, Clone)]
pub enum ListParser {
    /// Survey C_life §2/§3.5: complete JSON inventory embedded in `var result`.
    /// `document_field=None` yields candidate product rows; a field selects actual
    /// document references without assuming one document per product or edition.
    Lifeplanet { document_field: Option<String> },
    /// The body is JSON: `items_path` is a `.`-separated path to the item array and
    /// `id_field` the field inside each item object. `total_field` is a `.`-separated path
    /// to the advertised total, if the endpoint reports one.
    Json {
        items_path: String,
        id_field: String,
        total_field: Option<String>,
        next_field: Option<String>,
    },
    /// The body is HTML: collect ids from `href` attributes that contain
    /// `link_substring` (an empty substring matches every link). The id is the
    /// `id_query_key=` query value; an empty query key is rejected.
    /// `total_marker` is an optional literal preceding a
    /// decimal total (e.g. `총 <b>`).
    HtmlLinks {
        link_substring: String,
        id_query_key: String,
        total_marker: Option<String>,
        /// Site-specific positive empty-state evidence. Without either this marker
        /// or an advertised zero, no matching links means a parse failure.
        empty_marker: Option<String>,
    },
}

impl ListParser {
    pub fn expects_json(&self) -> bool {
        matches!(self, Self::Json { .. })
    }
}

/// Parse `body` with `parser`. Unknown JSON shapes are a parse failure — an unparseable
/// page is not an empty list.
pub fn parse_page(parser: &ListParser, body: &[u8]) -> Result<ParsedPage, &'static str> {
    match parser {
        ListParser::Lifeplanet { document_field } => {
            parse_lifeplanet(body, document_field.as_deref())
        }
        ListParser::Json {
            items_path,
            id_field,
            total_field,
            next_field,
        } => {
            let v: serde_json::Value =
                serde_json::from_slice(body).map_err(|_| "body is not JSON")?;
            let items = json_path(&v, items_path)
                .and_then(|v| v.as_array())
                .ok_or("items path is not an array")?;
            let mut out = ParsedPage::default();
            for item in items {
                let id = item
                    .get(id_field.as_str())
                    .and_then(|v| {
                        v.as_str()
                            .map(String::from)
                            .or_else(|| v.as_u64().map(|n| n.to_string()))
                    })
                    .ok_or("item lacks id field")?;
                out.item_ids.push(id);
            }
            if let Some(t) = total_field {
                out.advertised_total = json_path(&v, t).and_then(|v| {
                    v.as_u64()
                        .or_else(|| v.as_str().and_then(|s| s.parse().ok()))
                });
            }
            if let Some(n) = next_field {
                out.next_cursor = json_path(&v, n).and_then(|v| {
                    v.as_str()
                        .and_then(|s| (!s.is_empty()).then(|| s.to_string()))
                        .or_else(|| v.as_u64().map(|x| x.to_string()))
                });
            }
            Ok(out)
        }
        ListParser::HtmlLinks {
            link_substring,
            id_query_key,
            total_marker,
            empty_marker,
        } => {
            let html = String::from_utf8_lossy(body);
            let mut out = ParsedPage::default();
            for href in href_values(&html) {
                if !link_substring.is_empty() && !href.contains(link_substring.as_str()) {
                    continue;
                }
                let id = if id_query_key.is_empty() {
                    Some(href.clone())
                } else {
                    query_value(&href, id_query_key)
                };
                if let Some(id) = id {
                    if !out.item_ids.contains(&id) {
                        out.item_ids.push(id);
                    }
                }
            }
            if let Some(marker) = total_marker {
                out.advertised_total = total_after_marker(&html, marker);
            }
            if id_query_key.is_empty() {
                return Err("HTML list requires a site-specific item selector and key");
            }
            // HTTP 200 and absence of links cannot prove an empty list. Maintenance
            // pages and unrendered JS shells must fail even without a total marker.
            let verified_empty = out.advertised_total == Some(0)
                || empty_marker
                    .as_ref()
                    .is_some_and(|m| !m.is_empty() && html.contains(m));
            if out.item_ids.is_empty() && !verified_empty {
                return Err("HTML list structure or verified empty-state evidence absent");
            }
            Ok(out)
        }
    }
}

/// Parse JSON as data; never evaluate site JavaScript. The survey observed all rows
/// in outData.prdList, including hidden sale periods, on each of the two list pages.
fn parse_lifeplanet(body: &[u8], document_field: Option<&str>) -> Result<ParsedPage, &'static str> {
    if document_field.is_some_and(|field| !["insTxtPat", "prdSryPat", "prdMdPat"].contains(&field))
    {
        return Err("unverified document field");
    }
    let html = std::str::from_utf8(body).map_err(|_| "inventory is not UTF-8")?;
    let (_, tail) = html
        .split_once("var result")
        .ok_or("inventory variable absent")?;
    let tail = tail
        .trim_start()
        .strip_prefix('=')
        .ok_or("inventory assignment absent")?;
    let data = serde_json::Deserializer::from_str(tail.trim_start())
        .into_iter::<serde_json::Value>()
        .next()
        .ok_or("inventory data absent")?
        .map_err(|_| "inventory JSON malformed")?;
    let rows = json_path(&data, "outData.prdList")
        .and_then(|v| v.as_array())
        .ok_or("inventory rows absent")?;
    let mut out = ParsedPage::default();
    for row in rows {
        // A code is not an edition identity (H1/H5). Pin the complete observed
        // metadata row as a discovery candidate, without inventing a sale-version key.
        for field in ["prdCd", "saleStYmd", "saleEdYmd"] {
            if row
                .get(field)
                .and_then(|v| v.as_str())
                .is_none_or(str::is_empty)
            {
                return Err("inventory row identity absent");
            }
        }
        let id = if let Some(field) = document_field {
            // Missing references are not proof that the expected document is absent.
            let path = row
                .get(field)
                .and_then(|v| v.as_str())
                .filter(|s| !s.trim().is_empty())
                .ok_or("document reference missing")?;
            path.to_string()
        } else {
            format!(
                "lifeplanet-row:{}",
                crate::digest::sha256_hex(
                    &serde_json::to_vec(row).map_err(|_| "inventory row malformed")?
                )
            )
        };
        if !out.item_ids.contains(&id) {
            out.item_ids.push(id);
        }
    }
    Ok(out)
}

fn json_path<'a>(v: &'a serde_json::Value, path: &str) -> Option<&'a serde_json::Value> {
    let mut cur = v;
    for seg in path.split('.') {
        if seg.is_empty() {
            continue;
        }
        cur = if let Ok(i) = seg.parse::<usize>() {
            cur.get(i)?
        } else {
            cur.get(seg)?
        };
    }
    Some(cur)
}

/// All `href="…"`/`href='…'` attribute values in order, entity-decoded the way a real
/// HTML parser hands them back (`&amp;` is a literal `&`).
///
/// Attribute *names* are matched on a lowercased copy (`HREF` matches), but values are
/// sliced from the original document: an id like `tptyCode=PB15` is case-significant —
/// lowercasing it would mangle the id and merge case-distinct items into one. `href`
/// must start an attribute word: `data-href`, `xhref` and similar names do not count,
/// and neither does `location.href='…'` inside script text — an attribute name is
/// preceded by whitespace (or `/` in a tolerated self-close).
fn href_values(html: &str) -> Vec<String> {
    let low = html.to_ascii_lowercase();
    let bytes = low.as_bytes();
    let mut out = Vec::new();
    let mut rest = 0usize;
    while let Some(i) = low[rest..].find("href") {
        let at = rest + i;
        if at == 0 || !(bytes[at - 1].is_ascii_whitespace() || bytes[at - 1] == b'/') {
            rest = at + 4;
            continue;
        }
        let tail = &low[at..];
        let val = tail
            .strip_prefix("href")
            .and_then(|t| t.trim_start().strip_prefix('='))
            .map(|t| t.trim_start())
            .and_then(|t| {
                // (offset, len) of the value inside `tail`, so the slice can come from
                // the original document, not the lowercased copy.
                let start = tail.len() - t.len();
                if let Some(q) = t.strip_prefix('"') {
                    q.find('"').map(|e| (start + 1, e))
                } else if let Some(q) = t.strip_prefix('\'') {
                    q.find('\'').map(|e| (start + 1, e))
                } else {
                    t.find(|c: char| c.is_whitespace() || c == '>')
                        .map(|e| (start, e))
                }
            });
        if let Some((s, len)) = val {
            out.push(unescape_entities(&html[at + s..at + s + len]));
        }
        rest = at + 4;
    }
    out
}

/// Entity-decode an attribute value (`html.unescape` subset). A page that writes its
/// query separators as `&amp;` yields `?a=1&amp;id=2` in the raw markup; splitting that
/// on `&` alone turns the second key into `amp;id`, silently dropping the item — and a
/// page whose links are all entity-encoded then looks like a *verified empty list*,
/// fabrication in the unsafe direction. Unknown or malformed entities stay literal.
fn unescape_entities(s: &str) -> String {
    if !s.contains('&') {
        return s.to_string();
    }
    let mut out = String::with_capacity(s.len());
    let mut rest = s;
    while let Some(i) = rest.find('&') {
        out.push_str(&rest[..i]);
        let tail = &rest[i + 1..];
        match decode_entity(tail) {
            Some((c, consumed)) => {
                out.push(c);
                rest = &tail[consumed..];
            }
            None => {
                out.push('&');
                rest = tail;
            }
        }
    }
    out.push_str(rest);
    out
}

/// `name;` at the head of `tail` → (decoded char, bytes consumed including the `;`).
/// The named set is the HTML-required five plus `&apos;`; numeric decimal/hex
/// references are decoded by code point.
fn decode_entity(tail: &str) -> Option<(char, usize)> {
    let end = tail.find(';')?;
    let name = &tail[..end];
    if name.is_empty() || name.len() > 10 {
        return None;
    }
    let c = match name {
        "amp" => '&',
        "lt" => '<',
        "gt" => '>',
        "quot" => '"',
        "apos" => '\'',
        _ => {
            let digits = name.strip_prefix('#')?;
            let v = match digits
                .strip_prefix('x')
                .or_else(|| digits.strip_prefix('X'))
            {
                Some(h) if !h.is_empty() && h.bytes().all(|b| b.is_ascii_hexdigit()) => {
                    u32::from_str_radix(h, 16).ok()?
                }
                _ if !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_digit()) => {
                    digits.parse::<u32>().ok()?
                }
                _ => return None,
            };
            char::from_u32(v)?
        }
    };
    Some((c, end + 1))
}

fn query_value(href: &str, key: &str) -> Option<String> {
    let q = href.split('?').nth(1)?;
    for pair in q.split('&') {
        let mut kv = pair.splitn(2, '=');
        if kv.next() == Some(key) {
            let v = kv.next().unwrap_or("");
            if !v.is_empty() {
                return Some(v.to_string());
            }
        }
    }
    None
}

/// First run of digits after `marker` (the "총 128건" shape), with separators stripped.
fn total_after_marker(html: &str, marker: &str) -> Option<u64> {
    let tail = html[html.find(marker)? + marker.len()..].trim_start();
    let digits: String = tail
        .chars()
        .take_while(|c| c.is_ascii_digit() || *c == ',')
        .collect();
    let digits: String = digits.chars().filter(|c| c.is_ascii_digit()).collect();
    digits.parse().ok()
}
