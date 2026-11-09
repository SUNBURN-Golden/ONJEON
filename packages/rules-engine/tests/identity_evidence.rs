//! Audit 2: rule identity and evidence must name non-empty, distinct values.
use onjeon_rules_engine::{Payout, Rule, RuleError};
use serde_json::{json, Value as J};

fn rule(version: &str, state: &str) -> J {
    json!({
        "rule_id": "identity-evidence", "rule_version": "1", "schema_version": version,
        "release_id": "rel-1", "publication_state": state,
        "inputs": {}, "eligibility": true, "amount": {"krw": 1},
        "unknown_policy": "use_three_valued_logic_never_default_to_zero",
        "evidence_refs": ["clause-2", "clause-1"]
    })
}

fn each_loader(j: &J, mut check: impl FnMut(Result<Rule, RuleError>)) {
    check(Rule::from_json(j));
    check(Rule::from_json_str(&serde_json::to_string(j).unwrap()));
}

fn each_rule(mut check: impl FnMut(J)) {
    for version in ["rule-0.1", "rule-0.2"] {
        for state in ["fixture_only", "candidate", "released"] {
            check(rule(version, state));
        }
    }
}

#[test]
fn blank_rule_ids_are_rejected() {
    each_rule(|base| {
        for id in [
            "",
            " ",
            "\t\r\n",
            "\u{000b}\u{000c}",
            "\u{0085}\u{00a0}",
            "\u{2003}\u{3000}",
            "\u{2028}\u{2029}\u{202f}\u{205f}",
        ] {
            let mut j = base.clone();
            j["rule_id"] = json!(id);
            each_loader(&j, |result| {
                let err = result.expect_err("blank rule ID must fail at load");
                assert_eq!(err.path, "rule_id");
                assert!(err.message.contains("empty"), "{err}");
            });
        }
    });
}

#[test]
fn json_escaped_whitespace_rule_ids_are_rejected_after_decoding() {
    each_rule(|base| {
        let text = serde_json::to_string(&base).unwrap();
        for escaped in [r"\u0020", r"\t\r\n", r"\u00a0\u2003\u3000"] {
            let text = text.replace("identity-evidence", escaped);
            let decoded: J = serde_json::from_str(&text).unwrap();
            assert!(decoded["rule_id"].as_str().unwrap().trim().is_empty());
            for result in [Rule::from_json_str(&text), Rule::from_json(&decoded)] {
                let err = result.expect_err("escaped blank ID must fail at load");
                assert_eq!(err.path, "rule_id");
                assert_eq!(err.message, "must not be empty");
            }
        }
    });
}

#[test]
fn nonblank_rule_ids_are_preserved_in_every_result_state() {
    each_rule(|base| {
        for id in ["identity-evidence", "규칙-암-001", " \t규칙-001\u{3000}"] {
            let mut j = base.clone();
            j["rule_id"] = json!(id);
            j["inputs"] = json!({"eligible": "bool"});
            j["eligibility"] = json!({"input": "eligible"});
            each_loader(&j, |result| {
                let loaded = result.unwrap();
                assert_eq!(loaded.rule_id(), id);
                assert_eq!(loaded.source_json(), &j);
                let reloaded = Rule::from_json(loaded.source_json()).unwrap();
                assert_eq!(loaded.content_hash(), reloaded.content_hash());
                if id != id.trim() {
                    let mut trimmed = j.clone();
                    trimmed["rule_id"] = json!(id.trim());
                    assert_ne!(
                        loaded.content_hash(),
                        Rule::from_json(&trimmed).unwrap().content_hash(),
                        "validation must not trim identity before hashing"
                    );
                }
                for inputs in [
                    json!({"eligible": true}),
                    json!({"eligible": false}),
                    json!({"eligible": null}),
                    json!({}),
                ] {
                    let evaluated = loaded.evaluate(&inputs).unwrap();
                    match inputs.get("eligible").and_then(J::as_bool) {
                        Some(true) => assert!(matches!(evaluated.payout, Payout::Payable { .. })),
                        Some(false) => assert!(matches!(evaluated.payout, Payout::NotPayable)),
                        None => assert!(matches!(evaluated.payout, Payout::Undetermined { .. })),
                    }
                    assert_eq!(evaluated.rule_id, id);
                    assert_eq!(evaluated.rule_content_hash, loaded.content_hash());
                    assert_eq!(serde_json::to_value(&evaluated).unwrap()["rule_id"], id);
                    assert_eq!(
                        serde_json::to_vec(&evaluated).unwrap(),
                        serde_json::to_vec(&reloaded.evaluate(&inputs).unwrap()).unwrap()
                    );
                }
            });
        }
    });
}

#[test]
fn blank_evidence_refs_cannot_satisfy_the_evidence_requirement() {
    each_rule(|base| {
        for blank in ["", " ", "\t\r\n", "\u{2003}\u{3000}"] {
            for refs in [json!([blank]), json!(["clause-1", blank])] {
                let mut j = base.clone();
                let index = refs.as_array().unwrap().len() - 1;
                j["evidence_refs"] = refs;
                each_loader(&j, |result| {
                    let err = result.expect_err("blank evidence must fail at load");
                    assert_eq!(err.path, format!("evidence_refs[{index}]"));
                    assert!(err.message.contains("blank"), "{err}");
                });
            }
        }
    });
}

#[test]
fn duplicate_evidence_refs_are_rejected_at_the_repeated_index() {
    each_rule(|base| {
        for (refs, index) in [
            (json!(["clause-1", "clause-1"]), 1),
            (json!(["clause-2", "clause-1", "clause-2"]), 2),
        ] {
            let mut j = base.clone();
            j["evidence_refs"] = refs;
            each_loader(&j, |result| {
                let err = result.expect_err("duplicate evidence must fail at load");
                assert_eq!(err.path, format!("evidence_refs[{index}]"));
                assert!(err.message.contains("duplicate"), "{err}");
            });
        }
    });
}

#[test]
fn empty_evidence_list_is_allowed_only_for_fixtures() {
    each_rule(|mut j| {
        j["evidence_refs"] = json!([]);
        each_loader(&j, |result| {
            if j["publication_state"] == "fixture_only" {
                assert!(result.unwrap().evidence_refs().is_empty());
            } else {
                let err = result.expect_err("publishable rule must cite evidence");
                assert_eq!(err.path, "evidence_refs");
                assert!(err.message.contains("at least one"), "{err}");
            }
        });
    });
}

#[test]
fn valid_identity_and_distinct_refs_survive_loading_reloading_and_evaluation() {
    each_rule(|j| {
        each_loader(&j, |result| {
            let loaded = result.unwrap();
            assert_eq!(loaded.rule_id(), "identity-evidence");
            assert_eq!(loaded.evidence_refs(), ["clause-2", "clause-1"]);
            assert_eq!(loaded.source_json(), &j);
            let reloaded = Rule::from_json(loaded.source_json()).unwrap();
            assert_eq!(loaded.content_hash(), reloaded.content_hash());
            let evaluated = loaded.evaluate(&json!({})).unwrap();
            assert_eq!(evaluated.rule_id, loaded.rule_id());
            assert_eq!(evaluated.evidence_refs, loaded.evidence_refs());
            assert_eq!(evaluated.rule_content_hash, loaded.content_hash());
        });
    });
}
