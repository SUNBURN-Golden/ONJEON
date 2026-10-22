//! `evidence_ref` grammar: parser, validator and fixture-id converter (T-CT-04).
//!
//! The grammar is 02_구현계약 §6.1; `evidence_ref.md` is its table and
//! `json/common.schema.json` carries the same grammar as regular expressions.
//! [`parse`] accepts exactly what the grammar allows, with these narrowings that
//! make every accepted string round-trip byte for byte through [`ParsedRef`]'s
//! `Display`:
//!
//! * decimal numbers (pages, criterion version) have no leading zeros,
//! * an `obs` source is `src:<org>/<channel>/<n>` (three parts, §1.1) and its
//!   time is a real RFC 3339 timestamp,
//! * a page range is ascending and starts at page 1 or later.
//!
//! [`validate`] adds the checks that need more than the grammar: the clause page
//! lies inside its segment's page range and coordinates are positive numbers.
//! Role rules (`basis` accepts only clause refs of statute segments, ...) belong
//! to the release builder and the database, not here (02 §6.1).

use std::fmt;

const ULID_LEN: usize = 26;

/// A parsed `evidence_ref`. `Display` renders the canonical string back.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ParsedRef {
    Segment(SegmentParts),
    Clause(ClauseParts),
    Edition(String),
    Premium(String),
    Assertion(String),
    Rule(RuleParts),
    Observation(ObservationParts),
    Raw(String),
    Evaluation(String),
    Criterion(CriterionParts),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SegmentParts {
    /// First 12 hex characters of the raw SHA-256, or up to all 64 on collision.
    pub raw_sha: String,
    pub page_from: u32,
    pub page_to: u32,
    pub doc_role: String,
    pub seg_rule_ver: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClauseParts {
    pub segment: SegmentParts,
    pub path_slug: String,
    pub page: u32,
    pub extractor: String,
    pub extractor_ver: String,
    /// `x,y,w,h` exactly as written (kept as text so the round trip is exact).
    pub bbox: Option<[String; 4]>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuleParts {
    pub rule_id: String,
    pub rule_version: String,
    pub content_hash12: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ObservationParts {
    pub org: String,
    pub channel: String,
    pub n: String,
    pub observed_at: String,
    pub sha16: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CriterionParts {
    pub slug: String,
    pub version: u32,
}

/// The ten grammar productions (the kinds of `evidence_ref`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum RefKind {
    Segment,
    Clause,
    Edition,
    Premium,
    Assertion,
    Rule,
    Observation,
    Raw,
    Evaluation,
    Criterion,
}

impl RefKind {
    pub const ALL: [RefKind; 10] = [
        RefKind::Segment,
        RefKind::Clause,
        RefKind::Edition,
        RefKind::Premium,
        RefKind::Assertion,
        RefKind::Rule,
        RefKind::Observation,
        RefKind::Raw,
        RefKind::Evaluation,
        RefKind::Criterion,
    ];
}

impl ParsedRef {
    pub fn kind(&self) -> RefKind {
        match self {
            ParsedRef::Segment(_) => RefKind::Segment,
            ParsedRef::Clause(_) => RefKind::Clause,
            ParsedRef::Edition(_) => RefKind::Edition,
            ParsedRef::Premium(_) => RefKind::Premium,
            ParsedRef::Assertion(_) => RefKind::Assertion,
            ParsedRef::Rule(_) => RefKind::Rule,
            ParsedRef::Observation(_) => RefKind::Observation,
            ParsedRef::Raw(_) => RefKind::Raw,
            ParsedRef::Evaluation(_) => RefKind::Evaluation,
            ParsedRef::Criterion(_) => RefKind::Criterion,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RefError {
    pub reason: &'static str,
}

impl fmt::Display for RefError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "invalid evidence_ref: {}", self.reason)
    }
}

impl std::error::Error for RefError {}

fn err<T>(reason: &'static str) -> Result<T, RefError> {
    Err(RefError { reason })
}

// ---- character classes -----------------------------------------------------

fn is_hex(s: &str, min: usize, max: usize) -> bool {
    (min..=max).contains(&s.len()) && s.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

fn is_ulid(s: &str) -> bool {
    s.len() == ULID_LEN
        && s.bytes().all(|b| {
            matches!(b, b'0'..=b'9' | b'A'..=b'H' | b'J' | b'K' | b'M' | b'N' | b'P'..=b'T' | b'V'..=b'Z')
        })
}

/// `[A-Za-z0-9._-]+`
fn is_token(s: &str) -> bool {
    !s.is_empty()
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'))
}

/// `[a-z][a-z0-9_]*`
fn is_snake(s: &str) -> bool {
    let mut it = s.bytes();
    matches!(it.next(), Some(b'a'..=b'z'))
        && it.all(|b| matches!(b, b'a'..=b'z' | b'0'..=b'9' | b'_'))
}

/// `[a-z0-9_-]+`
fn is_slug(s: &str) -> bool {
    !s.is_empty()
        && s.bytes()
            .all(|b| matches!(b, b'a'..=b'z' | b'0'..=b'9' | b'_' | b'-'))
}

/// Canonical decimal: digits, no leading zero (except `0`).
fn number(s: &str, reason: &'static str) -> Result<u32, RefError> {
    let ok =
        !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit()) && (s == "0" || !s.starts_with('0'));
    if !ok {
        return err(reason);
    }
    s.parse::<u32>().or_else(|_| err(reason))
}

fn no_ws(s: &str) -> bool {
    !s.is_empty() && !s.chars().any(char::is_whitespace)
}

// ---- RFC 3339 --------------------------------------------------------------

fn digits(s: &str, n: usize) -> Option<u32> {
    if s.len() == n && s.bytes().all(|b| b.is_ascii_digit()) {
        s.parse().ok()
    } else {
        None
    }
}

/// `YYYY-MM-DDThh:mm:ss[.f+](Z|±hh:mm)`, uppercase `T` and `Z`, real calendar date.
pub fn is_rfc3339(s: &str) -> bool {
    let Some((date, time)) = s.split_once('T') else {
        return false;
    };
    let d: Vec<&str> = date.split('-').collect();
    let (Some(y), Some(m), Some(day)) = (
        d.first().and_then(|x| digits(x, 4)),
        d.get(1).and_then(|x| digits(x, 2)),
        d.get(2).and_then(|x| digits(x, 2)),
    ) else {
        return false;
    };
    if d.len() != 3 || !(1..=12).contains(&m) {
        return false;
    }
    let leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
    let dim = match m {
        2 if leap => 29,
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    };
    if !(1..=dim).contains(&day) {
        return false;
    }
    let (clock, zone) = if let Some(c) = time.strip_suffix('Z') {
        (c, None)
    } else if let Some(i) = time.rfind(['+', '-']) {
        (&time[..i], Some(&time[i + 1..]))
    } else {
        return false;
    };
    if let Some(z) = zone {
        let Some((zh, zm)) = z.split_once(':') else {
            return false;
        };
        match (digits(zh, 2), digits(zm, 2)) {
            (Some(h), Some(m)) if h <= 23 && m <= 59 => {}
            _ => return false,
        }
    }
    let (hms, frac) = match clock.split_once('.') {
        Some((h, f)) => (h, Some(f)),
        None => (clock, None),
    };
    if let Some(f) = frac {
        if f.is_empty() || !f.bytes().all(|b| b.is_ascii_digit()) {
            return false;
        }
    }
    let t: Vec<&str> = hms.split(':').collect();
    if t.len() != 3 {
        return false;
    }
    match (digits(t[0], 2), digits(t[1], 2), digits(t[2], 2)) {
        (Some(h), Some(mi), Some(s)) => h <= 23 && mi <= 59 && s <= 60,
        _ => false,
    }
}

// ---- parser ----------------------------------------------------------------

/// Parse one `evidence_ref`. Grammar only; see [`validate`] for the semantic checks.
pub fn parse(input: &str) -> Result<ParsedRef, RefError> {
    // `clause:` embeds a segment and `obs:src:` embeds colons, so dispatch on the head.
    let Some((head, rest)) = input.split_once(':') else {
        return err("missing kind prefix");
    };
    match head {
        "seg" => parse_segment_body(rest).map(ParsedRef::Segment),
        "clause" => parse_clause_body(rest).map(ParsedRef::Clause),
        "ted" => ulid_ref(rest).map(ParsedRef::Edition),
        "premium" => ulid_ref(rest).map(ParsedRef::Premium),
        "assertion" => ulid_ref(rest).map(ParsedRef::Assertion),
        "eval" => ulid_ref(rest).map(ParsedRef::Evaluation),
        "rule" => parse_rule_body(rest).map(ParsedRef::Rule),
        "obs" => parse_obs_body(rest).map(ParsedRef::Observation),
        "raw" => {
            let Some(h) = rest.strip_prefix("sha256:") else {
                return err("raw ref needs the sha256: algorithm");
            };
            if is_hex(h, 64, 64) {
                Ok(ParsedRef::Raw(h.to_string()))
            } else {
                err("raw sha256 must be 64 lowercase hex characters")
            }
        }
        "crit" => parse_crit_body(rest).map(ParsedRef::Criterion),
        _ => err("unknown evidence_ref kind"),
    }
}

fn ulid_ref(s: &str) -> Result<String, RefError> {
    if is_ulid(s) {
        Ok(s.to_string())
    } else {
        err("ulid must be 26 Crockford base32 characters (no I, L, O, U)")
    }
}

fn parse_segment_body(s: &str) -> Result<SegmentParts, RefError> {
    // <raw_sha>:p<from>-<to>:<doc_role>:<seg_rule_ver>
    let parts: Vec<&str> = s.split(':').collect();
    if parts.len() != 4 {
        return err("segment needs raw_sha:pFROM-TO:doc_role:seg_rule_ver");
    }
    if !is_hex(parts[0], 12, 64) {
        return err("raw_sha must be 12 to 64 lowercase hex characters");
    }
    let Some(range) = parts[1].strip_prefix('p') else {
        return err("page range must start with p");
    };
    let Some((from, to)) = range.split_once('-') else {
        return err("page range must be pFROM-TO");
    };
    let page_from = number(from, "page_from is not a canonical number")?;
    let page_to = number(to, "page_to is not a canonical number")?;
    if page_from < 1 || page_from > page_to {
        return err("page range must be ascending and start at page 1 or later");
    }
    if !is_snake(parts[2]) {
        return err("doc_role must be lowercase snake_case");
    }
    if !is_token(parts[3]) {
        return err("seg_rule_ver must match [A-Za-z0-9._-]+");
    }
    Ok(SegmentParts {
        raw_sha: parts[0].to_string(),
        page_from,
        page_to,
        doc_role: parts[2].to_string(),
        seg_rule_ver: parts[3].to_string(),
    })
}

fn parse_clause_body(s: &str) -> Result<ClauseParts, RefError> {
    // seg:<...>/<path_slug>#p<page>:<extractor>@<ver>[@x,y,w,h]
    let Some(s) = s.strip_prefix("seg:") else {
        return err("clause must start with its segment (clause:seg:...)");
    };
    let Some((seg, tail)) = s.split_once('/') else {
        return err("clause needs /<path_slug> after the segment");
    };
    let segment = parse_segment_body(seg)?;
    let Some((path_slug, tail)) = tail.split_once('#') else {
        return err("clause needs #p<page> after the path_slug");
    };
    if !no_ws(path_slug) {
        return err("path_slug must be non-empty without whitespace or #");
    }
    let Some((page, edition)) = tail.split_once(':') else {
        return err("clause needs :<extractor>@<ver> after the page");
    };
    let Some(page) = page.strip_prefix('p') else {
        return err("clause page must be p<page>");
    };
    let page = number(page, "clause page is not a canonical number")?;
    let mut it = edition.split('@');
    let (Some(extractor), Some(ver)) = (it.next(), it.next()) else {
        return err("extraction edition must be <extractor>@<ver>");
    };
    if !is_token(extractor) || !is_token(ver) {
        return err("extractor and version must match [A-Za-z0-9._-]+");
    }
    let bbox = match it.next() {
        None => None,
        Some(b) => {
            let c: Vec<&str> = b.split(',').collect();
            let ok = c.len() == 4
                && c.iter()
                    .all(|x| !x.is_empty() && x.bytes().all(|y| y.is_ascii_digit() || y == b'.'));
            if !ok {
                return err("coordinates must be x,y,w,h of digits and dots");
            }
            Some([
                c[0].to_string(),
                c[1].to_string(),
                c[2].to_string(),
                c[3].to_string(),
            ])
        }
    };
    if it.next().is_some() {
        return err("too many @ parts in the extraction edition");
    }
    Ok(ClauseParts {
        segment,
        path_slug: path_slug.to_string(),
        page,
        extractor: extractor.to_string(),
        extractor_ver: ver.to_string(),
        bbox,
    })
}

fn parse_rule_body(s: &str) -> Result<RuleParts, RefError> {
    let Some((id, tail)) = s.split_once('@') else {
        return err("rule needs @<rule_version>");
    };
    let Some((ver, hash)) = tail.split_once('#') else {
        return err("rule needs #<content_hash12>");
    };
    if !is_token(id) || !is_token(ver) {
        return err("rule_id and rule_version must match [A-Za-z0-9._-]+");
    }
    if !is_hex(hash, 12, 12) {
        return err("content_hash12 must be 12 lowercase hex characters");
    }
    Ok(RuleParts {
        rule_id: id.to_string(),
        rule_version: ver.to_string(),
        content_hash12: hash.to_string(),
    })
}

fn parse_obs_body(s: &str) -> Result<ObservationParts, RefError> {
    // src:<org>/<channel>/<n>/<RFC3339>/<sha16>
    let Some(s) = s.strip_prefix("src:") else {
        return err("obs source must start with src:");
    };
    let f: Vec<&str> = s.split('/').collect();
    if f.len() != 5 {
        return err("obs needs <org>/<channel>/<n>/<RFC3339>/<sha16>");
    }
    if !f[..3].iter().all(|x| no_ws(x)) {
        return err("obs org, channel and n must be non-empty without whitespace");
    }
    if !is_rfc3339(f[3]) {
        return err("obs time is not RFC 3339");
    }
    if !is_hex(f[4], 16, 16) {
        return err("obs sha16 must be 16 lowercase hex characters");
    }
    Ok(ObservationParts {
        org: f[0].to_string(),
        channel: f[1].to_string(),
        n: f[2].to_string(),
        observed_at: f[3].to_string(),
        sha16: f[4].to_string(),
    })
}

fn parse_crit_body(s: &str) -> Result<CriterionParts, RefError> {
    let Some((slug, ver)) = s.split_once('@') else {
        return err("crit needs @<version>");
    };
    if !is_slug(slug) {
        return err("criterion slug must match [a-z0-9_-]+");
    }
    Ok(CriterionParts {
        slug: slug.to_string(),
        version: number(ver, "criterion version is not a canonical number")?,
    })
}

// ---- rendering -------------------------------------------------------------

impl fmt::Display for SegmentParts {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "seg:{}:p{}-{}:{}:{}",
            self.raw_sha, self.page_from, self.page_to, self.doc_role, self.seg_rule_ver
        )
    }
}

impl fmt::Display for ParsedRef {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ParsedRef::Segment(s) => write!(f, "{s}"),
            ParsedRef::Clause(c) => {
                write!(
                    f,
                    "clause:{}/{}#p{}:{}@{}",
                    c.segment, c.path_slug, c.page, c.extractor, c.extractor_ver
                )?;
                if let Some([x, y, w, h]) = &c.bbox {
                    write!(f, "@{x},{y},{w},{h}")?;
                }
                Ok(())
            }
            ParsedRef::Edition(u) => write!(f, "ted:{u}"),
            ParsedRef::Premium(u) => write!(f, "premium:{u}"),
            ParsedRef::Assertion(u) => write!(f, "assertion:{u}"),
            ParsedRef::Evaluation(u) => write!(f, "eval:{u}"),
            ParsedRef::Rule(r) => {
                write!(
                    f,
                    "rule:{}@{}#{}",
                    r.rule_id, r.rule_version, r.content_hash12
                )
            }
            ParsedRef::Observation(o) => write!(
                f,
                "obs:src:{}/{}/{}/{}/{}",
                o.org, o.channel, o.n, o.observed_at, o.sha16
            ),
            ParsedRef::Raw(h) => write!(f, "raw:sha256:{h}"),
            ParsedRef::Criterion(c) => write!(f, "crit:{}@{}", c.slug, c.version),
        }
    }
}

// ---- semantic validation ---------------------------------------------------

/// Parse and check what the grammar alone cannot: the clause page is inside its
/// segment's page range and the bounding box has positive width and height.
pub fn validate(input: &str) -> Result<ParsedRef, RefError> {
    let parsed = parse(input)?;
    if let ParsedRef::Clause(c) = &parsed {
        if c.page < c.segment.page_from || c.page > c.segment.page_to {
            return err("clause page lies outside its segment's page range");
        }
        if let Some(b) = &c.bbox {
            let mut v = [0f64; 4];
            for (slot, text) in v.iter_mut().zip(b.iter()) {
                *slot = text
                    .parse::<f64>()
                    .or_else(|_| err("coordinate is not a number"))?;
            }
            if v[2] <= 0.0 || v[3] <= 0.0 {
                return err("bounding box width and height must be positive");
            }
        }
    }
    Ok(parsed)
}

/// The kind of a valid `evidence_ref`, or `None` when it is not one.
pub fn kind_of(input: &str) -> Option<RefKind> {
    parse(input).ok().map(|p| p.kind())
}

// ---- fixture id converter --------------------------------------------------

/// A canonical ref produced from a fixture-local id. Always `origin=fixture`:
/// converting never makes test data service data (02 §6.1, §8).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FixtureRef {
    pub evidence_ref: String,
}

impl FixtureRef {
    pub const ORIGIN: crate::AssertionOrigin = crate::checks::ORIGIN_FIXTURE;
}

/// Where a fixture-local segment id (for example `seg:hana_r2_1`) lands.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FixtureSegment {
    pub local_id: String,
    /// Full SHA-256 of the raw file the segment is cut from.
    pub raw_sha256: String,
    pub page_from: u32,
    pub page_to: u32,
    pub doc_role: String,
    pub seg_rule_ver: String,
}

/// Where a fixture-local clause id (for example `hana_2601_3d#c_2_1_art1_1`) lands.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FixtureClause {
    pub local_id: String,
    pub segment_local_id: String,
    pub page: u32,
    /// `<extractor>@<version>`, for example `docproc-text@1.0`.
    pub extraction_edition: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct FixtureIdMap {
    pub segments: Vec<FixtureSegment>,
    pub clauses: Vec<FixtureClause>,
}

impl FixtureIdMap {
    fn segment(&self, local: &str) -> Result<&FixtureSegment, RefError> {
        self.segments
            .iter()
            .find(|s| s.local_id == local)
            .map_or_else(|| err("fixture segment id is not in the map"), Ok)
    }

    /// Canonical segment ref for a fixture-local segment id.
    pub fn convert_segment(&self, local: &str) -> Result<FixtureRef, RefError> {
        let s = self.segment(local)?;
        if !is_hex(&s.raw_sha256, 64, 64) {
            return err("fixture raw_sha256 must be 64 lowercase hex characters");
        }
        let text = format!(
            "seg:{}:p{}-{}:{}:{}",
            &s.raw_sha256[..12],
            s.page_from,
            s.page_to,
            s.doc_role,
            s.seg_rule_ver
        );
        validate(&text)?;
        Ok(FixtureRef { evidence_ref: text })
    }

    /// Canonical clause ref for a fixture-local clause id. The path slug is the
    /// part after `#` in the local id; the segment comes from the map.
    pub fn convert_clause(&self, local: &str) -> Result<FixtureRef, RefError> {
        let c = self
            .clauses
            .iter()
            .find(|c| c.local_id == local)
            .map_or_else(|| err("fixture clause id is not in the map"), Ok)?;
        let Some((_, slug)) = local.split_once('#') else {
            return err("fixture clause id needs #<path>");
        };
        let seg = self.convert_segment(&c.segment_local_id)?;
        let text = format!(
            "clause:{}/{}#p{}:{}",
            seg.evidence_ref, slug, c.page, c.extraction_edition
        );
        validate(&text)?;
        Ok(FixtureRef { evidence_ref: text })
    }

    /// Convert whichever kind of local id this is.
    pub fn convert(&self, local: &str) -> Result<FixtureRef, RefError> {
        if local.contains('#') {
            self.convert_clause(local)
        } else {
            self.convert_segment(local)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const ULID: &str = "01HZX3K4M5N6P7Q8R9S0T1V2W3";
    const SHA64: &str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    const SEG: &str = "seg:0123456789ab:p3-7:terms_main:seg-0.1";

    /// One sample per grammar production, in `RefKind::ALL` order.
    fn samples() -> Vec<(RefKind, String)> {
        vec![
            (RefKind::Segment, SEG.to_string()),
            (
                RefKind::Clause,
                format!("clause:{SEG}/art1.1#p4:docproc-text@1.0"),
            ),
            (RefKind::Edition, format!("ted:{ULID}")),
            (RefKind::Premium, format!("premium:{ULID}")),
            (RefKind::Assertion, format!("assertion:{ULID}")),
            (RefKind::Rule, "rule:cancer-dx@rule-0.2#0123456789ab".into()),
            (
                RefKind::Observation,
                "obs:src:life-hanwha/terms/1/2026-10-17T03:04:05Z/0123456789abcdef".into(),
            ),
            (RefKind::Raw, format!("raw:sha256:{SHA64}")),
            (RefKind::Evaluation, format!("eval:{ULID}")),
            (RefKind::Criterion, "crit:diag-amount@3".into()),
        ]
    }

    #[test]
    fn evidence_ref_every_kind_round_trips() {
        let samples = samples();
        let kinds: Vec<RefKind> = samples.iter().map(|(k, _)| *k).collect();
        assert_eq!(kinds, RefKind::ALL, "a grammar production has no sample");
        for (kind, text) in samples {
            let parsed = parse(&text).unwrap_or_else(|e| panic!("{text}: {e}"));
            assert_eq!(parsed.kind(), kind, "{text}");
            assert_eq!(parsed.to_string(), text, "round trip changed {text}");
            assert_eq!(validate(&text).unwrap(), parsed, "{text}");
            assert_eq!(kind_of(&text), Some(kind));
        }
    }

    #[test]
    fn evidence_ref_clause_variants_round_trip() {
        for text in [
            format!("clause:{SEG}/a/b/c#p3:docproc-text@1.0@10,20.5,30,40"),
            "clause:seg:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef:p1-1:annex:v2/\u{c81c}1\u{c870}#p1:t@1".to_string(),
            format!("clause:{SEG}/x#p7:docproc-text@1.0"),
        ] {
            let p = validate(&text).unwrap_or_else(|e| panic!("{text}: {e}"));
            assert_eq!(p.to_string(), text);
        }
    }

    #[test]
    fn evidence_ref_rejects_malformed() {
        let bad = [
            "",
            "seg",
            "foo:bar",
            // segment
            "seg:0123456789a:p1-2:terms_main:v1",
            "seg:0123456789AB:p1-2:terms_main:v1",
            "seg:0123456789ab:p2-1:terms_main:v1",
            "seg:0123456789ab:p0-1:terms_main:v1",
            "seg:0123456789ab:p01-2:terms_main:v1",
            "seg:0123456789ab:p1-2:Terms:v1",
            "seg:0123456789ab:p1-2:terms_main",
            "seg:0123456789ab:p1-2:terms_main:v 1",
            // clause
            "clause:0123456789ab/x#p1:t@1",
            "clause:seg:0123456789ab:p1-2:terms_main:v1#p1:t@1",
            "clause:seg:0123456789ab:p1-2:terms_main:v1/x:t@1",
            "clause:seg:0123456789ab:p1-2:terms_main:v1/x#p1:t",
            "clause:seg:0123456789ab:p1-2:terms_main:v1/x#p1:t@1@1,2,3",
            "clause:seg:0123456789ab:p1-2:terms_main:v1/x#p1:t@1@1,2,3,4@5",
            "clause:seg:0123456789ab:p1-2:terms_main:v1/x#1:t@1",
            // ulid kinds
            "ted:01HZX3K4M5N6P7Q8R9S0T1V2W",
            "ted:01HZX3K4M5N6P7Q8R9S0T1V2WI",
            "premium:01hzx3k4m5n6p7q8r9s0t1v2w3",
            "eval:",
            "assertion:a:01HZX3K4M5N6P7Q8R9S0T1V2W3",
            // rule
            "rule:r@v",
            "rule:r@v#0123456789a",
            "rule:r@v#0123456789AB",
            "rule:@v#0123456789ab",
            // obs
            "obs:src:a/b/1/2026-10-17T03:04:05Z/0123456789abcdef0",
            "obs:src:a/b/2026-10-17T03:04:05Z/0123456789abcdef",
            "obs:src:a/b/1/2026-02-30T03:04:05Z/0123456789abcdef",
            "obs:src:a/b/1/2026-10-17T03:04:05/0123456789abcdef",
            "obs:a/b/1/2026-10-17T03:04:05Z/0123456789abcdef",
            // raw
            "raw:sha256:abc",
            "raw:md5:0123456789abcdef0123456789abcdef",
            // crit
            "crit:Diag@1",
            "crit:diag@01",
            "crit:diag",
        ];
        for text in bad {
            assert!(parse(text).is_err(), "should be rejected: {text:?}");
        }
    }

    #[test]
    fn evidence_ref_validate_checks_what_the_grammar_cannot() {
        // Grammar-valid, but the clause page is outside the segment's pages.
        let out_of_range = format!("clause:{SEG}/art1#p9:docproc-text@1.0");
        assert!(parse(&out_of_range).is_ok());
        assert!(validate(&out_of_range).is_err());
        let flat_box = format!("clause:{SEG}/art1#p3:docproc-text@1.0@1,2,0,4");
        assert!(parse(&flat_box).is_ok());
        assert!(validate(&flat_box).is_err());
        let dots = format!("clause:{SEG}/art1#p3:docproc-text@1.0@1.2.3,2,3,4");
        assert!(parse(&dots).is_ok());
        assert!(validate(&dots).is_err());
    }

    #[test]
    fn evidence_ref_rfc3339_accepts_offsets_and_fractions_only_when_real() {
        for ok in [
            "2026-10-17T03:04:05Z",
            "2026-10-17T03:04:05.123Z",
            "2026-10-17T12:04:05+09:00",
            "2024-02-29T00:00:00Z",
        ] {
            assert!(is_rfc3339(ok), "{ok}");
        }
        for bad in [
            "2026-10-17",
            "2026-10-17t03:04:05Z",
            "2026-13-01T00:00:00Z",
            "2025-02-29T00:00:00Z",
            "2026-10-17T24:00:00Z",
            "2026-10-17T03:04:05.Z",
            "2026-10-17T03:04:05+0900",
        ] {
            assert!(!is_rfc3339(bad), "{bad}");
        }
    }

    /// The Rust grammar and the JSON Schema regexes must describe the same set. The
    /// schema file is the contract for TypeScript and Dart, so every sample the parser
    /// accepts has to be a form the schema's `EvidenceRef` lists, and the schema has
    /// exactly the ten alternatives.
    #[test]
    fn evidence_ref_matches_the_schema_alternatives() {
        let common: serde_json::Value =
            serde_json::from_str(include_str!("../json/common.schema.json")).unwrap();
        let defs = &common["$defs"];
        let union = defs["EvidenceRef"]["pattern"].as_str().unwrap();
        for name in [
            "SegmentRef",
            "ClauseRef",
            "EditionRef",
            "PremiumRef",
            "AssertionRef",
            "RuleEvidenceRef",
            "ObservationRef",
            "RawRef",
            "EvaluationRef",
            "CriterionRef",
        ] {
            let p = defs[name]["pattern"].as_str().unwrap();
            let body = p.trim_start_matches('^').trim_end_matches('$');
            assert!(
                union.contains(body),
                "{name} is not in the EvidenceRef union"
            );
        }
        assert_eq!(RefKind::ALL.len(), 10);
        // Each sample starts with the literal prefix its schema pattern starts with.
        for (kind, text) in samples() {
            let name = match kind {
                RefKind::Segment => "SegmentRef",
                RefKind::Clause => "ClauseRef",
                RefKind::Edition => "EditionRef",
                RefKind::Premium => "PremiumRef",
                RefKind::Assertion => "AssertionRef",
                RefKind::Rule => "RuleEvidenceRef",
                RefKind::Observation => "ObservationRef",
                RefKind::Raw => "RawRef",
                RefKind::Evaluation => "EvaluationRef",
                RefKind::Criterion => "CriterionRef",
            };
            let pat = defs[name]["pattern"].as_str().unwrap();
            let prefix: String = pat
                .trim_start_matches('^')
                .chars()
                .take_while(|c| c.is_ascii_lowercase() || *c == ':')
                .collect();
            assert!(text.starts_with(&prefix), "{name}: {text} vs {prefix}");
        }
    }

    fn map() -> FixtureIdMap {
        FixtureIdMap {
            segments: vec![FixtureSegment {
                local_id: "seg:hana_r2_1".into(),
                raw_sha256: SHA64.into(),
                page_from: 3,
                page_to: 7,
                doc_role: "terms_main".into(),
                seg_rule_ver: "seg-0.1".into(),
            }],
            clauses: vec![FixtureClause {
                local_id: "hana_2601_3d#c_2_1_art1_1".into(),
                segment_local_id: "seg:hana_r2_1".into(),
                page: 4,
                extraction_edition: "docproc-text@1.0".into(),
            }],
        }
    }

    #[test]
    fn evidence_ref_fixture_ids_convert_to_canonical_refs() {
        let m = map();
        let seg = m.convert("seg:hana_r2_1").unwrap();
        assert_eq!(seg.evidence_ref, "seg:0123456789ab:p3-7:terms_main:seg-0.1");
        let clause = m.convert("hana_2601_3d#c_2_1_art1_1").unwrap();
        assert_eq!(
            clause.evidence_ref,
            "clause:seg:0123456789ab:p3-7:terms_main:seg-0.1/c_2_1_art1_1#p4:docproc-text@1.0"
        );
        assert_eq!(kind_of(&clause.evidence_ref), Some(RefKind::Clause));
        assert_eq!(FixtureRef::ORIGIN.as_str(), "fixture");
        // The local forms are not canonical grammar.
        assert!(parse("seg:hana_r2_1").is_err());
        assert!(parse("hana_2601_3d#c_2_1_art1_1").is_err());
    }

    #[test]
    fn evidence_ref_fixture_converter_rejects_unmapped_or_inconsistent_input() {
        let mut m = map();
        assert!(m.convert("seg:unknown").is_err());
        assert!(m.convert("other#c1").is_err());
        m.clauses[0].page = 99; // outside the segment's pages
        assert!(m.convert("hana_2601_3d#c_2_1_art1_1").is_err());
        m.clauses[0].page = 4;
        m.segments[0].raw_sha256 = "abc".into();
        assert!(m.convert("seg:hana_r2_1").is_err());
    }
}
