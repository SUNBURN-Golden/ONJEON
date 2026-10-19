//! Release snapshot reading.
//!
//! A [`Snapshot`] is what a request reads: the typed view of one frozen release plus the
//! rule bytes the release pinned. Members outside the release list are invisible, and an
//! in-place edit, a missing member or a swapped rule file surfaces in `integrity` (K15),
//! which callers should treat as findings rather than silently proceed on.

use onjeon_ontology::{candidate_view, view, Abox, Result, View};

/// A frozen release (or a not-yet-frozen candidate) as the input stage reads it.
#[derive(Debug, Clone)]
pub struct Snapshot {
    /// The release this snapshot reads, or `None` for a candidate view.
    pub release_id: Option<String>,
    view: View,
}

impl Snapshot {
    /// The frozen release `release_id` of `abox`. Members are read exactly as frozen.
    pub fn release(abox: &Abox, release_id: &str) -> Result<Snapshot> {
        Ok(Snapshot {
            release_id: Some(release_id.to_string()),
            view: view(abox, release_id)?,
        })
    }

    /// Everything stored now, unfrozen. For harnesses and tests; a release id is absent.
    pub fn candidate(abox: &Abox) -> Result<Snapshot> {
        Ok(Snapshot {
            release_id: None,
            view: candidate_view(abox)?,
        })
    }

    /// The typed release view (assertions, editions, nodes, conflicts, rule bytes).
    pub fn view(&self) -> &View {
        &self.view
    }

    /// K15 integrity findings of this read. Empty means the stored content reproduces
    /// what the release froze.
    pub fn integrity_findings(&self) -> &[onjeon_ontology::Violation] {
        &self.view.integrity
    }

    /// Bytes of a rule file pinned by this snapshot.
    pub fn rule_bytes(&self, rule_path: &str) -> Option<&[u8]> {
        self.view.rule_files.get(rule_path).map(Vec::as_slice)
    }
}
