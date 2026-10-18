//! Code membership (C-26 `judge`) and scope relations computed from code sets.
//!
//! A category's members are `∪ included − ∪ excluded`, where each side is a CodeSet (ranges of KCD codes)
//! or another category. Only accepted claims count; anything unaccepted makes the answer unknown rather
//! than false. A scope relation between two categories is computed over an explicit code universe; without
//! one (no official code system loaded) the pair is `not_comparable`.

use crate::error::{OntologyError, Result};
use crate::model::View;
use onjeon_contracts::Tri;
use std::collections::BTreeSet;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TrailEntry {
    pub assertion_id: String,
    pub message: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Judgement {
    pub value: Tri,
    /// The assertions the answer rests on, in the order they were read.
    pub trail: Vec<TrailEntry>,
    /// CodeSet nodes consulted (code system, edition and effective date live on the node).
    pub code_system_refs: Vec<String>,
    /// The date the judgement was asked for (CodeSets say `judged_as_of: diagnosis_date`).
    pub judged_as_of: Option<String>,
}

impl Judgement {
    pub fn evidence_assertion_ids(&self) -> Vec<&str> {
        self.trail.iter().map(|t| t.assertion_id.as_str()).collect()
    }
}

/// `A00`, `A00.1`: letter, two digits, optional minor digits.
struct Code<'a> {
    letter: char,
    major: u32,
    minor: Option<&'a str>,
}

fn parse_code(c: &str) -> Result<Code<'_>> {
    let bad = || OntologyError::BadCode(c.to_string());
    let b = c.as_bytes();
    if b.len() < 3 || !b[0].is_ascii_uppercase() || !b[1].is_ascii_digit() || !b[2].is_ascii_digit()
    {
        return Err(bad());
    }
    let minor = match &c[3..] {
        "" => None,
        rest => {
            let m = rest.strip_prefix('.').ok_or_else(bad)?;
            if m.is_empty() || !m.bytes().all(|x| x.is_ascii_digit()) {
                return Err(bad());
            }
            Some(m)
        }
    };
    Ok(Code {
        letter: b[0] as char,
        major: c[1..3].parse().map_err(|_| bad())?,
        minor,
    })
}

/// Is `code` inside `range` (`C16`, `C16.2`, `C00-C14`, `C00-D48`)? A major-only range covers every minor;
/// a hyphenated range compares (letter, major) and its bounds must not carry minors.
pub fn in_range(code: &str, range: &str) -> Result<bool> {
    let c = parse_code(code)?;
    if let Some((a, b)) = range.split_once('-') {
        let (a, b) = (parse_code(a)?, parse_code(b)?);
        // A bound with a minor digit has no defined meaning here; refuse instead of guessing.
        if a.minor.is_some() || b.minor.is_some() {
            return Err(OntologyError::BadCode(format!(
                "range bound with minor: {range}"
            )));
        }
        let key = (c.letter, c.major);
        return Ok((a.letter, a.major) <= key && key <= (b.letter, b.major));
    }
    let r = parse_code(range)?;
    if c.letter != r.letter || c.major != r.major {
        return Ok(false);
    }
    Ok(match r.minor {
        None => true,
        Some(n) => c.minor.is_some_and(|m| m.starts_with(n)),
    })
}

/// Is `code` a member of category `cat` at `as_of`? Claims outside their validity at `as_of` are ignored
/// (`None`: no date filter).
pub fn membership(view: &View, cat: &str, code: &str, as_of: Option<&str>) -> Result<Judgement> {
    parse_code(code)?;
    let mut trail = Vec::new();
    let mut refs = BTreeSet::new();
    let mut stack = Vec::new();
    let m = member(view, cat, code, as_of, &mut trail, &mut refs, &mut stack)?;
    Ok(Judgement {
        value: match m {
            Some(true) => Tri::True,
            Some(false) => Tri::False,
            None => Tri::Unknown,
        },
        trail,
        code_system_refs: refs.into_iter().collect(),
        judged_as_of: as_of.map(str::to_string),
    })
}

fn member(
    view: &View,
    cat: &str,
    code: &str,
    as_of: Option<&str>,
    trail: &mut Vec<TrailEntry>,
    refs: &mut BTreeSet<String>,
    stack: &mut Vec<String>,
) -> Result<Option<bool>> {
    if stack.iter().any(|c| c == cat) {
        return Ok(None); // a category defined through itself has no answer
    }
    let active = |a: &&crate::model::Assertion| as_of.is_none_or(|d| a.valid_on(d));
    let inc: Vec<_> = view
        .current()
        .filter(|a| a.subject == cat && a.predicate == "includes_codes")
        .filter(active)
        .collect();
    let exc: Vec<_> = view
        .current()
        .filter(|a| a.subject == cat && a.predicate == "excludes_codes")
        .filter(active)
        .collect();
    if inc.is_empty() {
        return Ok(None);
    }
    stack.push(cat.to_string());
    let label = view.node(cat).map_or(cat, |n| n.label()).to_string();
    let contains = |obj: Option<&str>,
                    trail: &mut Vec<TrailEntry>,
                    refs: &mut BTreeSet<String>,
                    stack: &mut Vec<String>|
     -> Result<Option<bool>> {
        let Some(n) = obj.and_then(|o| view.node(o)) else {
            return Ok(None);
        };
        if n.class == "CodeSet" {
            refs.insert(n.id.clone());
            let ranges = n
                .raw
                .get("ranges")
                .and_then(|r| r.as_array())
                .map(Vec::as_slice)
                .unwrap_or(&[]);
            for r in ranges {
                let r = r.as_str().ok_or_else(|| {
                    OntologyError::BadCode(format!("{}: range must be text", n.id))
                })?;
                if in_range(code, r)? {
                    return Ok(Some(true));
                }
            }
            return Ok(Some(false));
        }
        member(view, &n.id, code, as_of, trail, refs, stack)
    };
    let mut unknown = false;
    let mut included = false;
    for a in &inc {
        if !a.accepted() {
            unknown = true;
            trail.push(TrailEntry {
                assertion_id: a.id.clone(),
                message: format!("판정 불가({})", a.review_status.as_str()),
            });
            continue;
        }
        match contains(a.object.as_deref(), trail, refs, stack)? {
            None => unknown = true,
            Some(true) => {
                included = true;
                trail.push(TrailEntry {
                    assertion_id: a.id.clone(),
                    message: format!("{code} ∈ {label}의 포함 범위"),
                });
            }
            Some(false) => {}
        }
    }
    for a in &exc {
        if !a.accepted() {
            unknown = true;
            continue;
        }
        match contains(a.object.as_deref(), trail, refs, stack)? {
            None => unknown = true,
            Some(true) => {
                trail.push(TrailEntry {
                    assertion_id: a.id.clone(),
                    message: format!("{code}는 {label}에서 제외"),
                });
                stack.pop();
                return Ok(Some(false));
            }
            Some(false) => trail.push(TrailEntry {
                assertion_id: a.id.clone(),
                message: format!("{code}는 {label}의 제외 대상 아님"),
            }),
        }
    }
    stack.pop();
    Ok(if unknown { None } else { Some(included) })
}

/// The codes two categories are compared over, with the code system they come from.
/// Built by the caller from an official code system; this crate ships none.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CodeUniverse {
    pub code_system: String,
    pub edition: String,
    codes: Vec<String>,
}

impl CodeUniverse {
    pub fn new(code_system: &str, edition: &str, codes: Vec<String>) -> Result<CodeUniverse> {
        for c in &codes {
            parse_code(c)?;
        }
        Ok(CodeUniverse {
            code_system: code_system.to_string(),
            edition: edition.to_string(),
            codes,
        })
    }

    pub fn codes(&self) -> &[String] {
        &self.codes
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScopeRelation {
    SameScope,
    Narrower,
    Broader,
    Overlaps,
    Disjoint,
    NotComparable,
}

impl ScopeRelation {
    pub fn as_str(self) -> &'static str {
        match self {
            ScopeRelation::SameScope => "same_scope",
            ScopeRelation::Narrower => "narrower",
            ScopeRelation::Broader => "broader",
            ScopeRelation::Overlaps => "overlaps",
            ScopeRelation::Disjoint => "disjoint",
            ScopeRelation::NotComparable => "not_comparable",
        }
    }
}

/// Relation of category `a` to category `b`, computed from their code sets over `universe`.
/// No universe (no official code system) or any unknown membership in it → `NotComparable`.
pub fn scope_relation(
    view: &View,
    a: &str,
    b: &str,
    universe: Option<&CodeUniverse>,
) -> Result<ScopeRelation> {
    let Some(u) = universe else {
        return Ok(ScopeRelation::NotComparable);
    };
    let (mut sa, mut sb) = (BTreeSet::new(), BTreeSet::new());
    for code in u.codes() {
        let (ma, mb) = (
            membership(view, a, code, None)?.value,
            membership(view, b, code, None)?.value,
        );
        if ma == Tri::Unknown || mb == Tri::Unknown {
            return Ok(ScopeRelation::NotComparable);
        }
        if ma == Tri::True {
            sa.insert(code);
        }
        if mb == Tri::True {
            sb.insert(code);
        }
    }
    Ok(if sa == sb {
        ScopeRelation::SameScope
    } else if sa.is_subset(&sb) {
        ScopeRelation::Narrower
    } else if sb.is_subset(&sa) {
        ScopeRelation::Broader
    } else if sa.intersection(&sb).next().is_some() {
        ScopeRelation::Overlaps
    } else {
        ScopeRelation::Disjoint
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn range_spans_letters() {
        assert!(in_range("C16", "C00-D48").unwrap());
        assert!(in_range("D10.3", "C00-D48").unwrap());
        assert!(!in_range("D49", "C00-D48").unwrap());
        assert!(in_range("A05", "A00-B99").unwrap());
        assert!(!in_range("C16", "A00-B99").unwrap());
        assert!(in_range("C16.9", "C16-C17").unwrap());
    }

    #[test]
    fn range_bound_with_minor_is_rejected() {
        assert!(matches!(
            in_range("C16.0", "C16.2-C17"),
            Err(OntologyError::BadCode(_))
        ));
    }
}
