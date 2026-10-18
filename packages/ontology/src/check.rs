//! Consistency constraints K1~K16 over a [`View`].
//!
//! Faithful to the T-box rules (`schemas/ontology/tbox.json`). K15 is raised while a frozen release is read
//! (`release::view`) and arrives in `View::integrity`; a candidate view has none.

use crate::edition::edition_statuses;
use crate::membership::{scope_relation, CodeUniverse, ScopeRelation};
use crate::model::{Assertion, View, SECTIONS, STRUCTURAL};
use crate::resolve::simulate_allowed;
use onjeon_contracts::checks::ORIGIN_FIXTURE;
use onjeon_contracts::ReviewStatus;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

pub const ANCHORS: [&str; 7] = [
    "계약일",
    "보장개시일",
    "갱신일",
    "부활일",
    "결과보고일",
    "진단확정일",
    "청구일",
];
pub const DURATION_UNITS: [&str; 3] = ["day", "calendar_month", "calendar_year"];
pub const PRIVATE_PREFIXES: [&str; 3] = ["contract:", "person:", "upload:"];

/// Code of the violations only the service profile raises (fixtures cannot be accepted knowledge).
pub const PROFILE_VIOLATION: &str = "PROFILE";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Violation {
    /// `K1`~`K16`, or [`PROFILE_VIOLATION`].
    pub code: String,
    pub subject: String,
    pub message: String,
}

impl Violation {
    pub fn new(code: &str, subject: &str, message: impl Into<String>) -> Violation {
        Violation {
            code: code.to_string(),
            subject: subject.to_string(),
            message: message.into(),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProfileKind {
    /// Reads the case A-box as the discussion material left it: `fixture_assumption` and `origin=fixture` are allowed.
    HistoricalFixture,
    /// What a service store accepts: fixtures are never accepted knowledge.
    ServiceConformance,
}

/// How to check. `universe` is the code universe K12 computes scope relations over; without one, scope relation
/// claims cannot be verified and an accepted one is a K12 violation.
#[derive(Debug, Clone)]
pub struct CheckProfile {
    pub kind: ProfileKind,
    pub universe: Option<CodeUniverse>,
}

impl CheckProfile {
    pub fn historical_fixture(universe: Option<CodeUniverse>) -> CheckProfile {
        CheckProfile {
            kind: ProfileKind::HistoricalFixture,
            universe,
        }
    }

    pub fn service_conformance(universe: Option<CodeUniverse>) -> CheckProfile {
        CheckProfile {
            kind: ProfileKind::ServiceConformance,
            universe,
        }
    }
}

/// All violations of K1~K16 in the view, in constraint order (K15 findings first), plus the profile's own.
pub fn check_constraints(view: &View, profile: &CheckProfile) -> Vec<Violation> {
    let mut v = view.integrity.clone();
    let terms = view.terms_clauses();
    let cur: Vec<&Assertion> = view.current().collect();
    k1_k2(&cur, &terms, &mut v);
    k3_k8_nodes(view, &cur, &mut v);
    k9(view, &cur, &mut v);
    k10_k11(view, &mut v);
    k12(view, &cur, profile, &mut v);
    k13(view, &mut v);
    k14(view, &cur, &mut v);
    k16(view, &mut v);
    if profile.kind == ProfileKind::ServiceConformance {
        profile_fixture(view, &mut v);
    }
    v
}

fn k1_k2(cur: &[&Assertion], terms: &BTreeMap<String, String>, v: &mut Vec<Violation>) {
    for a in cur {
        if a.criticality == "C0" && a.accepted() {
            if STRUCTURAL.contains(&a.predicate.as_str()) {
                if !a.evidence.iter().any(|e| e.role == "observation") {
                    v.push(Violation::new("K1", &a.id, "구조 주장에 관측 근거가 없음"));
                }
                continue;
            }
            if !a
                .evidence
                .iter()
                .any(|e| e.role == "basis" && terms.contains_key(&e.target))
            {
                v.push(Violation::new(
                    "K1",
                    &a.id,
                    "C0 accepted인데 약관 본문 판에 이어진 basis 근거가 없음",
                ));
            }
        }
    }
    for a in cur {
        if a.predicate == "same_benefit_as" {
            let docs: BTreeSet<&String> = a
                .evidence
                .iter()
                .filter(|e| e.role == "basis")
                .filter_map(|e| terms.get(&e.target))
                .collect();
            if docs.len() < 2 {
                v.push(Violation::new(
                    "K2",
                    &a.id,
                    "same_benefit_as에 양쪽 약관 대조 근거가 없음",
                ));
            }
        }
    }
}

fn duration(view: &View, node: &str) -> Option<(String, String)> {
    let d = view.node(node)?.raw.get("duration")?;
    Some((
        d.get("unit")?.as_str()?.to_string(),
        d.get("value").map(Value::to_string).unwrap_or_default(),
    ))
}

/// K3~K8 (node-level rules and the claims about them).
fn k3_k8_nodes(view: &View, cur: &[&Assertion], v: &mut Vec<Violation>) {
    for n in &view.nodes {
        if n.class == "CodeSet" {
            for k in ["code_system", "edition", "effective", "judged_as_of"] {
                if n.get_str(k).is_none() {
                    v.push(Violation::new("K3", &n.id, format!("코드 집합에 {k} 없음")));
                }
            }
        }
    }
    // K4 narrower/broader cycles of any length (edge = "is contained in")
    let mut edges: BTreeSet<(&str, &str)> = BTreeSet::new();
    for a in cur.iter().filter(|a| a.predicate == "scope_relation") {
        if let (Some(o), Some(rel)) = (a.object.as_deref(), a.value_str()) {
            match rel {
                "narrower" => edges.insert((a.subject.as_str(), o)),
                "broader" => edges.insert((o, a.subject.as_str())),
                _ => false,
            };
        }
    }
    let starts: BTreeSet<&str> = edges.iter().map(|(s, _)| *s).collect();
    for s in starts {
        let mut seen: BTreeSet<&str> = BTreeSet::new();
        let mut stack = vec![s];
        let mut cyclic = false;
        while let Some(n) = stack.pop() {
            for (_, t) in edges.range((n, "")..).take_while(|(f, _)| *f == n) {
                if *t == s {
                    cyclic = true;
                }
                if seen.insert(*t) {
                    stack.push(*t);
                }
            }
        }
        if cyclic {
            v.push(Violation::new("K4", s, "narrower/broader 순환"));
        }
    }
    // K5
    for a in &view.assertions {
        if let (Some(f), Some(t)) = (&a.valid_from, &a.valid_to) {
            if f > t {
                v.push(Violation::new("K5", &a.id, "valid_from > valid_to"));
            }
        }
    }
    for n in &view.nodes {
        if n.class == "Condition" {
            if let Some(anchor) = n.get_str("anchor") {
                if !ANCHORS.contains(&anchor) {
                    v.push(Violation::new("K5", &n.id, "기산 시점이 어휘에 없음"));
                }
            }
        }
    }
    // K6
    for n in &view.nodes {
        if n.class == "Condition" {
            if let Some(unit) = n
                .raw
                .get("duration")
                .and_then(|d| d.get("unit"))
                .and_then(Value::as_str)
            {
                if !DURATION_UNITS.contains(&unit) {
                    v.push(Violation::new(
                        "K6",
                        &n.id,
                        "기간 단위가 원문 단위 어휘에 없음",
                    ));
                }
            }
        }
    }
    for a in cur {
        if a.predicate == "same_duration_as" {
            if let (Some(d1), Some(d2)) = (
                duration(view, &a.subject),
                a.object.as_deref().and_then(|o| duration(view, o)),
            ) {
                if d1.0 != d2.0 {
                    v.push(Violation::new(
                        "K6",
                        &a.id,
                        "단위가 다른 기간을 같다고 주장",
                    ));
                }
            }
        }
    }
    // K7
    for a in cur {
        if a.predicate == "has_condition" && a.value_state == "observed" {
            if let Some(n) = a.object.as_deref().and_then(|o| view.node(o)) {
                let reduction = n.raw.get("kind").and_then(Value::as_str) == Some("감액");
                let none_value = n.raw.get("value").and_then(Value::as_str) == Some("없음");
                let has_target = match n.raw.get("applies_to") {
                    None | Some(Value::Null) => false,
                    Some(Value::String(s)) => !s.is_empty(),
                    Some(Value::Array(l)) => !l.is_empty(),
                    Some(_) => true,
                };
                if reduction && !none_value && !has_target {
                    v.push(Violation::new("K7", &a.id, "감액 적용 대상 없음"));
                }
            }
        }
    }
    // K8: nothing in the public sections names a private-zone id
    let blob: String = SECTIONS
        .iter()
        .map(|k| Value::Array(view.raw.get(*k).cloned().unwrap_or_default()).to_string())
        .collect::<Vec<_>>()
        .join("\n");
    for p in PRIVATE_PREFIXES {
        if blob.contains(p) {
            v.push(Violation::new("K8", p, "공개 영역에 개인 영역 식별자"));
        }
    }
}

/// Coverage plus the category tree below it: the claims that make up what a rule for the coverage executes.
pub(crate) fn coverage_scope<'a>(
    view: &'a View,
    cur: &[&'a Assertion],
    cov: &str,
) -> BTreeSet<String> {
    let mut covered: BTreeSet<String> = BTreeSet::new();
    covered.insert(cov.to_string());
    let mut frontier: Vec<String> = vec![cov.to_string()];
    for a in cur {
        if a.subject == cov && a.predicate == "uses_definition" {
            if let Some(o) = &a.object {
                if covered.insert(o.clone()) {
                    frontier.push(o.clone());
                }
            }
        }
    }
    while let Some(s) = frontier.pop() {
        for x in cur {
            if x.subject == s
                && (x.predicate == "includes_codes" || x.predicate == "excludes_codes")
            {
                if let Some(o) = &x.object {
                    if view.node(o).is_some_and(|n| n.class == "DiseaseCategory")
                        && covered.insert(o.clone())
                    {
                        frontier.push(o.clone());
                    }
                }
            }
        }
    }
    covered
}

fn k9(view: &View, cur: &[&Assertion], v: &mut Vec<Violation>) {
    for a in cur {
        if a.predicate != "implemented_by" || !a.accepted() {
            continue;
        }
        let Some(path) = a.rule_path.as_deref() else {
            v.push(Violation::new(
                "K9",
                &a.id,
                "implemented_by에 rule_path 없음",
            ));
            continue;
        };
        let refs: Result<BTreeSet<String>, String> = match view.rule_files.get(path) {
            None => Err(format!("규칙 파일 없음: {path}")),
            Some(bytes) => serde_json::from_slice::<Value>(bytes)
                .map_err(|e| format!("규칙 파일을 읽을 수 없음: {e}"))
                .and_then(|r| match r.get("evidence_refs").and_then(Value::as_array) {
                    Some(l) => Ok(l
                        .iter()
                        .filter_map(|x| x.as_str().map(str::to_string))
                        .collect()),
                    None => Err("규칙에 evidence_refs 없음".to_string()),
                }),
        };
        let refs = match refs {
            Ok(r) => r,
            Err(m) => {
                v.push(Violation::new("K9", &a.id, m));
                continue;
            }
        };
        let covered = coverage_scope(view, cur, &a.subject);
        let basis: BTreeSet<&str> = cur
            .iter()
            .filter(|x| covered.contains(&x.subject) && x.criticality == "C0" && x.accepted())
            .flat_map(|x| {
                x.evidence
                    .iter()
                    .filter(|e| e.role == "basis")
                    .map(|e| e.target.as_str())
            })
            .collect();
        let extra: Vec<&str> = refs
            .iter()
            .map(String::as_str)
            .filter(|r| !basis.contains(r))
            .collect();
        if !extra.is_empty() {
            v.push(Violation::new(
                "K9",
                &a.id,
                format!("규칙 근거가 담보의 C0 basis 밖: {}", extra.join(",")),
            ));
        }
    }
}

fn k10_k11(view: &View, v: &mut Vec<Violation>) {
    let mut targets: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
    for a in &view.assertions {
        if let Some(t) = &a.supersedes {
            targets.entry(t).or_default().push(&a.id);
        }
    }
    for (t, ss) in &targets {
        if ss.len() > 1
            && !view
                .conflicts
                .iter()
                .any(|c| ss.iter().all(|s| c.assertions.iter().any(|x| x == s)))
        {
            v.push(Violation::new(
                "K10",
                t,
                "같은 주장을 둘이 대체하는데 충돌 기록 없음",
            ));
        }
    }
    for n in view
        .nodes
        .iter()
        .filter(|n| n.class == "CoverageOccurrence")
    {
        if view.declared_capabilities.get(&n.id).map(String::as_str) == Some("enabled")
            && !simulate_allowed(view, &n.id).0
        {
            v.push(Violation::new(
                "K11",
                &n.id,
                "hold·충돌이 있는데 simulate enabled",
            ));
        }
    }
}

fn k12(view: &View, cur: &[&Assertion], profile: &CheckProfile, v: &mut Vec<Violation>) {
    for a in cur {
        if a.predicate != "scope_relation" {
            continue;
        }
        let Some(obj) = a.object.as_deref() else {
            continue;
        };
        match scope_relation(view, &a.subject, obj, profile.universe.as_ref()) {
            Ok(ScopeRelation::NotComparable) => {
                if a.accepted() {
                    v.push(Violation::new(
                        "K12",
                        &a.id,
                        "계산할 수 없는 쌍의 범위 관계가 accepted",
                    ));
                }
            }
            Ok(got) => {
                if Some(got.as_str()) != a.value_str() {
                    v.push(Violation::new(
                        "K12",
                        &a.id,
                        format!(
                            "주장 {} ≠ 계산 {}",
                            a.value_str().unwrap_or("None"),
                            got.as_str()
                        ),
                    ));
                }
            }
            Err(e) => v.push(Violation::new(
                "K12",
                &a.id,
                format!("범위 관계를 계산할 수 없음: {e}"),
            )),
        }
    }
}

fn k13(view: &View, v: &mut Vec<Violation>) {
    for p in view.raw.get("premium_observations").into_iter().flatten() {
        if p.get("comparison_eligible").and_then(Value::as_bool) == Some(true) {
            let id = p.get("id").and_then(Value::as_str).unwrap_or("?");
            for k in ["conditions", "package_binding", "as_of"] {
                let empty = match p.get(k) {
                    None | Some(Value::Null) => true,
                    Some(Value::String(s)) => s.is_empty(),
                    Some(Value::Array(l)) => l.is_empty(),
                    Some(Value::Object(o)) => o.is_empty(),
                    Some(_) => false,
                };
                if empty {
                    v.push(Violation::new(
                        "K13",
                        id,
                        format!("비교 자격이 있는 가격 관측에 {k} 없음"),
                    ));
                }
            }
        }
    }
}

fn k14(view: &View, cur: &[&Assertion], v: &mut Vec<Violation>) {
    for a in cur {
        if a.predicate != "realizes" || !a.accepted() {
            continue;
        }
        let seg = view.segment(&a.subject);
        if seg.and_then(|s| s.fingerprint.as_ref()).is_none() {
            v.push(Violation::new(
                "K14",
                &a.id,
                "본문 지문 없는 구획으로 본문 판을 확정",
            ));
        } else if !a
            .evidence
            .iter()
            .any(|e| e.role == "observation" && e.target == a.subject)
        {
            v.push(Violation::new(
                "K14",
                &a.id,
                "구획 관측 근거 없이 본문 판을 확정",
            ));
        } else if !matches!(
            a.decision_by(),
            Some("review_decision") | Some("fixture_assumption")
        ) {
            v.push(Violation::new(
                "K14",
                &a.id,
                format!(
                    "승인 결정이 검수 결정이 아님({})",
                    a.decision_by().unwrap_or("None")
                ),
            ));
        }
    }
}

fn k16(view: &View, v: &mut Vec<Violation>) {
    for st in edition_statuses(view) {
        for m in &st.mismatch {
            v.push(Violation::new(
                "K16",
                &m.assertion_id,
                format!(
                    "{}: 검수 결정 없이 같은 판으로 승인할 수 없음",
                    m.describe()
                ),
            ));
        }
        if !st.accepted_realizes.is_empty() && !st.missing_parts.is_empty() {
            v.push(Violation::new(
                "K16",
                &st.edition,
                format!(
                    "근거 묶음이 판의 구성 {}개를 덮지 못함(동일성 미확인, hold여야 함)",
                    st.missing_parts.len()
                ),
            ));
        }
    }
}

/// Service profile: any accepted claim that is a fixture (`origin=fixture`) or rests on a test-only
/// assumption (`decision.by=fixture_assumption`) is listed. All claims count, not only current ones.
fn profile_fixture(view: &View, v: &mut Vec<Violation>) {
    for a in &view.assertions {
        if a.review_status != ReviewStatus::Accepted {
            continue;
        }
        if a.origin.as_deref() == Some(ORIGIN_FIXTURE) {
            v.push(Violation::new(
                PROFILE_VIOLATION,
                &a.id,
                "origin=fixture인 주장은 서비스에서 accepted일 수 없음",
            ));
        } else if a.decision_by() == Some("fixture_assumption") {
            v.push(Violation::new(
                PROFILE_VIOLATION,
                &a.id,
                "fixture_assumption 결정은 서비스에서 accepted일 수 없음",
            ));
        }
    }
}
