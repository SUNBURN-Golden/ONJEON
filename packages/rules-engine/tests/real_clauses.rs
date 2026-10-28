//! V1-b: rules transcribed from real policy clauses (design validation, AI interpretation,
//! not reviewed, never service data). Each `*.cases.json` in `fixtures/rules/real` names its
//! rule(s), a `base` input set and per-case overrides (`set`). Engine-owned supplements in
//! `tests/fixtures/cases/real` add boundary cases without editing the shared fixtures.
mod common;
use common::*;
use onjeon_rules_engine::Rule;
use serde_json::{json, Value as J};
use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

// 47 shared design-validation cases + 68 engine-owned boundary cases.
// Update deliberately when adding or removing cases; never derive this from discovered files.
const EXPECTED_REAL_CLAUSE_CASES: usize = 47 + 68;

fn rules() -> BTreeMap<String, Rule> {
    let rules = real_rules();
    for (id, rule) in &rules {
        assert_eq!(
            rule.publication_state(),
            "fixture_only",
            "{id}: real-clause validation rules must never be publishable"
        );
        assert_eq!(
            rule.source_json()["example_kind"],
            "real_clause_design_validation",
            "{id}"
        );
    }
    rules
}

/// Every `*.cases.json` in the real-clause directory, sorted by file name.
fn case_files() -> Vec<(String, J)> {
    let mut out = Vec::new();
    for e in std::fs::read_dir(real_dir()).unwrap() {
        let p = e.unwrap().path();
        let name = p.file_name().unwrap().to_string_lossy().to_string();
        if name.ends_with(".cases.json") {
            let file = case_file(p.strip_prefix(fixtures_dir()).unwrap());
            out.push((name, file));
        }
    }
    out.sort_by(|a, b| a.0.cmp(&b.0));
    out
}

/// Runs every case against its rule. Returns the ids of the rules the cases exercised, the
/// number of cases run, and every problem found: a case naming no rule, a case (or a file-level
/// `rule_id`) naming a rule that was not loaded, or an observed result differing from `expect`.
fn run_cases(
    files: &[(String, J)],
    rules: &BTreeMap<String, Rule>,
) -> (BTreeSet<String>, usize, Vec<String>) {
    let mut exercised = BTreeSet::new();
    let mut problems = Vec::new();
    let mut n = 0;
    for (name, file) in files {
        if let Some(rid) = file.get("rule_id").and_then(J::as_str) {
            if !rules.contains_key(rid) {
                problems.push(format!("{name}: file rule_id `{rid}` names no loaded rule"));
            }
        }
        for case in file["cases"].as_array().into_iter().flatten() {
            let Some(rule_id) = case["rule"].as_str().or_else(|| file["rule_id"].as_str()) else {
                problems.push(format!("{name}: case {} names no rule", case["id"]));
                continue;
            };
            let Some(rule) = rules.get(rule_id) else {
                problems.push(format!(
                    "{name}: case {} names unknown rule `{rule_id}`",
                    case["id"]
                ));
                continue;
            };
            exercised.insert(rule_id.to_string());
            let inputs = merged(&file["base"], case.get("set"));
            let observed = observe(rule, &inputs);
            n += 1;
            if observed != case["expect"] {
                problems.push(format!(
                    "{}: expected {} got {}",
                    case["id"], case["expect"], observed
                ));
            }
        }
    }
    (exercised, n, problems)
}

/// Loaded rules no case exercises (a rule that could silently regress).
fn unexercised(exercised: &BTreeSet<String>, rules: &BTreeMap<String, Rule>) -> Vec<String> {
    rules
        .keys()
        .filter(|id| !exercised.contains(*id))
        .cloned()
        .collect()
}

fn assert_case_coverage(exercised: &BTreeSet<String>, n: usize, rules: &BTreeMap<String, Rule>) {
    assert_eq!(
        n, EXPECTED_REAL_CLAUSE_CASES,
        "expected the full real-clause case set, ran {n}"
    );
    assert_eq!(
        exercised,
        &rules.keys().cloned().collect::<BTreeSet<_>>(),
        "rules without any case: {:?}",
        unexercised(exercised, rules)
    );
}

#[test]
fn every_real_clause_case_matches() {
    let rules = rules();
    let (exercised, n, problems) = run_cases(&case_files(), &rules);
    assert!(problems.is_empty(), "{}", problems.join("\n"));
    assert_case_coverage(&exercised, n, &rules);
}

#[test]
fn exact_case_count_check_catches_each_missing_file() {
    let rules = rules();
    let files = case_files();
    for (missing, _) in &files {
        let without: Vec<_> = files
            .iter()
            .filter(|(name, _)| name != missing)
            .cloned()
            .collect();
        let (exercised, n, problems) = run_cases(&without, &rules);
        assert!(problems.is_empty(), "{problems:?}");
        assert!(n < EXPECTED_REAL_CLAUSE_CASES);
        let failure = std::panic::catch_unwind(|| assert_case_coverage(&exercised, n, &rules))
            .expect_err("a missing cases file must fail the coverage check");
        let message = failure.downcast_ref::<String>().unwrap();
        assert!(
            message.contains("expected the full real-clause case set"),
            "{missing}: expected a count failure, got {message}"
        );
    }
}

#[test]
#[should_panic(expected = "expected the full real-clause case set")]
fn exact_case_count_check_catches_one_missing_case_with_all_rules_still_covered() {
    let rules = rules();
    let mut files = case_files();
    files[0].1["cases"].as_array_mut().unwrap().pop().unwrap();
    let (exercised, n, problems) = run_cases(&files, &rules);
    assert!(problems.is_empty(), "{problems:?}");
    assert_eq!(n, EXPECTED_REAL_CLAUSE_CASES - 1);
    assert!(unexercised(&exercised, &rules).is_empty());
    assert_case_coverage(&exercised, n, &rules);
}

#[test]
#[should_panic(expected = "expected the full real-clause case set")]
fn exact_case_count_check_catches_an_unexpected_extra_case() {
    let rules = rules();
    let mut files = case_files();
    let cases = files[0].1["cases"].as_array_mut().unwrap();
    cases.push(cases[0].clone());
    let (exercised, n, problems) = run_cases(&files, &rules);
    assert!(problems.is_empty(), "{problems:?}");
    assert_eq!(n, EXPECTED_REAL_CLAUSE_CASES + 1);
    assert_case_coverage(&exercised, n, &rules);
}

#[test]
#[should_panic(expected = "rules without any case: [\"rule-without-cases\"]")]
fn rule_coverage_check_catches_an_unexercised_rule_with_the_exact_case_count() {
    let mut rules = rules();
    let mut orphan = rules.values().next().unwrap().source_json().clone();
    orphan["rule_id"] = json!("rule-without-cases");
    rules.insert(
        "rule-without-cases".into(),
        Rule::from_json(&orphan).unwrap(),
    );
    let (exercised, n, problems) = run_cases(&case_files(), &rules);
    assert!(problems.is_empty(), "{problems:?}");
    assert_eq!(n, EXPECTED_REAL_CLAUSE_CASES);
    assert_case_coverage(&exercised, n, &rules);
}

#[test]
fn case_coverage_check_catches_orphans_and_unknown_rules() {
    let rules = rules();
    let files = case_files();
    let all: BTreeSet<_> = rules.keys().cloned().collect();

    // Baseline is clean, so every failure below comes from the tamper alone.
    let (exercised, _, problems) = run_cases(&files, &rules);
    assert!(problems.is_empty(), "{problems:?}");
    assert_eq!(exercised, all);

    // Dropping a cases file (here the shared wholelife one) leaves two rules orphaned.
    let without: Vec<_> = files
        .iter()
        .filter(|(n, _)| n != "kyobo-wholelife-death.cases.json")
        .cloned()
        .collect();
    let (exercised, _, problems) = run_cases(&without, &rules);
    assert!(problems.is_empty(), "{problems:?}");
    assert_eq!(
        unexercised(&exercised, &rules),
        [
            "kyobo-wholelife-accident-death",
            "kyobo-wholelife-disease-death"
        ]
    );

    // A shared-file case pointed at a rule that is not loaded is reported, not skipped.
    let mut typo = files.clone();
    let shared = typo
        .iter_mut()
        .find(|(n, _)| n == "kyobo-wholelife-death.cases.json")
        .unwrap();
    shared.1["cases"][0]["rule"] = json!("kyobo-wholelife-accident-dath");
    let (_, _, problems) = run_cases(&typo, &rules);
    assert!(
        problems
            .iter()
            .any(|p| p.contains("unknown rule `kyobo-wholelife-accident-dath`")),
        "{problems:?}"
    );

    // A file-level rule_id naming no loaded rule is reported even with zero cases.
    let mut renamed = files.clone();
    let f = renamed
        .iter_mut()
        .find(|(n, _)| n == "kb-driver-fine.cases.json")
        .unwrap();
    f.1["rule_id"] = json!("kb-driver-fine-v2");
    f.1["cases"] = json!([]);
    let (exercised, _, problems) = run_cases(&renamed, &rules);
    assert!(
        problems
            .iter()
            .any(|p| p.contains("file rule_id `kb-driver-fine-v2` names no loaded rule")),
        "{problems:?}"
    );
    assert_eq!(unexercised(&exercised, &rules), ["kb-driver-fine"]);

    // A case with no rule anywhere is reported.
    let mut nameless = files.clone();
    let shared = nameless
        .iter_mut()
        .find(|(n, _)| n == "kyobo-wholelife-death.cases.json")
        .unwrap();
    shared.1["cases"][0].as_object_mut().unwrap().remove("rule");
    let (_, _, problems) = run_cases(&nameless, &rules);
    assert!(
        problems.iter().any(|p| p.contains("names no rule")),
        "{problems:?}"
    );
}

#[test]
fn whole_life_accident_and_disease_death_never_both_pay() {
    // routes_to: the exclusion exceptions in art. 8 send one death to exactly one benefit.
    let rules = rules();
    let acc = &rules["kyobo-wholelife-accident-death"];
    let dis = &rules["kyobo-wholelife-disease-death"];
    let tri = [json!(true), json!(false), J::Null];
    let mut checked = 0;
    for cause in &tri {
        for harm in &tri {
            for no_will in &tri {
                for death in ["2026-06-01", "2027-12-31", "2028-01-01", "2030-12-31"] {
                    let inputs = json!({
                        "contract_date": "2026-01-01", "coverage_start_date": "2026-01-01",
                        "is_revived": false, "revival_application_date": null, "death_date": death,
                        "cause_in_accident_table": cause, "self_harm": harm,
                        "self_harm_without_free_will": no_will,
                        "harmed_by_beneficiary_or_contractor": false,
                        "basic_amount_krw": 100000000, "insured_amount_krw": 100000000,
                        "additional_reserve_krw": 0
                    });
                    let a = acc.evaluate(&inputs).unwrap().eligibility;
                    let d = dis.evaluate(&inputs).unwrap().eligibility;
                    let both = serde_json::to_value(a).unwrap() == "true"
                        && serde_json::to_value(d).unwrap() == "true";
                    assert!(!both, "both benefits pay for {inputs}");
                    checked += 1;
                }
            }
        }
    }
    assert_eq!(checked, 108);
}

#[test]
fn waiting_period_units_are_not_interchangeable() {
    // 90 days (2026 product) and 3 months (1995 product) give different first covered days.
    let rules = rules();
    let days = &rules["kyobo-cancer-main-dx"];
    let months = &rules["kyobo-1995-cancer-waiting"];
    let d = days
        .evaluate(&json!({
            "contract_date": "2026-06-01", "is_revived": false, "revival_date": null,
            "diagnosis_date": "2026-08-31", "policy_end_date": "2086-01-01",
            "dx_in_cancer_annex_at_dx": true, "already_paid": false, "self_harm": false,
            "self_harm_without_free_will": false, "harmed_by_beneficiary_or_contractor": false,
            "insured_amount_krw": 30000000
        }))
        .unwrap();
    let m = months
        .evaluate(&json!({
            "contract_date": "2026-06-01", "diagnosis_date": "2026-08-31",
            "dx_in_cancer_annex": true, "benefit_amount_krw": 30000000
        }))
        .unwrap();
    assert_eq!(serde_json::to_value(d.eligibility).unwrap(), "true");
    assert_eq!(serde_json::to_value(m.eligibility).unwrap(), "false");
}

#[test]
fn every_real_rule_evidence_ref_names_an_encoded_clause() {
    // Rule evidence must resolve to a clause in docs/blueprint/validation/encoded/<file>.json.
    let encoded =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../docs/blueprint/validation/encoded");
    for (id, rule) in rules() {
        for r in rule.evidence_refs() {
            let (file, clause) = r
                .split_once('#')
                .unwrap_or_else(|| panic!("{id}: evidence ref `{r}` must be <file>#<clause_id>"));
            let doc = load_json(&encoded.join(format!("{file}.json")));
            let found = doc["clauses"]
                .as_array()
                .unwrap()
                .iter()
                .any(|c| c["clause_id"] == clause);
            assert!(found, "{id}: `{r}` not found in encoded/{file}.json");
        }
    }
}

/// Korean won text exactly as the screen writes it: "1,500만원", "51,290원", "0원".
fn fmt_krw(krw: i64) -> String {
    fn grouped(n: i64) -> String {
        let s = n.to_string();
        let mut out = String::new();
        for (i, c) in s.chars().enumerate() {
            if i > 0 && (s.len() - i).is_multiple_of(3) {
                out.push(',');
            }
            out.push(c);
        }
        out
    }
    if krw != 0 && krw % 10_000 == 0 {
        format!("{}만원", grouped(krw / 10_000))
    } else {
        format!("{}원", grouped(krw))
    }
}

/// The payout text a scenario line must start with, generated from the engine result alone.
fn payout_text(payout: &J) -> String {
    match (payout["kind"].as_str(), payout["amount"]["kind"].as_str()) {
        (Some("not_payable"), _) => fmt_krw(0),
        (Some("payable"), Some("exact")) => fmt_krw(payout["amount"]["krw"].as_i64().unwrap()),
        (Some("payable"), Some("range")) => format!(
            "{}~{}",
            fmt_krw(payout["amount"]["min_krw"].as_i64().unwrap()),
            fmt_krw(payout["amount"]["max_krw"].as_i64().unwrap())
        ),
        _ => "계산 불가".to_string(),
    }
}

fn engine_krw(payout: &J) -> Option<i64> {
    match (payout["kind"].as_str(), payout["amount"]["kind"].as_str()) {
        (Some("not_payable"), _) => Some(0),
        (Some("payable"), Some("exact")) => payout["amount"]["krw"].as_i64(),
        _ => None,
    }
}

fn collect_amounts<'a>(v: &'a J, out: &mut Vec<&'a J>) {
    match v {
        J::Object(m) => {
            if let Some(J::Array(a)) = m.get("amounts") {
                out.extend(a.iter());
            }
            m.values().for_each(|x| collect_amounts(x, out));
        }
        J::Array(a) => a.iter().for_each(|x| collect_amounts(x, out)),
        _ => {}
    }
}

/// Every way the screen can disagree with the engine. Empty means the screen is faithful.
fn screen_errors(screen: &J, rules: &BTreeMap<String, Rule>) -> Vec<String> {
    let mut errors = Vec::new();
    let mut results = BTreeMap::new();
    for s in screen["scenarios"].as_array().into_iter().flatten() {
        let id = s["id"].as_str().unwrap_or("?").to_string();
        let Some(rule) = s["rule_id"].as_str().and_then(|r| rules.get(r)) else {
            errors.push(format!("{id}: unknown rule"));
            continue;
        };
        if let Err(e) = rule.evaluate(&s["inputs"]) {
            errors.push(format!("{id}: evaluation error: {e}"));
            continue;
        }
        let observed = observe(rule, &s["inputs"]);
        if observed != s["expect"] {
            errors.push(format!(
                "{id}: engine gives {observed}, screen file expects {}",
                s["expect"]
            ));
        }
        let want = payout_text(&observed["payout"]);
        let line = s["display"]["line"].as_str().unwrap_or("");
        if !line.starts_with(&want) {
            errors.push(format!(
                "{id}: line `{line}` must start with engine text `{want}`"
            ));
        }
        results.insert(id, observed["payout"].clone());
    }
    let mut amounts = Vec::new();
    collect_amounts(screen, &mut amounts);
    for a in amounts {
        let Some(id) = a["source"]
            .as_str()
            .and_then(|s| s.strip_prefix("scenario:"))
        else {
            continue; // price, candidate and clause sources are checked by tools/validation_check.py
        };
        match results.get(id).map(engine_krw) {
            Some(Some(krw)) if Some(krw) == a["krw"].as_i64() => {}
            Some(Some(krw)) => {
                errors.push(format!("amount {} cites scenario {id} = {krw}", a["krw"]))
            }
            Some(None) => errors.push(format!(
                "amount {} cites scenario {id} with no exact amount",
                a["krw"]
            )),
            None => errors.push(format!("amount {} cites unknown scenario {id}", a["krw"])),
        }
    }
    errors
}

fn detail_screen() -> J {
    load_json(
        &PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../docs/blueprint/validation/screen/coverage_detail.cancer.json"),
    )
}

#[test]
fn screen_payout_text_and_amounts_come_from_the_engine() {
    // V1-c: payout lines start with text generated from the engine result, and every amount
    // the screen attributes to a scenario equals what the engine computes for it.
    let screen = detail_screen();
    assert!(screen["scenarios"].as_array().unwrap().len() >= 7);
    let errors = screen_errors(&screen, &rules());
    assert!(errors.is_empty(), "{}", errors.join("\n"));
}

#[test]
fn screen_check_catches_tampered_numbers() {
    // Each tamper must fail for its intended reason, not merely produce some error.
    let rules = rules();
    let base = detail_screen();
    type Tamper = fn(&mut J);
    let tampers: [(&str, Tamper, &str); 5] = [
        (
            "display line 1,500만원 -> 9,999만원",
            |s| s["scenarios"][1]["display"]["line"] = json!("9,999만원 · 첫 1년 50%"),
            "sc2: line `9,999만원 · 첫 1년 50%` must start with engine text `1,500만원`",
        ),
        (
            "declared scenario amount changed",
            |s| s["sections"]["when_not_paid"][1]["amounts"][0]["krw"] = json!(99_990_000),
            "amount 99990000 cites scenario sc2 = 15000000",
        ),
        (
            "expectation and line changed together",
            |s| {
                s["scenarios"][1]["expect"]["payout"]["amount"]["krw"] = json!(99_990_000);
                s["scenarios"][1]["display"]["line"] = json!("9,999만원 · 첫 1년 50%");
            },
            "sc2: engine gives",
        ),
        (
            "scenario input changed under a fixed line",
            |s| s["scenarios"][1]["inputs"]["diagnosis_date"] = json!("2026-02-01"),
            "sc2: line `1,500만원 · 첫 1년 50%` must start with engine text `0원`",
        ),
        (
            "scenario points at the wrong rule",
            |s| s["scenarios"][1]["rule_id"] = json!("kyobo-small-cancer-skin"),
            "sc2: evaluation error",
        ),
    ];
    for (name, tamper, expected) in tampers {
        let mut s = base.clone();
        tamper(&mut s);
        let errors = screen_errors(&s, &rules);
        assert!(
            errors.iter().any(|e| e.contains(expected)),
            "{name}: expected an error containing `{expected}`, got {errors:?}"
        );
    }
}
