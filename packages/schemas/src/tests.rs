use crate::checks::*;
use crate::*;
use serde::{de::DeserializeOwned, Serialize};
use serde_json::{json, Value};
use std::path::PathBuf;

macro_rules! fixture {
    ($name:literal) => {
        include_str!(concat!(
            "../codegen/tests/fixtures/",
            $name,
            ".fixture.json"
        ))
    };
}

fn schemas_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

/// JSON has one number type: `12` and `12.0` are the same value (display-only 만원 fields are f64).
fn canon(v: Value) -> Value {
    match v {
        Value::Number(n) => json!(n.as_f64().unwrap()),
        Value::Array(a) => Value::Array(a.into_iter().map(canon).collect()),
        Value::Object(o) => Value::Object(o.into_iter().map(|(k, v)| (k, canon(v))).collect()),
        other => other,
    }
}

/// Parse into the typed contract and back; nothing may be lost, renamed or added.
fn round_trip<T: DeserializeOwned + Serialize>(src: &str) -> T {
    let original: Value = serde_json::from_str(src).unwrap();
    let typed: T = serde_json::from_value(original.clone())
        .unwrap_or_else(|e| panic!("fixture does not deserialize: {e}"));
    assert_eq!(
        canon(serde_json::to_value(&typed).unwrap()),
        canon(original),
        "round trip changed the document"
    );
    typed
}

#[test]
fn every_fixture_round_trips_through_its_type() {
    round_trip::<Assertion>(fixture!("Assertion.relation"));
    round_trip::<Assertion>(fixture!("Assertion.value"));
    round_trip::<ReleaseManifest>(fixture!("ReleaseManifest"));
    round_trip::<EvaluationResult>(fixture!("EvaluationResult.payable"));
    round_trip::<EvaluationResult>(fixture!("EvaluationResult.undetermined"));
    round_trip::<ScenarioResult>(fixture!("ScenarioResult.evaluated"));
    round_trip::<ScenarioResult>(fixture!("ScenarioResult.blocked"));
    round_trip::<CoverageDetail>(fixture!("CoverageDetail"));
    round_trip::<CompareView>(fixture!("CompareView"));
    round_trip::<PlanView>(fixture!("PlanView"));
    round_trip::<EvidenceView>(fixture!("EvidenceView"));
    round_trip::<NeedResult>(fixture!("NeedResult"));
    round_trip::<PremiumObservation>(fixture!("PremiumObservation.raw"));
    round_trip::<PremiumObservation>(fixture!("PremiumObservation.full"));
    round_trip::<ContractSnapshot>(fixture!("ContractSnapshot"));
    round_trip::<ErrorResponse>(fixture!("ErrorResponse"));
}

#[test]
fn unknown_enum_values_are_errors_not_defaults() {
    let mut a: Value = serde_json::from_str(fixture!("Assertion.relation")).unwrap();
    a["criticality"] = json!("c9");
    assert!(serde_json::from_value::<Assertion>(a).is_err());

    let mut p: Value = serde_json::from_str(fixture!("PlanView")).unwrap();
    p["groups"][0]["plan_action"] = json!("estimated");
    assert!(serde_json::from_value::<PlanView>(p).is_err());

    // a retired price basis stays rejected
    let mut o: Value = serde_json::from_str(fixture!("PremiumObservation.raw")).unwrap();
    o["price_basis"] = json!("estimated_range");
    assert!(serde_json::from_value::<PremiumObservation>(o).is_err());
}

#[test]
fn missing_required_field_is_an_error() {
    let mut a: Value = serde_json::from_str(fixture!("Assertion.relation")).unwrap();
    a.as_object_mut().unwrap().remove("evidence");
    assert!(serde_json::from_value::<Assertion>(a).is_err());

    // release_id is required even though it may be null on an evaluation result
    let mut e: Value = serde_json::from_str(fixture!("EvaluationResult.payable")).unwrap();
    assert!(e["release_id"].is_null());
    e["release_id"] = json!(5);
    assert!(serde_json::from_value::<EvaluationResult>(e.clone()).is_err());
    // null is a value; an absent key is not
    e.as_object_mut().unwrap().remove("release_id");
    assert!(serde_json::from_value::<EvaluationResult>(e).is_err());
}

#[test]
fn unknown_fields_are_ignored_so_minor_additions_do_not_break_old_clients() {
    let mut a: Value = serde_json::from_str(fixture!("Assertion.relation")).unwrap();
    a["added_in_a_later_minor"] = json!(true);
    let typed: Assertion = serde_json::from_value(a).unwrap();
    assert_eq!(typed.criticality, Criticality::C0);
}

#[test]
fn generated_enums_equal_the_vocabulary_exactly() {
    let path = schemas_dir().join("vocabulary.json");
    let vocab: Value = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
    assert_eq!(VOCABULARY_VERSION, vocab["version"].as_str().unwrap());
    let from_json: Vec<(String, Vec<String>)> = vocab["axes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|a| {
            (
                a["id"].as_str().unwrap().to_string(),
                a["values"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v["code"].as_str().unwrap().to_string())
                    .collect(),
            )
        })
        .collect();
    let generated: Vec<(String, Vec<String>)> = axes()
        .into_iter()
        .map(|(id, codes)| {
            (
                id.to_string(),
                codes.into_iter().map(str::to_string).collect(),
            )
        })
        .collect();
    assert_eq!(generated, from_json, "generated code is stale: run gen.sh");
}

#[test]
fn enum_serialization_uses_the_vocabulary_code() {
    assert_eq!(serde_json::to_string(&Tri::True).unwrap(), "\"true\"");
    assert_eq!(
        serde_json::to_string(&PriceBasis::TableDerived).unwrap(),
        "\"table_derived\""
    );
    assert_eq!(DiffType::NewWaiting.as_str(), "new_waiting");
}

#[test]
fn generated_files_are_up_to_date() {
    let status = std::process::Command::new("python3")
        .arg("-I")
        .arg(schemas_dir().join("codegen/gen.py"))
        .arg("--check")
        .status()
        .expect("python3 is required to check generated files");
    assert!(
        status.success(),
        "generated files are stale: run `bash packages/schemas/codegen/gen.sh`"
    );
}

#[test]
fn python_codegen_suite_passes() {
    let status = std::process::Command::new("python3")
        .args(["-I", "-m", "unittest", "discover", "-s"])
        .arg(schemas_dir().join("codegen/tests"))
        .status()
        .expect("python3 is required to run the codegen suite");
    assert!(status.success(), "packages/schemas/codegen/tests failed");
}

/// A deleted field must fail the compatibility check (structural diff and compile probe).
#[test]
fn compat_check_selftest_detects_a_deleted_field() {
    let status = std::process::Command::new("bash")
        .arg(schemas_dir().join("codegen/check_compat.sh"))
        .arg("--selftest")
        .status()
        .expect("bash is required to run the compat self-test");
    assert!(status.success(), "check_compat.sh --selftest failed");
}

#[test]
fn contracts_version_matches_the_generated_clients() {
    let ts =
        std::fs::read_to_string(schemas_dir().join("codegen/generated/ts/package.json")).unwrap();
    assert!(ts.contains(&format!("\"version\": \"{CONTRACTS_VERSION}\"")));
}

// ---- wire compatibility with the real rule engine -----------------------

#[test]
fn rule_engine_output_deserializes_into_evaluation_result() {
    use onjeon_rules_engine::Rule;
    let dir = schemas_dir().join("../fixtures/rules");
    let mut checked = 0;
    let mut with_effect = 0;
    for rule_file in [
        "fixture-rule-001",
        "real/kyobo-cancer-main-dx",
        "real/kb-driver-fine",
    ] {
        let rule_src = std::fs::read_to_string(dir.join(format!("{rule_file}.json"))).unwrap();
        let rule = Rule::from_json_str(&rule_src).unwrap();
        let cases: Value = serde_json::from_str(
            &std::fs::read_to_string(dir.join(format!("{rule_file}.cases.json"))).unwrap(),
        )
        .unwrap();
        for case in cases["cases"].as_array().unwrap() {
            let Ok(result) = rule.evaluate(&case["inputs"]) else {
                continue;
            };
            let wire = serde_json::to_string(&result).unwrap();
            let typed = round_trip::<EvaluationResult>(&wire);
            assert_eq!(
                check_evaluation_result(&typed),
                vec![],
                "engine result breaks a contract invariant: {wire}"
            );
            if let Some(ce) = &typed.contract_effect {
                assert_eq!(
                    ce.kind, CONTRACT_EFFECT_NONE,
                    "fixture rules are rule-0.1: no effect declared"
                );
                with_effect += 1;
            }
            checked += 1;
        }
    }
    assert!(checked >= 10, "expected many engine results, got {checked}");
    assert!(
        with_effect == 0 || with_effect == checked,
        "an engine build reports contract_effect on every result or on none ({with_effect}/{checked})"
    );
}

/// `applies` and `undetermined` effects come only from rule-0.2 rules.
///
/// An engine build without rule-0.2 (this branch forked before PR #105 landed on `main`) rejects
/// the probe rule. The test then checks nothing beyond the reason for the rejection and returns:
/// it is vacuous on such a build and says so. It runs in full against the engine on `main`, which
/// CI builds (the PR merged with `main`). `ONJ_REQUIRE_RULE_02=1` turns the skip into a failure.
#[test]
fn rule_02_contract_effects_round_trip_when_the_engine_supports_them() {
    use onjeon_rules_engine::Rule;
    let rule = json!({
        "rule_id": "contract-effect-probe", "rule_version": "1", "schema_version": "rule-0.2",
        "inputs": {"hit": "bool", "insured_amount_krw": "money_krw"},
        "eligibility": "hit", "amount": "insured_amount_krw",
        "contract_effect": "void_refund_premium",
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": [], "publication_state": "fixture_only"
    });
    let rule = match Rule::from_json(&rule) {
        Ok(rule) => rule,
        Err(e) => {
            // A pre-rule-0.2 engine objects to the `contract_effect` key or to the schema
            // version. Any other rejection means the probe rule itself is broken.
            assert!(
                e.message.contains("contract_effect") || e.path == "schema_version",
                "probe rule rejected for a reason other than missing rule-0.2 support: {e}"
            );
            assert!(
                std::env::var_os("ONJ_REQUIRE_RULE_02").is_none(),
                "ONJ_REQUIRE_RULE_02 is set but this engine build has no rule-0.2: {e}"
            );
            eprintln!(
                "VACUOUS: engine without rule-0.2 ({e}); contract_effect shapes were checked from fixtures only"
            );
            return;
        }
    };
    let shapes = [
        (
            json!({"hit": true, "insured_amount_krw": 100}),
            CONTRACT_EFFECT_APPLIES,
            Some("void_refund_premium"),
            None,
        ),
        (json!({"hit": false}), CONTRACT_EFFECT_NONE, None, None),
        (
            json!({"insured_amount_krw": 100}),
            CONTRACT_EFFECT_UNDETERMINED,
            None,
            Some("void_refund_premium"),
        ),
    ];
    for (inputs, kind, effect, conditional) in shapes {
        let wire = serde_json::to_string(&rule.evaluate(&inputs).unwrap()).unwrap();
        let typed = round_trip::<EvaluationResult>(&wire);
        assert_eq!(check_evaluation_result(&typed), vec![], "{wire}");
        let ce = typed
            .contract_effect
            .expect("a rule-0.2 engine reports contract_effect");
        assert_eq!(ce.kind, kind);
        assert_eq!(ce.effect.as_deref(), effect);
        assert_eq!(ce.conditional_effect.as_deref(), conditional);
    }
}

#[test]
fn engine_payout_kinds_are_the_contract_payout_axis() {
    use onjeon_rules_engine::Rule;
    let dir = schemas_dir().join("../fixtures/rules");
    let rule_src = std::fs::read_to_string(dir.join("fixture-rule-001.json")).unwrap();
    let rule = Rule::from_json_str(&rule_src).unwrap();
    let cases: Value = serde_json::from_str(
        &std::fs::read_to_string(dir.join("fixture-rule-001.cases.json")).unwrap(),
    )
    .unwrap();
    let mut seen = std::collections::BTreeSet::new();
    for case in cases["cases"].as_array().unwrap() {
        let wire = serde_json::to_value(rule.evaluate(&case["inputs"]).unwrap()).unwrap();
        let typed: EvaluationResult = serde_json::from_value(wire).unwrap();
        seen.insert(typed.payout.kind.as_str());
    }
    let all: std::collections::BTreeSet<_> = Payout::ALL.iter().map(|p| p.as_str()).collect();
    assert_eq!(seen, all, "fixture cases should exercise every payout kind");
}

// ---- cross-field invariants ----------------------------------------------

fn assertion() -> Assertion {
    serde_json::from_str(fixture!("Assertion.relation")).unwrap()
}

#[test]
fn fixture_assertion_is_valid_but_never_accepted() {
    assert!(check_assertion(&assertion()).is_empty());
    let mut a = assertion();
    a.review_status = ReviewStatus::Accepted;
    a.review_decision_id = Some(format!("rd:{}", "01ARZ3NDEKTSV4RRFFQ69G5FAV"));
    let rules: Vec<_> = check_assertion(&a).iter().map(|v| v.rule).collect();
    assert_eq!(rules, vec!["chk_fixture_never_accepted"]);
}

#[test]
fn accepted_assertion_needs_a_review_decision() {
    let mut a = assertion();
    a.origin = AssertionOrigin::Pipeline;
    a.review_status = ReviewStatus::Accepted;
    let rules: Vec<_> = check_assertion(&a).iter().map(|v| v.rule).collect();
    assert_eq!(rules, vec!["chk_accepted_needs_decision"]);
    a.review_decision_id = Some("rd:01ARZ3NDEKTSV4RRFFQ69G5FAV".into());
    assert!(check_assertion(&a).is_empty());
}

#[test]
fn assertion_is_a_relation_or_a_value_never_both_or_neither() {
    let mut a = assertion();
    a.value = serde_json::from_str::<Assertion>(fixture!("Assertion.value"))
        .unwrap()
        .value;
    assert_eq!(check_assertion(&a)[0].rule, "assertion_object_xor_value");
    a.object = None;
    a.value = None;
    assert_eq!(check_assertion(&a)[0].rule, "assertion_object_xor_value");
}

#[test]
fn premium_comparison_eligibility_needs_the_full_condition_set() {
    let raw: PremiumObservation = serde_json::from_str(fixture!("PremiumObservation.raw")).unwrap();
    assert!(
        check_premium_observation(&raw).is_empty(),
        "raw observation with gaps is preserved"
    );
    let full: PremiumObservation =
        serde_json::from_str(fixture!("PremiumObservation.full")).unwrap();
    assert!(check_premium_observation(&full).is_empty());
    assert!(
        !full.comparison_eligible,
        "no fixture file is comparison-eligible: that needs accepted, which origin=fixture never is"
    );

    // the eligible case exists only here, in memory: accepted pipeline data with every condition
    let mut eligible = full.clone();
    eligible.comparison_eligible = true;
    eligible.review_status = ReviewStatus::Accepted;
    eligible.review_decision_id = Some("rd:01ARZ3NDEKTSV4RRFFQ69G5FAV".into());
    eligible.origin = AssertionOrigin::Pipeline;
    assert!(check_premium_observation(&eligible).is_empty());

    let mut still_fixture = eligible.clone();
    still_fixture.origin = ORIGIN_FIXTURE;
    let rules: Vec<_> = check_premium_observation(&still_fixture)
        .iter()
        .map(|v| v.rule)
        .collect();
    assert_eq!(rules, vec!["chk_fixture_never_accepted"]);

    let mut bad = raw.clone();
    bad.comparison_eligible = true;
    let found = check_premium_observation(&bad);
    assert!(found
        .iter()
        .all(|v| v.rule == "chk_premium_raw_vs_eligible"));
    assert_eq!(found.len(), 2, "conditions/as_of gaps and not accepted");

    let mut no_as_of = eligible.clone();
    no_as_of.source_as_of = None;
    assert_eq!(check_premium_observation(&no_as_of).len(), 1);
}

#[test]
fn blocked_scenario_carries_no_engine_result() {
    let blocked: ScenarioResult = serde_json::from_str(fixture!("ScenarioResult.blocked")).unwrap();
    assert!(check_scenario_result(&blocked).is_empty());
    let evaluated: ScenarioResult =
        serde_json::from_str(fixture!("ScenarioResult.evaluated")).unwrap();
    assert!(check_scenario_result(&evaluated).is_empty());
    let mut bad = evaluated.clone();
    bad.blocked_by = blocked.blocked_by.clone();
    assert_eq!(
        check_scenario_result(&bad)[0].rule,
        "blocked_means_no_engine_call"
    );
}

#[test]
fn evaluation_result_invariants_catch_mismatched_kinds() {
    let payable: EvaluationResult =
        serde_json::from_str(fixture!("EvaluationResult.payable")).unwrap();
    let undetermined: EvaluationResult =
        serde_json::from_str(fixture!("EvaluationResult.undetermined")).unwrap();
    assert!(check_evaluation_result(&payable).is_empty());
    assert!(check_evaluation_result(&undetermined).is_empty());
    let rules = |e: &EvaluationResult| {
        check_evaluation_result(e)
            .iter()
            .map(|v| v.rule)
            .collect::<Vec<_>>()
    };

    let mut e = payable.clone();
    e.eligibility = Tri::False;
    assert_eq!(
        rules(&e),
        vec![
            "payout_matches_eligibility",
            "contract_effect_matches_eligibility"
        ]
    );

    let mut e = payable.clone();
    e.payout.conditional_amount = e.payout.amount.clone();
    assert_eq!(rules(&e), vec!["payout_fields_match_kind"]);

    let mut e = payable.clone();
    e.payout.amount.as_mut().unwrap().min_krw = Some(1);
    assert_eq!(rules(&e), vec!["amount_fields_match_kind"]);

    let mut e = undetermined.clone();
    let a = e.payout.conditional_amount.as_mut().unwrap();
    std::mem::swap(&mut a.min_krw, &mut a.max_krw); // min > max
    assert_eq!(rules(&e), vec!["amount_fields_match_kind"]);

    let mut e = payable.clone();
    let ce = e.contract_effect.as_mut().unwrap();
    ce.conditional_effect = ce.effect.clone();
    assert_eq!(rules(&e), vec!["contract_effect_fields_match_kind"]);

    let mut e = payable.clone();
    e.contract_effect.as_mut().unwrap().kind = "cancelled".into();
    assert_eq!(rules(&e), vec!["contract_effect_kind_known"]);

    let mut e = undetermined.clone();
    e.contract_effect.as_mut().unwrap().kind = "applies".into();
    assert_eq!(
        rules(&e),
        vec![
            "contract_effect_fields_match_kind",
            "contract_effect_matches_eligibility"
        ]
    );

    // a result from an engine build before rule-0.2 support carries no contract_effect at all
    let mut e = payable.clone();
    e.contract_effect = None;
    assert!(check_evaluation_result(&e).is_empty());
}

#[test]
fn every_fixture_satisfies_the_cross_field_checks_and_is_test_only() {
    for src in [fixture!("Assertion.relation"), fixture!("Assertion.value")] {
        let a: Assertion = serde_json::from_str(src).unwrap();
        assert_eq!(check_assertion(&a), vec![]);
        assert_eq!(a.origin, ORIGIN_FIXTURE);
        assert_ne!(a.review_status, ReviewStatus::Accepted);
    }
    for src in [
        fixture!("PremiumObservation.raw"),
        fixture!("PremiumObservation.full"),
    ] {
        let p: PremiumObservation = serde_json::from_str(src).unwrap();
        assert_eq!(check_premium_observation(&p), vec![]);
        assert_eq!(p.origin, ORIGIN_FIXTURE);
        assert_ne!(p.review_status, ReviewStatus::Accepted);
        assert!(!p.comparison_eligible);
    }
    for src in [
        fixture!("ScenarioResult.evaluated"),
        fixture!("ScenarioResult.blocked"),
    ] {
        let s: ScenarioResult = serde_json::from_str(src).unwrap();
        assert_eq!(check_scenario_result(&s), vec![]);
    }
    for src in [
        fixture!("EvaluationResult.payable"),
        fixture!("EvaluationResult.undetermined"),
    ] {
        let e: EvaluationResult = serde_json::from_str(src).unwrap();
        assert_eq!(check_evaluation_result(&e), vec![]);
        assert!(
            e.contract_effect.is_some(),
            "fixtures show the rule-0.2 shape"
        );
    }
    let e: ErrorResponse = serde_json::from_str(fixture!("ErrorResponse")).unwrap();
    assert_eq!(check_error_response(&e), vec![]);
}

#[test]
fn error_class_must_match_the_code() {
    let mut e: ErrorResponse = serde_json::from_str(fixture!("ErrorResponse")).unwrap();
    assert!(check_error_response(&e).is_empty());
    e.error_class = ErrorClass::NotFound;
    assert_eq!(check_error_response(&e)[0].rule, "error_class_matches_code");
}

#[test]
fn error_class_words_and_code_letters_correspond_one_to_one() {
    // the letter set of the `code` pattern (02 §4.2) and the vocabulary axis are the same closed set
    let letters: String = ErrorClass::ALL
        .iter()
        .map(|c| error_class_letter(*c))
        .collect();
    assert_eq!(letters, "VANSLUXT");
    for class in ErrorClass::ALL {
        let letter = error_class_letter(*class).to_string();
        assert_eq!(error_class_for_letter(&letter), Some(*class));
        let e = ErrorResponse {
            error_class: *class,
            code: format!("ONJ-AP-{letter}-001"),
            message_key: "error.any".into(),
            retryable: false,
            trace_id: "trace-fixture-1".into(),
        };
        assert_eq!(check_error_response(&e), vec![]);
    }
    assert_eq!(error_class_for_letter("Z"), None);
    assert_eq!(error_class_for_letter(""), None);
}

#[test]
fn a_class_letter_is_no_longer_a_valid_error_class_on_the_wire() {
    // 1.5.0 clients sent the letter; since vocabulary 1.6.0 the field is the enum word
    let doc = json!({"error_class": "V", "code": "ONJ-AP-V-001", "message_key": "k", "retryable": false, "trace_id": "t"});
    assert!(serde_json::from_value::<ErrorResponse>(doc).is_err());
}

#[test]
fn promoted_axes_reject_unknown_values_instead_of_keeping_a_string() {
    // the eleven fields that were pending-axis strings in 1.5.0 are closed vocabulary enums now
    let mut a: Value = serde_json::from_str(fixture!("Assertion.value")).unwrap();
    a["origin"] = json!("synthetic");
    assert!(serde_json::from_value::<Assertion>(a).is_err());
    let mut c: Value = serde_json::from_str(fixture!("CompareView")).unwrap();
    c["scope_relations"][0]["value"] = json!("superset");
    assert!(serde_json::from_value::<CompareView>(c).is_err());
    let mut n: Value = serde_json::from_str(fixture!("NeedResult")).unwrap();
    n["verdict"] = json!("buy");
    assert!(serde_json::from_value::<NeedResult>(n).is_err());
}

#[test]
fn no_wire_type_exposes_floating_point_money() {
    // money is integer KRW; the only f64 fields are the display-only 만원 values of the plan view
    let types = std::fs::read_to_string(schemas_dir().join("src/generated/types.rs")).unwrap();
    let mut owner = String::new();
    let mut floats = Vec::new();
    for line in types.lines() {
        if let Some(rest) = line.strip_prefix("pub struct ") {
            owner = rest.trim_end_matches(" {").to_string();
        }
        if line.contains("f64") {
            let name = line
                .trim()
                .trim_start_matches("pub ")
                .split(':')
                .next()
                .unwrap();
            floats.push(format!("{owner}.{name}"));
        }
    }
    floats.sort();
    assert_eq!(
        floats,
        vec![
            "Budget.max_man",
            "Budget.min_man",
            "Budget.step_man",
            "Budget.value_man",
            "CurrentPaid.man",
            "PriceLine.man",
        ]
    );
}
