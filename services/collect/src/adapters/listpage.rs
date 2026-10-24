//! List-page classification and item extraction for enumeration (T-DT-04).
//!
//! A 200 response is not an enumeration success by itself (DATA_PIPELINE_CONTRACT §2, §8;
//! Masterplan §24.2): a list URL that answers a login form, an error page, a JS shell or a
//! truncated body has produced no items. [`classify`] decides which case a response is; a
//! `LoginPage` records a `blocked` range, never an item count.
//!
//! Item extraction is declarative ([`ListParser`]) so each institution adapter configures
//! the shape its site actually publishes instead of sharing one guessed selector. Both
//! classification and extraction read markup through the same context-aware tokenizer:
//! credential markers are compared entity-decoded on real tags (numeric references with
//! or without the `;`, as browsers read them), and an embedded inventory counts only
//! from a top-level statement in executable script text — never from a comment, a
//! template, a data block, a JS comment, a string, a template literal or a regular
//! expression literal. Script text the lexer cannot classify fails closed.

use onjeon_contracts::DocRole;

use super::manifest::{CandidateDocument, ProductCandidate};

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
/// Two scans, either of which classifies (the safe direction is `blocked`, never a count):
///
/// 1. The HTML tokenizer ([`parse_html_context`]) reads every real tag and compares the
///    *entity-decoded*, trimmed, case-folded attribute values — `type="pass&#119;ord"`
///    and `type="pass&#119ord"` (no `;`, still decoded by browsers) are password inputs,
///    `action="/auth"` a credential form. Tags in inert contexts
///    (`template`, `svg`, …) still count: a login modal kept in a template is still a
///    login page, not a list.
/// 2. The legacy raw-text scan over the whole body, kept so markers inside script
///    templates or malformed markup the tokenizer refuses keep classifying as before.
pub fn looks_like_login(body: &[u8]) -> bool {
    if std::str::from_utf8(body)
        .ok()
        .and_then(|html| parse_html_context(html).ok())
        .is_some_and(|context| context.credential_form)
    {
        return true;
    }
    login_markers_in_raw_text(body)
}

/// Input names/ids sites give credential fields (compared entity-decoded, case-folded).
const CREDENTIAL_FIELD_NAMES: [&str; 10] = [
    "pwd",
    "passwd",
    "password",
    "userpw",
    "loginpw",
    "mb_password",
    "user_pw",
    "login_pw",
    "userpwd",
    "loginpwd",
];

/// Substrings of a form `action` that post to a credential endpoint.
const CREDENTIAL_ACTION_MARKERS: [&str; 7] = [
    "login", "logon", "signin", "sign-in", "sign_in", "member", "auth",
];

/// Entity-decoded, trimmed, ASCII-case-folded attribute value — how a browser compares
/// enumerated attributes such as `type`.
fn decoded_attr(tag: &HtmlTag<'_>, name: &str) -> Option<String> {
    tag.attrs
        .iter()
        .find(|(key, _)| key == name)
        .map(|(_, value)| unescape_entities(value).trim().to_ascii_lowercase())
}

/// Does one real start tag mark a credential form?
fn credential_tag(tag: &HtmlTag<'_>) -> bool {
    if tag.closing {
        return false;
    }
    match tag.name.as_str() {
        "input" => {
            decoded_attr(tag, "type").as_deref() == Some("password")
                || ["name", "id"].iter().any(|attr| {
                    decoded_attr(tag, attr)
                        .is_some_and(|v| CREDENTIAL_FIELD_NAMES.contains(&v.as_str()))
                })
                || decoded_attr(tag, "autocomplete")
                    .is_some_and(|v| v == "current-password" || v == "new-password")
        }
        "form" => {
            decoded_attr(tag, "action").is_some_and(|action| {
                CREDENTIAL_ACTION_MARKERS
                    .iter()
                    .any(|marker| action.contains(marker))
            }) || decoded_attr(tag, "onsubmit").is_some_and(|handler| handler.contains("login"))
        }
        _ => false,
    }
}

/// Raw-text login markers (case-insensitive ASCII scan over the whole body, attribute
/// spacing squashed). Kept alongside the tokenizer scan — see [`looks_like_login`].
fn login_markers_in_raw_text(body: &[u8]) -> bool {
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
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct ListItem {
    /// Stable id the adapter derived for the row (link key or JSON field value).
    pub id: String,
}

/// What a parsed page yielded.
#[derive(Debug, Clone, Default)]
pub struct ParsedPage {
    pub item_ids: Vec<String>,
    pub product_candidates: Vec<ProductCandidate>,
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
            let html = std::str::from_utf8(body).map_err(|_| "HTML is not UTF-8")?;
            let context = parse_html_context(html)?;
            let mut out = ParsedPage::default();
            for href in &context.hrefs {
                if !link_substring.is_empty() && !href.contains(link_substring.as_str()) {
                    continue;
                }
                let id = if id_query_key.is_empty() {
                    Some(href.clone())
                } else {
                    query_value(href, id_query_key)
                };
                if let Some(id) = id {
                    if !out.item_ids.contains(&id) {
                        out.item_ids.push(id);
                    }
                }
            }
            if let Some(marker) = total_marker {
                out.advertised_total = context.tail_after_marker(marker).and_then(total_from_tail);
            }
            if id_query_key.is_empty() {
                return Err("HTML list requires a site-specific item selector and key");
            }
            // HTTP 200 and absence of links cannot prove an empty list. Maintenance
            // pages and unrendered JS shells must fail even without a total marker.
            let verified_empty = out.advertised_total == Some(0)
                || empty_marker
                    .as_ref()
                    .is_some_and(|m| context.tail_after_marker(m).is_some());
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
    // The inventory is the `var result = {…}` statement the page's own script executes
    // (C_life §2). Only a top-level statement in executable script text can supply it:
    // an HTML comment, a template, a data-typed script, a JS comment, a string, a
    // template literal, a regular-expression literal or a function body that merely
    // *contains* the statement is not an inventory — a page carrying two such
    // statements is ambiguous, not a list — and script text the lexer cannot classify
    // (see [`js_var_assignment_tails`]) is a parse failure, never an empty list.
    let context = parse_html_context(html)?;
    let mut tails = Vec::new();
    for script in &context.scripts {
        tails.extend(js_var_assignment_tails(script, "result")?);
    }
    let tail = match tails.as_slice() {
        [] => return Err("inventory variable absent"),
        [tail] => *tail,
        _ => return Err("inventory variable ambiguous"),
    };
    let mut stream = serde_json::Deserializer::from_str(tail).into_iter::<serde_json::Value>();
    let data = stream
        .next()
        .ok_or("inventory data absent")?
        .map_err(|_| "inventory JSON malformed")?;
    // The statement must end where the JSON ends: `var result = {…}, result = {…}`,
    // `{…}.outData.prdList.slice(0, 0)` or `{…}\n(x)` each leave the page's `result`
    // something other than the object parsed here.
    if !js_statement_ends(&tail[stream.byte_offset()..]) {
        return Err("inventory statement not terminated");
    }
    let rows = json_path(&data, "outData.prdList")
        .and_then(|v| v.as_array())
        .ok_or("inventory rows absent")?;
    let mut out = ParsedPage::default();
    let source_page_hash = crate::digest::sha256_hex(body);
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
        let candidate_id = format!(
            "lifeplanet-row:{}",
            crate::digest::sha256_hex(
                &serde_json::to_vec(row).map_err(|_| "inventory row malformed")?
            )
        );
        let documents = [
            ("insTxtPat", DocRole::Terms),
            ("prdSryPat", DocRole::Summary),
            ("prdMdPat", DocRole::BusinessMethod),
        ]
        .into_iter()
        .filter_map(|(field, doc_role)| {
            row.get(field)
                .and_then(|v| v.as_str())
                .filter(|s| !s.trim().is_empty())
                .map(|reference| CandidateDocument {
                    doc_role,
                    reference: reference.into(),
                })
        })
        .collect();
        let candidate = ProductCandidate {
            candidate_id: candidate_id.clone(),
            product_code: row["prdCd"].as_str().unwrap().into(),
            sale_from: row["saleStYmd"].as_str().unwrap().into(),
            sale_to: row["saleEdYmd"].as_str().unwrap().into(),
            source_metadata: row.clone(),
            source_page_hash: source_page_hash.clone(),
            documents,
        };
        let id = if let Some(field) = document_field {
            // Missing references are not proof that the expected document is absent.
            let path = row
                .get(field)
                .and_then(|v| v.as_str())
                .filter(|s| !s.trim().is_empty())
                .ok_or("document reference missing")?;
            path.to_string()
        } else {
            candidate_id
        };
        if !out.product_candidates.contains(&candidate) {
            out.product_candidates.push(candidate);
        }
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

/// A conservative HTML tokenizer for the supported static list plans. Only actual
/// anchor/area start-tag attributes yield links. Comments, raw/RCDATA elements,
/// templates and foreign content cannot supply items or empty-list evidence.
/// Malformed or unterminated markup fails closed instead of guessing DOM recovery.
#[derive(Default)]
struct HtmlContext {
    hrefs: Vec<String>,
    evidence: String,
    marker_starts: Vec<std::ops::Range<usize>>,
    /// Executable text of each real, non-inert JavaScript `script` element, in document
    /// order — the only place an embedded inventory (`var result = …`) may come from.
    scripts: Vec<String>,
    /// Some real tag (inert contexts included) is a credential input or a login form.
    credential_form: bool,
}

/// Is this `script` start tag one the browser would execute as JavaScript? A missing or
/// empty `type` is classic/JS; data blocks (`text/template`, `application/json`, …) are
/// inert text, not executed code.
fn is_javascript_script(tag: &HtmlTag<'_>) -> bool {
    match decoded_attr(tag, "type") {
        None => true,
        Some(t) => matches!(
            t.as_str(),
            "" | "text/javascript"
                | "application/javascript"
                | "application/x-javascript"
                | "application/ecmascript"
                | "text/ecmascript"
                | "module"
        ),
    }
}

impl HtmlContext {
    fn tail_after_marker(&self, marker: &str) -> Option<&str> {
        if marker.is_empty() {
            return None;
        }
        self.evidence.match_indices(marker).find_map(|(at, _)| {
            self.marker_starts
                .iter()
                .any(|r| r.contains(&at))
                .then(|| &self.evidence[at + marker.len()..])
        })
    }
}

struct HtmlTag<'a> {
    name: String,
    closing: bool,
    attrs: Vec<(String, &'a str)>,
    end: usize,
}

fn html_tag(html: &str, start: usize) -> Result<HtmlTag<'_>, &'static str> {
    let bytes = html.as_bytes();
    let mut at = start + 1;
    let closing = bytes.get(at) == Some(&b'/');
    at += usize::from(closing);
    let name_start = at;
    while bytes
        .get(at)
        .is_some_and(|b| !b.is_ascii_whitespace() && !b"/>".contains(b))
    {
        if b"=\"'<".contains(&bytes[at]) {
            return Err("malformed HTML tag name");
        }
        at += 1;
    }
    if at == name_start {
        return Err("HTML tag name absent");
    }
    let name = html[name_start..at].to_ascii_lowercase();
    let mut attrs = Vec::new();
    loop {
        while bytes.get(at).is_some_and(u8::is_ascii_whitespace) {
            at += 1;
        }
        if bytes.get(at) == Some(&b'/') && bytes.get(at + 1) == Some(&b'>') {
            at += 1;
        }
        if bytes.get(at) == Some(&b'>') {
            return Ok(HtmlTag {
                name,
                closing,
                attrs,
                end: at + 1,
            });
        }
        if closing {
            return Err("malformed HTML closing tag");
        }
        let attr_start = at;
        while bytes
            .get(at)
            .is_some_and(|b| !b.is_ascii_whitespace() && !b"=/>\"'<".contains(b))
        {
            at += 1;
        }
        if at == attr_start {
            return Err("malformed or unterminated HTML tag");
        }
        let attr = html[attr_start..at].to_ascii_lowercase();
        while bytes.get(at).is_some_and(u8::is_ascii_whitespace) {
            at += 1;
        }
        let mut value = "";
        if bytes.get(at) == Some(&b'=') {
            at += 1;
            while bytes.get(at).is_some_and(u8::is_ascii_whitespace) {
                at += 1;
            }
            let quote = bytes
                .get(at)
                .copied()
                .ok_or("HTML attribute value absent")?;
            if quote == b'\"' || quote == b'\'' {
                at += 1;
                let value_start = at;
                while bytes.get(at).is_some_and(|b| *b != quote) {
                    at += 1;
                }
                value = html.get(value_start..at).ok_or("invalid HTML attribute")?;
                if bytes.get(at).is_none() {
                    return Err("unterminated HTML attribute");
                }
                at += 1;
            } else {
                let value_start = at;
                while bytes
                    .get(at)
                    .is_some_and(|b| !b.is_ascii_whitespace() && *b != b'>')
                {
                    if b"\"'<`".contains(&bytes[at]) {
                        return Err("malformed unquoted HTML attribute");
                    }
                    at += 1;
                }
                value = &html[value_start..at];
                if value.is_empty() {
                    return Err("HTML attribute value absent");
                }
            }
        }
        // HTML keeps the first of duplicate attributes.
        if !attrs.iter().any(|(key, _)| *key == attr) {
            attrs.push((attr, value));
        }
    }
}

fn parse_html_context(html: &str) -> Result<HtmlContext, &'static str> {
    let lower = html.to_ascii_lowercase();
    let bytes = html.as_bytes();
    let mut out = HtmlContext::default();
    let mut inert = Vec::new();
    let mut at = 0;
    while at < html.len() {
        if bytes[at] != b'<' {
            let end = html[at..].find('<').map_or(html.len(), |n| at + n);
            if inert.is_empty() {
                out.marker_starts
                    .push(out.evidence.len()..out.evidence.len() + end - at);
                out.evidence.push_str(&html[at..end]);
            }
            at = end;
            continue;
        }
        if html[at..].starts_with("<!--") {
            at += html[at + 4..]
                .find("-->")
                .ok_or("unterminated HTML comment")?
                + 7;
            out.evidence.push(' ');
            continue;
        }
        if matches!(bytes.get(at + 1), Some(b'!' | b'?')) {
            // Declarations/bogus comments are never tags. Reject ambiguous '<' in
            // them rather than accidentally interpreting embedded markup.
            let mut end = at + 2;
            let mut quote = None;
            while let Some(&b) = bytes.get(end) {
                if quote == Some(b) {
                    quote = None;
                } else if quote.is_none() {
                    if b == b'>' {
                        break;
                    }
                    if matches!(b, b'\'' | b'"') {
                        quote = Some(b);
                    }
                }
                end += 1;
            }
            if bytes.get(end).is_none() {
                return Err("unterminated HTML declaration");
            }
            if html[at + 1..end].contains('<') {
                return Err("ambiguous HTML declaration");
            }
            at = end + 1;
            out.evidence.push(' ');
            continue;
        }
        let name_at = at + 1 + usize::from(bytes.get(at + 1) == Some(&b'/'));
        if !bytes.get(name_at).is_some_and(u8::is_ascii_alphabetic) {
            if inert.is_empty() {
                out.marker_starts
                    .push(out.evidence.len()..out.evidence.len() + 1);
                out.evidence.push('<');
            }
            at += 1;
            continue;
        }
        let tag = html_tag(html, at)?;
        if credential_tag(&tag) {
            out.credential_form = true;
        }
        if !tag.closing && tag.name == "plaintext" {
            break;
        }
        if !tag.closing
            && matches!(
                tag.name.as_str(),
                "script"
                    | "style"
                    | "textarea"
                    | "title"
                    | "xmp"
                    | "iframe"
                    | "noembed"
                    | "noframes"
                    | "noscript"
            )
        {
            let closing = format!("</{}", tag.name);
            let mut search = tag.end;
            loop {
                let close_at = lower[search..]
                    .find(&closing)
                    .map(|n| search + n)
                    .ok_or("unterminated HTML text element")?;
                let boundary = close_at + closing.len();
                if bytes
                    .get(boundary)
                    .is_some_and(|b| b.is_ascii_whitespace() || b"/>".contains(b))
                {
                    // Legacy script double-escape states need a full HTML5 tree
                    // builder. Reject that unsupported form rather than treating an
                    // inner closing token as the end of executable text.
                    if tag.name == "script" && html[tag.end..close_at].contains("<!--") {
                        return Err("unsupported escaped HTML script context");
                    }
                    if tag.name == "script" && inert.is_empty() && is_javascript_script(&tag) {
                        out.scripts.push(html[tag.end..close_at].to_string());
                    }
                    at = html_tag(html, close_at)?.end;
                    break;
                }
                search = boundary;
            }
            out.evidence.push(' ');
            continue;
        }
        if matches!(tag.name.as_str(), "template" | "svg" | "math" | "select") {
            if tag.closing {
                if inert.last() != Some(&tag.name) {
                    return Err("unbalanced inert HTML element");
                }
                inert.pop();
            } else {
                inert.push(tag.name.clone());
            }
            at = tag.end;
            out.evidence.push(' ');
            continue;
        }
        if inert.is_empty() {
            if !tag.closing && matches!(tag.name.as_str(), "a" | "area") {
                if let Some((_, value)) = tag.attrs.iter().find(|(name, _)| name == "href") {
                    out.hrefs.push(unescape_entities(value));
                }
            }
            // Preserve static marker spelling while keeping quoted markup from
            // impersonating tags in an empty-state marker.
            out.marker_starts
                .push(out.evidence.len()..out.evidence.len() + 1);
            out.evidence.push('<');
            out.evidence
                .push_str(&html[at + 1..tag.end - 1].replace('<', "&lt;"));
            out.evidence.push('>');
        }
        at = tag.end;
    }
    if !inert.is_empty() {
        return Err("unterminated inert HTML element");
    }
    Ok(out)
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

/// A character reference at the head of `tail` → (decoded char, bytes consumed), the way
/// a browser reads one inside an attribute value:
///
/// - Numeric references (`&#119;`, `&#x77;`) decode with **or without** the `;` — the
///   semicolon is optional in HTML, so `pass&#119ord` is `password`. Zero, surrogates
///   and out-of-range values become U+FFFD; the C1 range is left as code points (the
///   Windows-1252 remap cannot produce an ASCII marker, so it cannot change a match).
/// - Named references are the HTML-required five plus `&apos;`. Without the `;`, only
///   the legacy `amp`/`lt`/`gt`/`quot` decode, and not when `=` or an alphanumeric
///   follows (the attribute-value rule that keeps `?a=1&ampid=2` literal).
///
/// Anything else stays literal.
fn decode_entity(tail: &str) -> Option<(char, usize)> {
    let bytes = tail.as_bytes();
    if bytes.first() == Some(&b'#') {
        let (digits_start, radix) = match bytes.get(1) {
            Some(b'x' | b'X') => (2, 16),
            _ => (1, 10),
        };
        let digits_end = digits_start
            + bytes[digits_start..]
                .iter()
                .take_while(|b| (**b as char).is_digit(radix))
                .count();
        if digits_end == digits_start {
            return None;
        }
        let c = match u32::from_str_radix(&tail[digits_start..digits_end], radix) {
            Ok(0) | Ok(0xD800..=0xDFFF) | Err(_) => '\u{FFFD}',
            Ok(v) => char::from_u32(v).unwrap_or('\u{FFFD}'),
        };
        let consumed = digits_end + usize::from(bytes.get(digits_end) == Some(&b';'));
        return Some((c, consumed));
    }
    let name_end = bytes
        .iter()
        .take_while(|b| b.is_ascii_alphanumeric())
        .count();
    let terminated = bytes.get(name_end) == Some(&b';');
    let c = match (&tail[..name_end], terminated) {
        ("amp" | "AMP", _) => '&',
        ("lt" | "LT", _) => '<',
        ("gt" | "GT", _) => '>',
        ("quot" | "QUOT", _) => '"',
        ("apos", true) => '\'',
        _ => return None,
    };
    if !terminated
        && bytes
            .get(name_end)
            .is_some_and(|b| *b == b'=' || b.is_ascii_alphanumeric())
    {
        return None;
    }
    Some((c, name_end + usize::from(terminated)))
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

/// Keywords after which a `/` begins a regular-expression literal, never a division.
const REGEX_AFTER_KEYWORDS: [&str; 15] = [
    "return",
    "typeof",
    "instanceof",
    "in",
    "of",
    "new",
    "delete",
    "void",
    "throw",
    "case",
    "do",
    "else",
    "yield",
    "await",
    "extends",
];

/// Keywords whose parenthesised head is followed by a statement — `if (x) /re/.test(y)`.
const PAREN_HEAD_KEYWORDS: [&str; 4] = ["if", "while", "for", "with"];

/// The previous significant token of the script lexer — what decides whether a `/` is a
/// division or the start of a regular-expression literal.
#[derive(Clone, Copy, PartialEq, Eq)]
enum JsToken<'a> {
    Start,
    /// An identifier, keyword or number (one maximal run of identifier bytes).
    Word(&'a str),
    /// The end of a string, template or regular-expression literal.
    Literal,
    Punct(u8),
    /// `)` — `head` when the matching `(` followed `if`/`while`/`for`/`with`.
    CloseParen {
        head: bool,
    },
    CloseBracket,
    CloseBrace,
}

/// The text after `=` of every top-level `var <name> = …` statement in executable script
/// text, or an error when the script uses a lexical context this scanner does not
/// classify.
///
/// A minimal JavaScript lexer, not an evaluator or a parser. It tokenizes line and block
/// comments (including Annex B `-->` line comments at a line start), string literals,
/// template literals without substitutions, regular-expression literals and
/// punctuators, and keeps the identifier/number word stream so that `var` must be a
/// whole word (`foo.var result` and `myvar result` are not declarations) and
/// `var result == x` is a comparison, not an assignment. Only a statement at brace depth
/// zero counts: a `var result` inside a function body is not the page's inventory.
///
/// Soundness over coverage: whatever the lexer skips can only *hide* a statement, which
/// fails the parse; whatever it cannot classify is an error, never a guess. A `/` is a
/// regex start after the script start, an operator, `(`/`,`/`[`/`{`/`;`/`:`, an
/// expression keyword or an `if`/`while`/`for`/`with` head, and a division after an
/// identifier, number, literal, `)` or `]`. After `}` or after `++`/`--` both readings
/// are possible, so the script is rejected. Template substitutions (`${`), unterminated
/// strings, comments or regexes and unbalanced brackets are rejected the same way — a
/// browser would not run such a script, so nothing in it can define `result`.
fn js_var_assignment_tails<'a>(script: &'a str, name: &str) -> Result<Vec<&'a str>, &'static str> {
    fn is_ident(b: u8) -> bool {
        b.is_ascii_alphanumeric() || b"_$.\\".contains(&b) || b >= 0x80
    }
    let bytes = script.as_bytes();
    let mut tails = Vec::new();
    let mut at = 0;
    let mut prev = JsToken::Start;
    let mut prev2 = JsToken::Start;
    let mut parens: Vec<bool> = Vec::new();
    let mut braces = 0usize;
    let mut line_start = true;
    while at < bytes.len() {
        let b = bytes[at];
        if b == b'\n' || b == b'\r' {
            line_start = true;
            at += 1;
            continue;
        }
        if b.is_ascii_whitespace() {
            at += 1;
            continue;
        }
        if b == b'/' && bytes.get(at + 1) == Some(&b'/') {
            at = js_line_end(bytes, at);
            continue;
        }
        if b == b'/' && bytes.get(at + 1) == Some(&b'*') {
            let end = bytes[at + 2..]
                .windows(2)
                .position(|w| w == b"*/")
                .map(|n| at + 2 + n)
                .ok_or("unsupported script lexical context: unterminated block comment")?;
            if bytes[at..end].iter().any(|c| matches!(c, b'\n' | b'\r')) {
                line_start = true;
            }
            at = end + 2;
            continue;
        }
        if line_start && bytes[at..].starts_with(b"-->") {
            at = js_line_end(bytes, at);
            continue;
        }
        line_start = false;
        let token = match b {
            b'\'' | b'"' | b'`' => {
                at = js_string_end(bytes, at)?;
                JsToken::Literal
            }
            b'/' => {
                if js_slash_starts_regex(prev, prev2)? {
                    at = js_regex_end(bytes, at)?;
                    JsToken::Literal
                } else {
                    at += 1;
                    JsToken::Punct(b'/')
                }
            }
            b'(' => {
                parens.push(matches!(prev, JsToken::Word(w) if PAREN_HEAD_KEYWORDS.contains(&w)));
                at += 1;
                JsToken::Punct(b'(')
            }
            b')' => {
                let head = parens
                    .pop()
                    .ok_or("unsupported script lexical context: unbalanced parenthesis")?;
                at += 1;
                JsToken::CloseParen { head }
            }
            b']' => {
                at += 1;
                JsToken::CloseBracket
            }
            b'{' => {
                braces += 1;
                at += 1;
                JsToken::Punct(b'{')
            }
            b'}' => {
                braces = braces
                    .checked_sub(1)
                    .ok_or("unsupported script lexical context: unbalanced brace")?;
                at += 1;
                JsToken::CloseBrace
            }
            _ if is_ident(b) => {
                let end = at + bytes[at..].iter().take_while(|c| is_ident(**c)).count();
                let word = &script[at..end];
                if word == "var" && braces == 0 {
                    let rest = script[end..].trim_start();
                    if let Some(after_name) = rest.strip_prefix(name) {
                        if !after_name.bytes().next().is_some_and(is_ident) {
                            let after_name = after_name.trim_start();
                            if after_name.starts_with('=') && !after_name.starts_with("==") {
                                tails.push(after_name[1..].trim_start());
                            }
                        }
                    }
                }
                at = end;
                JsToken::Word(word)
            }
            _ => {
                at += 1;
                JsToken::Punct(b)
            }
        };
        prev2 = prev;
        prev = token;
    }
    if !parens.is_empty() || braces != 0 {
        return Err("unsupported script lexical context: unbalanced brackets");
    }
    Ok(tails)
}

/// Division or regular-expression literal? See [`js_var_assignment_tails`].
fn js_slash_starts_regex(prev: JsToken<'_>, prev2: JsToken<'_>) -> Result<bool, &'static str> {
    Ok(match prev {
        JsToken::Start => true,
        JsToken::Word(word) => REGEX_AFTER_KEYWORDS.contains(&word),
        JsToken::Literal | JsToken::CloseBracket | JsToken::CloseParen { head: false } => false,
        JsToken::CloseParen { head: true } => true,
        JsToken::CloseBrace => {
            return Err("unsupported script lexical context: slash after brace");
        }
        JsToken::Punct(sign @ (b'+' | b'-')) if prev2 == JsToken::Punct(sign) => {
            return Err("unsupported script lexical context: slash after ++ or --");
        }
        JsToken::Punct(_) => true,
    })
}

/// Index just past the line terminator that ends the line starting at `at` (or the end).
fn js_line_end(bytes: &[u8], at: usize) -> usize {
    bytes[at..]
        .iter()
        .position(|c| matches!(c, b'\n' | b'\r'))
        .map_or(bytes.len(), |n| at + n + 1)
}

/// Index just past the string or template literal opening at `at`.
fn js_string_end(bytes: &[u8], at: usize) -> Result<usize, &'static str> {
    let quote = bytes[at];
    let mut at = at + 1;
    while let Some(&c) = bytes.get(at) {
        match c {
            b'\\' => at += 2,
            _ if c == quote => return Ok(at + 1),
            b'\n' | b'\r' if quote != b'`' => {
                return Err("unsupported script lexical context: unterminated string");
            }
            b'$' if quote == b'`' && bytes.get(at + 1) == Some(&b'{') => {
                return Err("unsupported script lexical context: template substitution");
            }
            _ => at += 1,
        }
    }
    Err("unsupported script lexical context: unterminated string")
}

/// Index just past the regular-expression literal (and its flags) opening at `at`.
fn js_regex_end(bytes: &[u8], at: usize) -> Result<usize, &'static str> {
    let mut at = at + 1;
    let mut in_class = false;
    while let Some(&c) = bytes.get(at) {
        match c {
            b'\\' => at += 2,
            b'\n' | b'\r' => {
                return Err("unsupported script lexical context: unterminated regex");
            }
            b'[' => {
                in_class = true;
                at += 1;
            }
            b']' => {
                in_class = false;
                at += 1;
            }
            b'/' if !in_class => {
                at += 1;
                while bytes
                    .get(at)
                    .is_some_and(|f| f.is_ascii_alphanumeric() || *f == b'_' || *f == b'$')
                {
                    at += 1;
                }
                return Ok(at);
            }
            _ => at += 1,
        }
    }
    Err("unsupported script lexical context: unterminated regex")
}

/// Does the script text after a parsed `var <name> = <value>` end that statement? Empty
/// text or a `;` does (comments skipped); so does a line break followed by a word that
/// cannot continue the expression (`var`, `function`, an identifier). Anything that
/// could extend the value — `,` (a second declarator), `.`/`(`/`[` (member or call), an
/// operator, or `in`/`instanceof` across the line break — does not.
fn js_statement_ends(rest: &str) -> bool {
    let bytes = rest.as_bytes();
    let mut at = 0;
    let mut crossed_line = false;
    loop {
        match bytes.get(at) {
            None => return true,
            Some(b';') => return true,
            Some(b'\n' | b'\r') => {
                crossed_line = true;
                at += 1;
            }
            Some(c) if c.is_ascii_whitespace() => at += 1,
            Some(b'/') if bytes.get(at + 1) == Some(&b'/') => {
                crossed_line = true;
                at = js_line_end(bytes, at);
            }
            Some(b'/') if bytes.get(at + 1) == Some(&b'*') => {
                let Some(n) = bytes[at + 2..].windows(2).position(|w| w == b"*/") else {
                    return false;
                };
                crossed_line |= bytes[at..at + 2 + n]
                    .iter()
                    .any(|c| matches!(c, b'\n' | b'\r'));
                at += 2 + n + 2;
            }
            Some(_) => break,
        }
    }
    if !crossed_line {
        return false;
    }
    let word_len = bytes[at..]
        .iter()
        .take_while(|c| c.is_ascii_alphanumeric() || **c == b'_' || **c == b'$')
        .count();
    word_len > 0 && !["in", "instanceof"].contains(&&rest[at..at + word_len])
}

/// First run of digits after a verified marker, with separators stripped.
fn total_from_tail(tail: &str) -> Option<u64> {
    let tail = tail.trim_start();
    let digits: String = tail
        .chars()
        .take_while(|c| c.is_ascii_digit() || *c == ',')
        .collect();
    let digits: String = digits.chars().filter(|c| c.is_ascii_digit()).collect();
    digits.parse().ok()
}
