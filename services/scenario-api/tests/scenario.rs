use onjeon_api_types::{EvaluationRequest, ScenarioRequest};
use onjeon_contracts::{
    checks::check_scenario_result, CalculationIssueCode, DisplayStatus, ResultState,
    ScenarioResult, Tri,
};
use onjeon_ontology::{freeze, Abox, Release};
use onjeon_scenario_api::{create_scenario, evaluate_coverage, ScenarioContext};
use onjeon_twin_runtime::{evaluate_request, Request, Snapshot};
use serde_json::{json, Value};
use std::{collections::BTreeMap, path::Path};

const ORIGINAL_COVERAGE: &str = "cov:hana_2_1";
const COVERAGE: &str = "cov:ted:01BX5ZZKBKACTAV9WEVGEMMVRY/art7";
const CONFIG: &str = "sc:hana_2601_3d_v20260701";

fn snapshot(inputs: Value, amount: Value) -> Snapshot {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../packages/ontology/tests/golden");
    let mut abox = Abox::from_dir(&path).unwrap();
    // Use the wire contract's identifier format without changing the shared A-box.
    for record in abox.sections.values_mut().flatten() {
        for key in ["id", "subject", "object"] {
            if record[key].as_str() == Some(ORIGINAL_COVERAGE) {
                record[key] = json!(COVERAGE);
            }
        }
    }
    // Reuse the fixture's existing approved link and freeze the synthetic rule bytes into it.
    let rule = json!({
        "example_kind": "ontology_case_validation",
        "rule_id": "hana-2601-3d-cancer-dx", "rule_version": "audit-7", "schema_version": "rule-0.2",
        "inputs": inputs, "eligibility": true, "amount": amount,
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": [], "publication_state": "fixture_only"
    });
    abox.rule_files.insert(
        "규칙/hana-2601-3d-cancer-dx.json".to_owned(),
        serde_json::to_vec(&rule).unwrap(),
    );
    let original = abox
        .releases
        .iter()
        .find(|r| r.id == "rel:case-r26")
        .unwrap();
    let mut members = original.freeze.members.clone();
    for id in members.values_mut().flatten() {
        if id == ORIGINAL_COVERAGE {
            *id = COVERAGE.to_owned();
        }
    }
    let frozen = freeze(&abox, &members, "case-0.2").unwrap();
    let id = "rel:20261118-1";
    abox.releases.push(Release {
        id: id.to_owned(),
        frozen_at: original.frozen_at.clone(),
        note: None,
        freeze: frozen,
    });
    Snapshot::release(&abox, id).unwrap()
}

fn context<'a>(
    snapshot: &'a Snapshot,
    verified: &'a BTreeMap<String, Value>,
) -> ScenarioContext<'a> {
    ScenarioContext {
        snapshot,
        candidates: &[CONFIG],
        contract_date: "2026-08-20",
        result_state: serde_json::from_value::<ResultState>(json!({
            "input_freshness": "fresh", "knowledge_freshness": "fresh",
            "usage_restriction": "none", "reproducible": true
        }))
        .unwrap(),
        verified_facts: verified,
        display_status: DisplayStatus::Confirmed,
    }
}

fn public(ctx: &ScenarioContext<'_>, facts: Value, assumptions: Value) -> ScenarioResult {
    let request: ScenarioRequest = serde_json::from_value(json!({
        "cov_id": COVERAGE, "facts": facts, "assumptions": assumptions, "idempotency_key": "audit7"
    }))
    .unwrap();
    let result = create_scenario(ctx, &request).unwrap();
    assert!(check_scenario_result(&result).is_empty());
    assert_eq!(result.release_id, "rel:20261118-1");
    result
}

#[test]
fn zero_and_missing_denominators_have_distinct_api_responses() {
    let rounding = json!({"rounding": "floor", "unit": 1});
    for amount in [
        json!({"pro_rata": [{"krw": 100}, 1, "denominator", rounding]}),
        json!({"divide_count": [{"krw": 100}, "denominator", rounding]}),
    ] {
        let snapshot = snapshot(
            json!({"denominator": "int", "use_share": "bool"}),
            json!({"if": "use_share", "then": amount, "else": {"krw": 100}}),
        );
        let verified = BTreeMap::new();
        let ctx = context(&snapshot, &verified);

        let held = public(
            &ctx,
            json!({"denominator": 0, "use_share": true}),
            Value::Null,
        );
        assert_eq!(held.display_status, DisplayStatus::Hold);
        assert!(held.blocked_by.is_empty());
        let wire = serde_json::to_value(&held).unwrap();
        println!("scenario_wire={wire}");
        assert_eq!(wire["display_status"], "hold");
        assert_eq!(
            wire["evaluation"]["payout"],
            json!({"kind": "payable", "amount": {"kind": "unknown"}})
        );
        assert_eq!(
            wire["evaluation"]["amount_issues"],
            json!([{"code":"zero_denominator", "path":"amount.then"}])
        );
        let personal: EvaluationRequest = serde_json::from_value(json!({
            "cov_ids": [COVERAGE],
            "scenario": {"facts": {"denominator": 0, "use_share": true}},
            "idempotency_key": "audit7"
        }))
        .unwrap();
        let personal_result = evaluate_coverage(&ctx, COVERAGE, &personal).unwrap();
        assert_eq!(serde_json::to_value(personal_result).unwrap(), wire);

        let explanation = held.explain.unwrap();
        let vocabulary: Value =
            serde_json::from_str(include_str!("../../../packages/schemas/vocabulary.json"))
                .unwrap();
        let issue_axis = vocabulary["axes"]
            .as_array()
            .unwrap()
            .iter()
            .find(|axis| axis["id"] == "calculation_issue_code")
            .unwrap();
        assert_eq!(
            explanation.template_id,
            CalculationIssueCode::ZeroDenominator.as_str()
        );
        assert_eq!(
            explanation.text,
            issue_axis["values"][0]["screen_ko"].as_str().unwrap()
        );
        assert!(explanation.amounts.is_empty());
        let evaluated = held.evaluation.unwrap();
        assert_eq!(evaluated.eligibility, Tri::True);
        assert!(evaluated.missing_inputs.is_empty());

        for facts in [
            json!({"use_share": true}),
            json!({"denominator": null, "use_share": true}),
            json!({"denominator": 0}),
        ] {
            let missing = public(&ctx, facts.clone(), Value::Null);
            assert_eq!(missing.display_status, DisplayStatus::InputMissing);
            assert!(missing.explain.is_none());
            let evaluation = missing.evaluation.unwrap();
            let wanted = if facts.get("use_share").is_some() {
                "denominator"
            } else {
                "use_share"
            };
            assert_eq!(evaluation.missing_inputs, [wanted]);
            assert!(evaluation.amount_issues.is_none());
        }

        let unselected = public(
            &ctx,
            json!({"denominator": 0, "use_share": false}),
            Value::Null,
        );
        assert_eq!(unselected.display_status, DisplayStatus::Confirmed);
        let evaluation = unselected.evaluation.unwrap();
        assert_eq!(evaluation.payout.amount.unwrap().krw, Some(100));
        assert!(evaluation.amount_issues.is_none());
    }
}

#[test]
fn event_list_confirmation_is_scoped_and_preserves_unknown_amounts() {
    let snapshot = snapshot(
        json!({"events": "class_money_list"}),
        json!({"max_over": "events"}),
    );
    let empty = BTreeMap::new();
    let ctx = context(&snapshot, &empty);
    for facts in [
        json!({}),
        json!({"events": []}),
        json!({"events": null}),
        json!({"events": {"confirmed_empty": true}}),
        json!({"events": [{"class": "surgery", "krw": null}]}),
    ] {
        let unknown = public(&ctx, facts, Value::Null);
        assert_eq!(unknown.display_status, DisplayStatus::InputMissing);
        let evaluation = unknown.evaluation.unwrap();
        assert_eq!(evaluation.missing_inputs, ["events"]);
        assert!(evaluation.payout.amount.unwrap().krw.is_none());
    }
    let assumed = public(&ctx, json!({}), json!({"events": []}));
    assert_eq!(assumed.display_status, DisplayStatus::Confirmed);
    assert_eq!(
        assumed.evaluation.unwrap().payout.amount.unwrap().krw,
        Some(0)
    );

    let contradicted = public(&ctx, json!({"events": null}), json!({"events": []}));
    assert_eq!(contradicted.display_status, DisplayStatus::InputMissing);

    let verified = BTreeMap::from([("events".to_owned(), json!([]))]);
    let verified_ctx = context(&snapshot, &verified);
    let verified = public(&verified_ctx, json!({"events": []}), Value::Null);
    assert_eq!(verified.display_status, DisplayStatus::Confirmed);
    assert_eq!(
        verified.evaluation.unwrap().payout.amount.unwrap().krw,
        Some(0)
    );

    let personal: EvaluationRequest = serde_json::from_value(json!({
        "cov_ids": [COVERAGE], "scenario": {"facts": {"events": []}},
        "confirmed_facts": {"events": []}, "idempotency_key": "audit7"
    }))
    .unwrap();
    let confirmed = evaluate_coverage(&ctx, COVERAGE, &personal).unwrap();
    assert_eq!(confirmed.display_status, DisplayStatus::Confirmed);
    assert_eq!(
        confirmed.evaluation.unwrap().payout.amount.unwrap().krw,
        Some(0)
    );

    // The runtime entry point is safe even when used without the scenario adapter.
    let runtime = evaluate_request(
        &snapshot,
        &Request {
            candidates: &[CONFIG],
            contract_date: ctx.contract_date,
            coverage: COVERAGE,
            facts: json!({"events": []}).as_object().unwrap(),
        },
    );
    assert_eq!(runtime.engine_calls, 1);
    assert_eq!(runtime.eval.unwrap().unwrap().missing_inputs, ["events"]);
}

#[test]
fn pre_engine_link_block_retains_its_distinct_wire_shape() {
    let snap = snapshot(json!({}), json!({"krw": 100}));
    let verified = BTreeMap::new();
    let mut ctx = context(&snap, &verified);
    ctx.candidates = &[];
    let result = public(&ctx, json!({}), Value::Null);
    assert_eq!(result.display_status, DisplayStatus::Hold);
    assert_eq!(result.blocked_by.len(), 1);
    assert!(result.evaluation.is_none());
    assert!(result.explain.is_none());
}
