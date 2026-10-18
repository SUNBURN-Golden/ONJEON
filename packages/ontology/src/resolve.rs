//! Input-stage link check (C-26, 02_구현계약 §1.7) and the simulate capability test.
//!
//! `resolve_chain` walks sales configuration → applied edition → edition identity → coverage → rule, and
//! blocks (zero engine calls) whenever a link is missing, ambiguous or unconfirmed. The requested coverage is
//! never trusted on its own: it must be defined in an edition the sales configuration uses.

use crate::check::coverage_scope;
use crate::edition::{edition_status, EditionState};
use crate::model::{Assertion, View};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BlockReason {
    NoUsesEdition,
    MultipleCandidates,
    ScopeUnknown,
    ApplicationScopeUnverified,
    AppliesFromOtherEditionUnmodeled,
    CompetingEditions,
    LinkUnapproved,
    EditionIdentityUnconfirmed,
    CovNotInEdition,
    NoRule,
    /// The coverage has unaccepted C0 claims or an unresolved conflict (K11).
    SimulateBlocked,
}

impl BlockReason {
    pub fn as_str(self) -> &'static str {
        match self {
            BlockReason::NoUsesEdition => "no_uses_edition",
            BlockReason::MultipleCandidates => "multiple_candidates",
            BlockReason::ScopeUnknown => "scope_unknown",
            BlockReason::ApplicationScopeUnverified => "application_scope_unverified",
            BlockReason::AppliesFromOtherEditionUnmodeled => "applies_from_other_edition_unmodeled",
            BlockReason::CompetingEditions => "competing_editions",
            BlockReason::LinkUnapproved => "link_unapproved",
            BlockReason::EditionIdentityUnconfirmed => "edition_identity_unconfirmed",
            BlockReason::CovNotInEdition => "cov_not_in_edition",
            BlockReason::NoRule => "no_rule",
            BlockReason::SimulateBlocked => "simulate_blocked",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Linked {
    pub sales_config: String,
    pub edition: String,
    pub coverage: String,
    /// The disease category the coverage's payout reason uses (`uses_definition`), if any.
    pub category: Option<String>,
    /// The accepted `implemented_by` assertion and the rule file it names.
    pub rule_assertion: String,
    pub rule_path: String,
    /// The `uses_edition` assertions that tie the sales configuration to the edition.
    pub link_assertions: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Blocked {
    pub reason: BlockReason,
    /// What held the conclusion back (assertion ids with status, unmet conditions).
    pub held: Vec<String>,
    pub sales_config: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Chain {
    Linked(Linked),
    Blocked(Blocked),
}

impl Chain {
    pub fn linked(&self) -> Option<&Linked> {
        match self {
            Chain::Linked(l) => Some(l),
            Chain::Blocked(_) => None,
        }
    }

    pub fn blocked(&self) -> Option<&Blocked> {
        match self {
            Chain::Blocked(b) => Some(b),
            Chain::Linked(_) => None,
        }
    }
}

fn block(reason: BlockReason, held: Vec<String>, sc: Option<&str>) -> Chain {
    Chain::Blocked(Blocked {
        reason,
        held,
        sales_config: sc.map(str::to_string),
    })
}

/// May the coverage be simulated: all C0 claims around it accepted, a rule implements it, no open conflict.
/// Returns the reasons when not.
pub fn simulate_allowed(view: &View, cov: &str) -> (bool, Vec<String>) {
    let cur: Vec<&Assertion> = view.current().collect();
    let scope = coverage_scope(view, &cur, cov);
    let mut bad: Vec<String> = cur
        .iter()
        .filter(|a| scope.contains(&a.subject) && a.criticality == "C0" && !a.accepted())
        .map(|a| format!("{}:{}", a.id, a.review_status.as_str()))
        .collect();
    if !cur
        .iter()
        .any(|a| a.subject == cov && a.predicate == "implemented_by" && a.accepted())
    {
        bad.push("implemented_by 없음".to_string());
    }
    let about: BTreeSet<&str> = cur
        .iter()
        .filter(|a| a.subject == cov)
        .map(|a| a.id.as_str())
        .collect();
    if view.conflicts.iter().any(|c| {
        c.state.as_deref() != Some("resolved")
            && c.assertions.iter().any(|x| about.contains(x.as_str()))
    }) {
        bad.push("미해소 충돌".to_string());
    }
    (bad.is_empty(), bad)
}

/// Links a request (candidate sales configurations, contract date, requested coverage) to a rule or blocks it.
/// The result does not depend on the order of `configs` or of the stored assertions.
pub fn resolve_chain(view: &View, configs: &[&str], as_of: &str, requested_cov: &str) -> Chain {
    let cur: Vec<&Assertion> = view.current().collect();
    let cfg_set: BTreeSet<&str> = configs.iter().copied().collect();
    // links in force on the contract date: (sales config, uses_edition assertion)
    let mut hits: Vec<(&str, &Assertion)> = Vec::new();
    for sc in &cfg_set {
        for a in &cur {
            if a.subject == *sc && a.predicate == "uses_edition" && a.valid_on(as_of) {
                hits.push((sc, a));
            }
        }
    }
    if hits.is_empty() {
        return block(
            BlockReason::NoUsesEdition,
            vec!["판매본 미확인".to_string()],
            None,
        );
    }
    let found: BTreeSet<&str> = hits.iter().map(|(sc, _)| *sc).collect();
    if found.len() > 1 {
        // ambiguity is "several sales configurations"; one configuration using several editions is normal
        return block(
            BlockReason::MultipleCandidates,
            vec![format!(
                "판매본 후보 복수: {}",
                found.iter().copied().collect::<Vec<_>>().join(",")
            )],
            None,
        );
    }
    let sc = *found.iter().next().expect("non-empty");
    let sc_opt = Some(sc);

    let cov_eds: BTreeSet<&str> = cur
        .iter()
        .filter(|a| a.subject == requested_cov && a.predicate == "in_edition" && a.accepted())
        .filter_map(|a| a.object.as_deref())
        .collect();
    let mut used: BTreeMap<Option<&str>, Vec<&Assertion>> = BTreeMap::new();
    for (_, a) in &hits {
        used.entry(a.object.as_deref()).or_default().push(a);
    }
    let by_id = |l: &mut Vec<&Assertion>| l.sort_by(|x, y| x.id.cmp(&y.id));
    for l in used.values_mut() {
        by_id(l);
    }
    let cand: Vec<&str> = cov_eds
        .iter()
        .copied()
        .filter(|e| used.contains_key(&Some(*e)))
        .collect();
    let unresolved: Vec<&Assertion> = used
        .iter()
        .flat_map(|(ed, l)| {
            l.iter()
                .filter(move |a| ed.is_none() || !a.accepted())
                .copied()
        })
        .collect();

    // a link whose edition is unknown cannot be shown unrelated to the requested coverage
    if let Some(unknown) = used.get(&None) {
        return block(
            BlockReason::ScopeUnknown,
            unknown
                .iter()
                .map(|a| format!("{}:scope_unknown", a.id))
                .collect(),
            sc_opt,
        );
    }
    let used_eds: Vec<&str> = used.keys().filter_map(|k| *k).collect();
    if cand.is_empty() {
        if !unresolved.is_empty() {
            let mut held: Vec<String> = unresolved
                .iter()
                .map(|a| format!("{}:{}", a.id, a.review_status.as_str()))
                .collect();
            held.sort();
            return block(BlockReason::LinkUnapproved, held, sc_opt);
        }
        return block(
            BlockReason::CovNotInEdition,
            vec![format!("{requested_cov}∉{used_eds:?}")],
            sc_opt,
        );
    }
    if cand.len() > 1 {
        return block(
            BlockReason::CompetingEditions,
            vec![format!("{requested_cov}: 판 후보 복수 {cand:?}")],
            sc_opt,
        );
    }
    let ed = cand[0];
    let links = &used[&Some(ed)];
    if links.iter().any(|a| !a.accepted()) {
        let held = links
            .iter()
            .filter(|a| !a.accepted())
            .map(|a| format!("{}:{}", a.id, a.review_status.as_str()))
            .collect();
        return block(BlockReason::LinkUnapproved, held, sc_opt);
    }
    let identity = edition_status(view, ed)
        .map(|s| s.state)
        .unwrap_or(EditionState::IdentityUnconfirmed);
    if identity != EditionState::Confirmed {
        return block(
            BlockReason::EditionIdentityUnconfirmed,
            vec![format!("{ed}:identity_unconfirmed")],
            sc_opt,
        );
    }

    // where an edition is defined (in_edition) differs from where it applies (applies_to)
    let rule_a = cur
        .iter()
        .find(|a| a.subject == requested_cov && a.predicate == "implemented_by" && a.accepted());
    let covered_eds: BTreeSet<String> = match rule_a.and_then(|a| a.covers_editions.clone()) {
        Some(l) => l.into_iter().collect(),
        None => [ed.to_string()].into_iter().collect(),
    };
    let applies: Vec<&&Assertion> = cur
        .iter()
        .filter(|a| a.predicate == "applies_to" && a.object.as_deref() == Some(requested_cov))
        .collect();
    let mut pending: Vec<&&&Assertion> = applies.iter().filter(|a| !a.accepted()).collect();
    pending.sort_by(|x, y| x.id.cmp(&y.id));
    if !pending.is_empty() {
        return block(
            BlockReason::ApplicationScopeUnverified,
            pending
                .iter()
                .map(|a| format!("{}:applies_unconfirmed", a.id))
                .collect(),
            sc_opt,
        );
    }
    let mut unmodeled: Vec<&str> = applies
        .iter()
        .map(|a| a.subject.as_str())
        .filter(|s| !covered_eds.contains(*s))
        .collect();
    unmodeled.sort();
    if !unmodeled.is_empty() {
        return block(
            BlockReason::AppliesFromOtherEditionUnmodeled,
            unmodeled
                .iter()
                .map(|e| format!("{e}:applies_from_other_edition_unmodeled"))
                .collect(),
            sc_opt,
        );
    }
    let others: Vec<&str> = used_eds.iter().copied().filter(|e| *e != ed).collect();
    if !others.is_empty() {
        let complete = cur.iter().any(|a| {
            a.subject == sc
                && a.predicate == "application_scope_complete"
                && a.accepted()
                && a.value == Some(serde_json::Value::Bool(true))
        });
        if !complete {
            return block(
                BlockReason::ApplicationScopeUnverified,
                vec![format!("{sc}:application_scope_unverified")],
                sc_opt,
            );
        }
    }

    let (ok, why) = simulate_allowed(view, requested_cov);
    if !ok {
        let reason = if why.iter().all(|w| w == "implemented_by 없음") {
            BlockReason::NoRule
        } else {
            BlockReason::SimulateBlocked
        };
        return block(reason, why, sc_opt);
    }
    let Some(rule_a) = rule_a else {
        return block(
            BlockReason::NoRule,
            vec!["implemented_by 없음".to_string()],
            sc_opt,
        );
    };
    let Some(rule_path) = rule_a.rule_path.clone() else {
        return block(
            BlockReason::NoRule,
            vec![format!("{}:rule_path 없음", rule_a.id)],
            sc_opt,
        );
    };
    let category = cur
        .iter()
        .find(|a| a.subject == requested_cov && a.predicate == "uses_definition")
        .and_then(|a| a.object.clone());
    Chain::Linked(Linked {
        sales_config: sc.to_string(),
        edition: ed.to_string(),
        coverage: requested_cov.to_string(),
        category,
        rule_assertion: rule_a.id.clone(),
        rule_path,
        link_assertions: links.iter().map(|a| a.id.clone()).collect(),
    })
}
