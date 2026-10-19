//! `input_stage::fill` (C-08/C-26, ADR-0014 §4): fills declared inputs from facts and
//! input-stage judgements; what it cannot judge fails explicitly, never defaults.

mod common;
use common::*;
use onjeon_twin_runtime::*;
use serde_json::{json, Value};

/// A linked chain + rule artifact to exercise `fill` against (golden Q1 on
/// rel:declared-r26, whose rule file carries the C-08 declaration).
fn linked_and_rule() -> (Snapshot, Linked, onjeon_rules_engine::Rule) {
    let snap = declared_snapshot();
    let chain = resolve_request(&snap, &[HANA_NEW, HANA_OLD], "2026-08-20", "cov:hana_2_1");
    let l = chain.linked().expect("Q1 links").clone();
    let (rule, outside) = load_rule_artifact(snap.rule_bytes(&l.rule_path).unwrap()).unwrap();
    assert_eq!(
        outside,
        dx_outside(),
        "the artifact declares dx_in_category"
    );
    (snap, l, rule)
}

#[test]
fn fill_produces_inputs_and_the_membership_judgement() {
    let (snap, l, rule) = linked_and_rule();
    let q = question("Q1");
    let facts = facts_of(&q);
    let out = fill(
        &dx_outside(),
        &FillRequest {
            snapshot: &snap,
            linked: &l,
            rule: &rule,
            facts: &facts,
        },
    )
    .unwrap();
    // every declared input is present: judged inputs by value, the rest from facts
    for name in rule.input_types().keys() {
        assert!(out.inputs.contains_key(name), "{name}");
    }
    assert_eq!(out.inputs["dx_in_category"], json!(true));
    assert_eq!(out.inputs["contract_date"], json!("2026-08-20"));
    assert_eq!(out.inputs["insured_amount_krw"], json!(10_000_000));
    assert_eq!(out.judgements.len(), 1);
    assert!(out.judgements[0]
        .evidence_assertion_ids
        .contains(&"a:hana_cat_inc".to_string()));
}

#[test]
fn a_missing_code_fact_leaves_the_input_unknown_with_a_judgement() {
    let (snap, l, rule) = linked_and_rule();
    let mut facts = facts_of(&question("Q5")); // dx_code: null
    facts.insert("dx_code".into(), Value::Null);
    let out = fill(
        &dx_outside(),
        &FillRequest {
            snapshot: &snap,
            linked: &l,
            rule: &rule,
            facts: &facts,
        },
    )
    .unwrap();
    assert_eq!(out.inputs["dx_in_category"], Value::Null);
    assert_eq!(out.judgements[0].value, onjeon_contracts::Tri::Unknown);
    assert!(out.judgements[0].evidence_assertion_ids.is_empty());
}

#[test]
fn unsupported_judged_by_fails_explicitly() {
    let (snap, l, rule) = linked_and_rule();
    let facts = facts_of(&question("Q1"));
    let bad = vec![OutsideInput {
        name: "already_paid".to_string(),
        judged_by: JudgedBy::ContractTwin,
        evidence_required: None,
        code_fact: None,
        as_of_fact: None,
        anchor_fact: None,
        duration: None,
        anchor_day_counted: None,
        dates_facts: Vec::new(),
    }];
    let e = fill(
        &bad,
        &FillRequest {
            snapshot: &snap,
            linked: &l,
            rule: &rule,
            facts: &facts,
        },
    )
    .unwrap_err();
    assert!(matches!(e, FillError::UnsupportedJudgedBy { .. }), "{e}");
}

#[test]
fn a_declaration_naming_no_rule_input_is_rejected() {
    let (snap, l, rule) = linked_and_rule();
    let facts = facts_of(&question("Q1"));
    let bad = vec![OutsideInput {
        name: "no_such_input".to_string(),
        judged_by: JudgedBy::Ontology,
        evidence_required: None,
        code_fact: Some("dx_code".to_string()),
        as_of_fact: None,
        anchor_fact: None,
        duration: None,
        anchor_day_counted: None,
        dates_facts: Vec::new(),
    }];
    let e = fill(
        &bad,
        &FillRequest {
            snapshot: &snap,
            linked: &l,
            rule: &rule,
            facts: &facts,
        },
    )
    .unwrap_err();
    assert!(matches!(e, FillError::BadDeclaration(_)), "{e}");
}

#[test]
fn a_malformed_code_fact_is_an_error_not_a_guess() {
    let (snap, l, rule) = linked_and_rule();
    let mut facts = facts_of(&question("Q1"));
    facts.insert("dx_code".into(), json!("not-a-code"));
    let e = fill(
        &dx_outside(),
        &FillRequest {
            snapshot: &snap,
            linked: &l,
            rule: &rule,
            facts: &facts,
        },
    )
    .unwrap_err();
    assert!(matches!(e, FillError::Ontology(_)), "{e}");
}

// ---------- judge_time (C-26) ----------

#[test]
fn judge_time_day_duration_anchor_counted_and_not() {
    let d90 = TimeDuration {
        value: 90,
        unit: DurUnit::Day,
    };
    // 기산일 미산입: [2026-08-21, 2026-11-18] — anchor day outside, end inside
    let j = judge_time(
        "2026-08-20",
        &d90,
        Some(false),
        &["2026-08-20", "2026-11-18", "2026-11-19"],
    )
    .unwrap();
    assert_eq!(j.value.as_deref(), Some("2026-11-18"));
    assert_eq!(
        j.within,
        [
            onjeon_contracts::Tri::False,
            onjeon_contracts::Tri::True,
            onjeon_contracts::Tri::False
        ]
    );
    // 기산일 포함: [2026-08-20, 2026-11-17] — the golden Q3 boundary (90일 면책)
    let j = judge_time(
        "2026-08-20",
        &d90,
        Some(true),
        &["2026-11-17", "2026-11-18"],
    )
    .unwrap();
    assert_eq!(j.value.as_deref(), Some("2026-11-17"));
    assert_eq!(
        j.within,
        [onjeon_contracts::Tri::True, onjeon_contracts::Tri::False]
    );
}

#[test]
fn judge_time_records_the_assumed_counting_rule() {
    let d = TimeDuration {
        value: 90,
        unit: DurUnit::Day,
    };
    let j = judge_time("2026-08-20", &d, None, &["2026-11-18"]).unwrap();
    // the source did not say → 기산일 미산입 is assumed and said so, never silent
    assert_eq!(j.value.as_deref(), Some("2026-11-18"));
    assert_eq!(j.assumptions.len(), 1);
    assert!(j.assumptions[0].contains("기산일 미산입"));
    let j = judge_time("2026-08-20", &d, Some(false), &["2026-11-18"]).unwrap();
    assert!(j.assumptions.is_empty());
}

#[test]
fn judge_time_calendar_month_and_year_clamp() {
    // 1 month from Jan 31 clamps to Feb 28 and says so
    let m1 = TimeDuration {
        value: 1,
        unit: DurUnit::CalendarMonth,
    };
    let j = judge_time(
        "2026-01-31",
        &m1,
        Some(false),
        &["2026-02-28", "2026-03-01"],
    )
    .unwrap();
    assert_eq!(j.value.as_deref(), Some("2026-02-28"));
    assert!(j.assumptions.iter().any(|a| a.contains("마지막 날")));
    assert_eq!(
        j.within,
        [onjeon_contracts::Tri::True, onjeon_contracts::Tri::False]
    );
    // 1 calendar year, not counted
    let y1 = TimeDuration {
        value: 1,
        unit: DurUnit::CalendarYear,
    };
    let j = judge_time("2026-08-20", &y1, Some(false), &["2027-08-20"]).unwrap();
    assert_eq!(j.value.as_deref(), Some("2027-08-20"));
    assert_eq!(j.within, [onjeon_contracts::Tri::True]);
}

#[test]
fn judge_time_refuses_bad_input_and_never_guesses() {
    let d = TimeDuration {
        value: 0,
        unit: DurUnit::Day,
    };
    assert!(judge_time("2026-08-20", &d, Some(false), &[]).is_err());
    assert!(judge_time(
        "not-a-date",
        &TimeDuration {
            value: 1,
            unit: DurUnit::Day
        },
        Some(false),
        &[]
    )
    .is_err());
    // a boundary out of the supported range is unknown, not a wrong date
    let j = judge_time(
        "2199-12-31",
        &TimeDuration {
            value: 1,
            unit: DurUnit::Day,
        },
        Some(false),
        &["2200-01-01"],
    )
    .unwrap();
    assert_eq!(j.value, None);
    assert_eq!(j.within, [onjeon_contracts::Tri::Unknown]);
    // the out-of-range date itself fails to parse too — error wins over unknown
    assert!(judge_time(
        "2026-08-20",
        &TimeDuration {
            value: 1,
            unit: DurUnit::Day
        },
        Some(false),
        &["2200-01-01"]
    )
    .is_err());
}

#[test]
fn fill_time_stage_judgement_and_its_boundary_travel() {
    let (snap, l, rule) = linked_and_rule();
    let mut facts = facts_of(&question("Q1"));
    facts.insert("dx_code".into(), json!("C16"));
    let outside = vec![OutsideInput {
        name: "already_paid".to_string(),
        judged_by: JudgedBy::TimeStage,
        evidence_required: None,
        code_fact: None,
        as_of_fact: None,
        anchor_fact: Some("contract_date".to_string()),
        duration: Some(TimeDuration {
            value: 90,
            unit: DurUnit::Day,
        }),
        anchor_day_counted: Some(false),
        dates_facts: vec!["diagnosis_date".to_string()],
    }];
    let out = fill(
        &outside,
        &FillRequest {
            snapshot: &snap,
            linked: &l,
            rule: &rule,
            facts: &facts,
        },
    )
    .unwrap();
    // diagnosis 2027-04-20 is past the 90-day period → false
    assert_eq!(out.inputs["already_paid"], json!(false));
    let j = &out.judgements[0];
    assert_eq!(j.judged_by, JudgedBy::TimeStage);
    assert_eq!(j.boundary.as_deref(), Some("2026-11-18"));
    assert_eq!(j.value, onjeon_contracts::Tri::False);
}

// ---------- as_of_fact: declared dates are validated, never silently dropped ----------

#[test]
fn a_missing_as_of_fact_is_unknown_not_an_undated_answer() {
    let (snap, l, rule) = linked_and_rule();
    let mut facts = facts_of(&question("Q1"));
    facts.remove("diagnosis_date");
    let out = fill(
        &dx_outside(),
        &FillRequest {
            snapshot: &snap,
            linked: &l,
            rule: &rule,
            facts: &facts,
        },
    )
    .unwrap();
    assert_eq!(out.inputs["dx_in_category"], Value::Null);
    assert_eq!(out.judgements[0].value, onjeon_contracts::Tri::Unknown);
    assert_eq!(out.judgements[0].judged_as_of, None);
}

#[test]
fn a_malformed_as_of_fact_is_an_error_not_a_guess() {
    let (snap, l, rule) = linked_and_rule();
    for bad in [json!("not-a-date"), json!(20270420)] {
        let mut facts = facts_of(&question("Q1"));
        facts.insert("diagnosis_date".into(), bad.clone());
        let e = fill(
            &dx_outside(),
            &FillRequest {
                snapshot: &snap,
                linked: &l,
                rule: &rule,
                facts: &facts,
            },
        )
        .unwrap_err();
        assert!(matches!(e, FillError::BadFact(_)), "{bad}: {e}");
    }
}

#[test]
fn evidence_required_false_is_a_bad_declaration() {
    let (snap, l, rule) = linked_and_rule();
    let outside: Vec<OutsideInput> = serde_json::from_value(json!([{
        "name": "dx_in_category", "judged_by": "ontology",
        "code_fact": "dx_code", "evidence_required": false
    }]))
    .unwrap();
    let e = fill(
        &outside,
        &FillRequest {
            snapshot: &snap,
            linked: &l,
            rule: &rule,
            facts: &facts_of(&question("Q1")),
        },
    )
    .unwrap_err();
    assert!(matches!(e, FillError::BadDeclaration(_)), "{e}");
}

// ---------- load_rule_artifact: the declaration is part of the rule file (C-08) ----------

#[test]
fn the_artifact_carries_the_declaration_and_the_engine_never_sees_it() {
    let snap = declared_snapshot();
    let chain = resolve_request(&snap, &[HANA_NEW, HANA_OLD], "2026-08-20", "cov:hana_2_1");
    let l = chain.linked().unwrap().clone();
    let bytes = snap.rule_bytes(&l.rule_path).unwrap();
    let (rule, outside) = load_rule_artifact(bytes).unwrap();
    assert_eq!(outside, dx_outside());
    // the engine's view of the artifact is the bare rule-0.1 body
    assert!(rule.source_json().get("inputs_from_outside_dsl").is_none());
    // a file without the key declares nothing
    let plain = std::fs::read(golden_dir().join("규칙/hana-2601-3d-cancer-dx.json")).unwrap();
    let (_, outside) = load_rule_artifact(&plain).unwrap();
    assert!(outside.is_empty());
}

#[test]
fn a_stale_or_unknown_key_in_the_declaration_fails_loudly() {
    // a `category` override once existed on the request side; the artifact must not
    // silently ignore it — the category always comes from the linked coverage
    let mut v: Value =
        serde_json::from_slice(&declared_abox().rule_files["규칙/hana-2601-3d-cancer-dx.json"])
            .unwrap();
    v["inputs_from_outside_dsl"][0]["category"] = json!("cat:other");
    let e = load_rule_artifact(&serde_json::to_vec(&v).unwrap()).unwrap_err();
    assert!(e.contains("inputs_from_outside_dsl"), "{e}");
}
