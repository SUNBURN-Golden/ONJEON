//! Sales-configuration selection (02_구현계약 §1.7 step 1).
//!
//! A request names candidate sales configurations; exactly one may apply on the contract
//! date. A candidate *applies* when at least one `uses_edition` link of it is in force on
//! that date (inclusive ends) — whatever the link's review status, since an unconfirmed
//! link can still mean the configuration applies. Ambiguity is only *several applicable
//! configurations*; one configuration using several terms editions is normal (S01).
//! Candidates are deduplicated and sorted by id, so the result never depends on the
//! order the caller passed them in.

use crate::snapshot::Snapshot;
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};

/// A `uses_edition` assertion the selection looked at: which configuration it belongs to,
/// its review status, and whether its validity period covers the contract date.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct HeldLink {
    pub sales_config: String,
    pub assertion_id: String,
    /// The link's review status (`accepted`, `hold`, `pending`, `rejected`).
    pub status: String,
    /// Whether the link's validity period covers the contract date.
    pub applies_on_date: bool,
}

/// Why no single sales configuration could be selected.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "reason", rename_all = "snake_case")]
pub enum ConfigBlock {
    /// Several candidate configurations apply on the contract date (E3).
    MultipleCandidates {
        /// The applicable configurations, sorted by id.
        candidates: Vec<String>,
        /// The links that keep each of them applicable.
        held: Vec<HeldLink>,
    },
    /// No candidate has a `uses_edition` link in force on the contract date.
    NoApplicableConfig {
        /// The links the candidates carry; `applies_on_date`/`status` say why none counted.
        held: Vec<HeldLink>,
    },
}

impl ConfigBlock {
    /// The block reason this maps to once the chain runs.
    pub fn reason(&self) -> crate::resolve::BlockReason {
        match self {
            ConfigBlock::MultipleCandidates { .. } => {
                crate::resolve::BlockReason::MultipleCandidates
            }
            ConfigBlock::NoApplicableConfig { .. } => crate::resolve::BlockReason::NoUsesEdition,
        }
    }

    /// The held links of this block, whatever the reason.
    pub fn held(&self) -> &[HeldLink] {
        match self {
            ConfigBlock::MultipleCandidates { held, .. }
            | ConfigBlock::NoApplicableConfig { held } => held,
        }
    }
}

/// The outcome of [`config_select`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConfigSelection {
    /// Exactly one candidate applies on the contract date.
    Selected {
        /// The selected sales configuration id.
        sales_config: String,
        /// Its `uses_edition` links in force on the date, sorted by assertion id.
        link_assertions: Vec<String>,
    },
    /// Selection is blocked; the affected conclusions hold, the engine is not called.
    Blocked(ConfigBlock),
}

/// Selects the sales configuration applicable on `contract_date` (`YYYY-MM-DD`).
pub fn config_select(snap: &Snapshot, candidates: &[&str], contract_date: &str) -> ConfigSelection {
    let candidates: BTreeSet<&str> = candidates.iter().copied().collect();
    // (sales configuration, assertion id) -> assertion; the map key fixes a stable order.
    let mut in_force: BTreeMap<(&str, &str), &onjeon_ontology::Assertion> = BTreeMap::new();
    let mut held: Vec<HeldLink> = Vec::new();
    for sc in &candidates {
        for a in snap
            .view()
            .current()
            .filter(|a| a.subject == *sc && a.predicate == "uses_edition")
        {
            let applies = a.valid_on(contract_date);
            if applies {
                in_force.insert((sc, a.id.as_str()), a);
            }
            held.push(HeldLink {
                sales_config: sc.to_string(),
                assertion_id: a.id.clone(),
                status: a.review_status.as_str().to_string(),
                applies_on_date: applies,
            });
        }
    }
    held.sort_by(|x, y| {
        (&x.sales_config, &x.assertion_id).cmp(&(&y.sales_config, &y.assertion_id))
    });
    let applicable: BTreeSet<&str> = in_force.keys().map(|(sc, _)| *sc).collect();
    match applicable.len() {
        0 => ConfigSelection::Blocked(ConfigBlock::NoApplicableConfig { held }),
        1 => {
            let sc = *applicable.iter().next().expect("one");
            ConfigSelection::Selected {
                sales_config: sc.to_string(),
                link_assertions: in_force
                    .values()
                    .filter(|a| a.subject == sc)
                    .map(|a| a.id.clone())
                    .collect(),
            }
        }
        _ => ConfigSelection::Blocked(ConfigBlock::MultipleCandidates {
            candidates: applicable.iter().map(|s| s.to_string()).collect(),
            held: held.into_iter().filter(|h| h.applies_on_date).collect(),
        }),
    }
}
