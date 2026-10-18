//! Identity of a terms edition (K14, K16; 02_구현계약 §1.3a).
//!
//! An edition is its *composition* (body + referenced annexes + referenced definitions, each part with a
//! fingerprint) and the *evidence bundle* that backs it: every accepted `realizes` of that edition, from
//! however many raw files. The edition is `confirmed` only when the bundle covers the whole composition and no
//! fingerprint differs without a review decision. A fingerprint is evidence for a review; whether two
//! texts are the same edition is a review decision, never decided here.

use crate::error::{OntologyError, Result};
use crate::model::{Fingerprint, View};
use std::collections::BTreeSet;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EditionState {
    Confirmed,
    IdentityUnconfirmed,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MismatchKind {
    /// Same normalisation rule, different fingerprint: the text may differ.
    ContentDifferenceCandidate,
    /// Different normalisation rule (OCR vs text, ...) or no fingerprint: the two cannot be compared.
    NotComparable,
}

impl MismatchKind {
    pub fn as_str(self) -> &'static str {
        match self {
            MismatchKind::ContentDifferenceCandidate => "content_difference_candidate",
            MismatchKind::NotComparable => "not_comparable",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PartRef {
    pub role: String,
    pub fingerprint: Fingerprint,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Mismatch {
    /// The `realizes` assertion whose segment does not match the composition.
    pub assertion_id: String,
    /// Fingerprint the segment carries (`None`: the segment has none).
    pub part: Option<Fingerprint>,
    pub kind: MismatchKind,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EditionStatus {
    pub edition: String,
    pub state: EditionState,
    /// The evidence bundle: accepted `realizes` of this edition.
    pub accepted_realizes: Vec<String>,
    /// Composition parts no accepted `realizes` covers.
    pub missing_parts: Vec<PartRef>,
    /// Accepted `realizes` whose fingerprint differs from the composition and has no review decision covering it.
    pub mismatch: Vec<Mismatch>,
}

impl Mismatch {
    pub fn describe(&self) -> String {
        match self.kind {
            MismatchKind::ContentDifferenceCandidate => {
                "같은 정규화 규칙에서 지문이 다름(내용 차이 후보)".to_string()
            }
            MismatchKind::NotComparable => {
                format!(
                    "정규화 규칙이 달라 지문 비교 불가({})",
                    self.part.as_ref().map_or("None", |p| p.rule.as_str())
                )
            }
        }
    }
}

/// Status of every edition of the view, by edition id order.
pub fn edition_statuses(view: &View) -> Vec<EditionStatus> {
    view.editions
        .iter()
        .map(|e| status_of(view, &e.id))
        .collect()
}

/// Status of one edition. Errors if the view has no such edition.
pub fn edition_status(view: &View, edition: &str) -> Result<EditionStatus> {
    if !view.editions.iter().any(|e| e.id == edition) {
        return Err(OntologyError::Unknown(format!("edition {edition}")));
    }
    Ok(status_of(view, edition))
}

fn status_of(view: &View, edition: &str) -> EditionStatus {
    let ed = view
        .editions
        .iter()
        .find(|e| e.id == edition)
        .expect("checked by caller");
    let mut covered: BTreeSet<Fingerprint> = BTreeSet::new();
    let (mut accepted, mut mismatch) = (Vec::new(), Vec::new());
    let mut unreviewed = false;
    for a in view.current() {
        if a.predicate != "realizes" || a.object.as_deref() != Some(edition) || !a.accepted() {
            continue;
        }
        let Some(seg) = view.segment(&a.subject) else {
            continue;
        };
        accepted.push(a.id.clone());
        // 지문은 검수의 근거일 뿐 판 동일성은 검수 결정이다: 결정 출처가 검수/픽스처 가정이 아니면 확정하지 않는다.
        let by = a.decision.as_ref().and_then(|d| d.by.as_deref());
        if !matches!(by, Some("review_decision" | "fixture_assumption")) {
            unreviewed = true;
        }
        let reviewed_cover = a
            .decision
            .as_ref()
            .filter(|d| d.by.as_deref() == Some("review_decision"))
            .and_then(|d| d.covers.clone());
        match &seg.fingerprint {
            Some(fp) if ed.parts.iter().any(|p| &p.fingerprint == fp) => {
                covered.insert(fp.clone());
            }
            fp => {
                if let Some(c) = reviewed_cover {
                    covered.insert(c);
                } else {
                    let same_rule = fp
                        .as_ref()
                        .is_some_and(|f| ed.parts.iter().any(|p| p.fingerprint.rule == f.rule));
                    mismatch.push(Mismatch {
                        assertion_id: a.id.clone(),
                        part: fp.clone(),
                        kind: if same_rule {
                            MismatchKind::ContentDifferenceCandidate
                        } else {
                            MismatchKind::NotComparable
                        },
                    });
                }
            }
        }
    }
    let missing_parts: Vec<PartRef> = ed
        .parts
        .iter()
        .filter(|p| !covered.contains(&p.fingerprint))
        .map(|p| PartRef {
            role: p.role.clone(),
            fingerprint: p.fingerprint.clone(),
        })
        .collect();
    let state =
        if !accepted.is_empty() && missing_parts.is_empty() && mismatch.is_empty() && !unreviewed {
            EditionState::Confirmed
        } else {
            EditionState::IdentityUnconfirmed
        };
    EditionStatus {
        edition: edition.to_string(),
        state,
        accepted_realizes: accepted,
        missing_parts,
        mismatch,
    }
}
