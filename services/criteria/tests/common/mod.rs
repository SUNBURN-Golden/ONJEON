//! Shared builders for the criteria test suite. Test material is `origin=fixture`
//! unless a test builds a pipeline store on purpose.
//!
//! Each integration test is its own binary; not every helper is used by every binary.
#![allow(dead_code)]

use onjeon_contracts::{AssertionOrigin, CorrectionReason, CriterionSourceKind};
use onjeon_criteria::*;
use serde_json::json;

pub const RAW_REF: &str =
    "raw:sha256:052dd4693601b0f5d4bf9ffb5b1f3bc47b39be0c9ad6706b36eaeb6929be4032";
pub const OBS_REF: &str = "obs:src:klia/pub/1/2026-10-09T04:22:22Z/052d0204c9bc1cd1";
pub const CLAUSE_REF: &str =
    "clause:seg:052dd4693601:p1-3:terms:seg-0.1/art_10#p2:docproc-text@1.0";

pub fn criterion(id: &str, kind: CriterionKind) -> Criterion {
    Criterion {
        id: id.to_string(),
        kind,
        label: format!("{id} label"),
        scope: CriterionScope {
            situations: vec!["소득 중단".into()],
            subjects: vec!["부양가족 있음".into()],
        },
        recorded_at: "2026-10-20T00:00:00Z".into(),
    }
}

pub fn source(ref_: &str, kind: CriterionSourceKind) -> CriterionSource {
    CriterionSource {
        ref_: ref_.to_string(),
        evidence_kind: kind,
    }
}

pub fn version(criterion_id: &str, n: u32) -> CriterionVersion {
    CriterionVersion {
        id: format!("{criterion_id}@{n}"),
        criterion_id: criterion_id.to_string(),
        version: n,
        valid_from: "2026-10-20".into(),
        valid_to: None,
        sources: vec![source(RAW_REF, CriterionSourceKind::TermsFact)],
        rationale: "첫 판".into(),
        recorded_at: "2026-10-20T00:00:00Z".into(),
        supersedes: (n > 1).then(|| format!("{criterion_id}@{}", n - 1)),
        correction_reason: (n > 1).then_some(CorrectionReason::ErrorCorrection),
        origin: AssertionOrigin::Pipeline,
    }
}

/// One-criterion pipeline store with `n` versions of `crit:a` (each superseding the last).
pub fn store_with(n: u32) -> CriterionStore {
    let mut s = CriterionStore::new();
    s.insert_criterion(criterion("crit:a", CriterionKind::PriorityRule))
        .unwrap();
    for v in 1..=n {
        s.insert_version(version("crit:a", v)).unwrap();
    }
    s
}

/// A full criterion-file JSON (`{criterion, versions[]}`) as a string.
pub fn file_json(over: &serde_json::Value) -> String {
    let mut base = json!({
        "criterion": {
            "id": "crit:file-a",
            "kind": "question_rule",
            "label": "부양가족 여부를 묻는다",
            "scope": {"situations": ["필요성 판단"], "subjects": ["전체"]},
            "recorded_at": "2026-10-20T00:00:00Z"
        },
        "versions": [{
            "version": 1,
            "valid_from": "2026-10-20",
            "sources": [{"ref": OBS_REF, "evidence_kind": "public_statistic"}],
            "rationale": "첫 판",
            "recorded_at": "2026-10-20T00:00:00Z",
            "origin": "fixture"
        }]
    });
    merge(&mut base, over);
    base.to_string()
}

fn merge(base: &mut serde_json::Value, over: &serde_json::Value) {
    match (base, over) {
        (serde_json::Value::Object(b), serde_json::Value::Object(o)) => {
            for (k, v) in o {
                merge(b.entry(k.clone()).or_insert(serde_json::Value::Null), v);
            }
        }
        (serde_json::Value::Array(b), serde_json::Value::Array(o)) => {
            for (i, v) in o.iter().enumerate() {
                if i < b.len() {
                    merge(&mut b[i], v);
                } else {
                    b.push(v.clone());
                }
            }
        }
        (b, o) => *b = o.clone(),
    }
}
