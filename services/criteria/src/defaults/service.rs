//! Service-facing semantics for default candidates — what a consumer may ever see
//! and how a candidate interacts with a user's own assumption.
//!
//! Three contracts, made executable:
//!
//! - **후보는 표시되지 않는다.** [`DefaultsStore::for_service`] is the only read a
//!   service-mode consumer may make; it is empty until a `criteria_application`
//!   record exists (T-KN-14, D-08). This module offers no way to mark a candidate
//!   applied.
//! - **기본값은 "참고 통계"로 표시되고 사실로 표시되지 않는다.** [`display`] returns
//!   [`DisplayKind::ReferenceStatistic`] — the enum has no `fact` variant to
//!   select, and the public label is the fixed [`REFERENCE_STAT_LABEL`].
//! - **사용자 가정이 있으면 기본값을 덮지 않는다.** [`effective`] returns the
//!   assumption whenever one exists; a candidate is only the fallback. When
//!   neither exists it returns `None` — never 0 or an average, so the need result
//!   can go `hold` instead of fabricating a number (D-08).

use super::model::{CandidateVersion, DefaultValue};
use super::store::CandidateVersionRef;
use crate::model::CriterionSource;

/// The only label a loaded default may ever be shown under (§1.5: 참고 통계).
/// `editorial` sources are impossible in this store, so "온전의 판단" labelling
/// never applies here.
pub const REFERENCE_STAT_LABEL: &str = "참고 통계";

/// What a displayed candidate is. Single-variant on purpose: there is no `Fact`
/// (or any other) variant for a caller to pick, so a default cannot be rendered
/// as a fact by accident.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DisplayKind {
    /// "참고 통계" — 출처 있는 공공 통계 값.
    ReferenceStatistic,
}

impl DisplayKind {
    /// The on-screen badge text.
    pub fn label(&self) -> &'static str {
        REFERENCE_STAT_LABEL
    }
}

/// A candidate version as it may be shown: always a reference statistic with its
/// summary and sources; the raw `value` travels for layout, the display kind is
/// fixed.
#[derive(Debug)]
pub struct CandidateDisplay<'a> {
    pub kind: DisplayKind,
    pub candidate_id: &'a str,
    pub label: &'a str,
    pub summary: &'a str,
    pub value: &'a DefaultValue,
    /// `raw:sha256:` refs of the archived statistics — the consumer can chain
    /// them into evidence views (I6).
    pub sources: &'a [CriterionSource],
}

/// Render one stored candidate version as a reference statistic — the only
/// display mode this module can produce.
pub fn display<'a>(r: CandidateVersionRef<'a>) -> CandidateDisplay<'a> {
    CandidateDisplay {
        kind: DisplayKind::ReferenceStatistic,
        candidate_id: &r.candidate.id,
        label: &r.candidate.label,
        summary: r.version.value.summary(),
        value: &r.version.value,
        sources: &r.version.sources,
    }
}

/// What an effective input is made of: the user's own assumption when present,
/// else a candidate — never an overwritten assumption.
#[derive(Debug, PartialEq)]
pub enum EffectiveDefault<'a, A> {
    /// The user stated this themselves (`user_assumption` 판, 개인 영역 — the
    /// payload type `A` stays generic here so no private-zone type is needed).
    UserAssumption(A),
    /// No assumption; the candidate may be used — still labelled "참고 통계".
    Candidate(&'a CandidateVersion),
}

/// Resolve the effective value for one input slot.
///
/// - `Some(assumption)` → the assumption. A candidate never overwrites it, even
///   when one exists (수락 기준: "사용자 가정이 있으면 기본값을 덮지 않는다").
/// - `None` + a candidate → the candidate.
/// - `None` + nothing → `None`. There is no made-up default (O05, D-08): the
///   caller must let the result hold, not fill 0 or a population average.
pub fn effective<'a, A>(
    user_assumption: Option<A>,
    candidate: Option<&'a CandidateVersion>,
) -> Option<EffectiveDefault<'a, A>> {
    match (user_assumption, candidate) {
        (Some(a), _) => Some(EffectiveDefault::UserAssumption(a)),
        (None, Some(c)) => Some(EffectiveDefault::Candidate(c)),
        (None, None) => None,
    }
}
