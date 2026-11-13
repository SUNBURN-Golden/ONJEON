//! Invalid fixtures must fail during loading, before they can reduce coverage silently.
mod common;
use common::*;
use serde_json::{json, Value as J};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};

struct Fixtures(PathBuf);

impl Fixtures {
    fn new() -> Self {
        static NEXT: AtomicUsize = AtomicUsize::new(0);
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../target");
        std::fs::create_dir_all(&root).unwrap();
        let path = root.join(format!(
            "harness-guards-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir(&path).unwrap();
        Self(path)
    }

    fn write(&self, relative: &str, value: &J) {
        let path = self.0.join(relative);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, serde_json::to_vec_pretty(value).unwrap()).unwrap();
    }

    fn cases(&self) -> J {
        case_file_in(
            &self.0.join("shared"),
            &self.0.join("extra"),
            Path::new("example.cases.json"),
        )
    }
}

impl Drop for Fixtures {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.0).unwrap();
    }
}

fn rejects(action: impl FnOnce() + std::panic::UnwindSafe, fragments: &[&str]) {
    let failure = std::panic::catch_unwind(action).expect_err("invalid fixture must be rejected");
    let message = failure
        .downcast_ref::<String>()
        .map(String::as_str)
        .or_else(|| failure.downcast_ref::<&str>().copied())
        .expect("string panic diagnostic");
    for fragment in fragments {
        assert!(
            message.contains(fragment),
            "expected {fragment:?} in {message}"
        );
    }
}

#[test]
fn matching_rule_files_preserve_every_rule_and_ignore_case_tables() {
    let fixtures = Fixtures::new();
    let mut expected = Vec::new();
    for id in ["a-rule", "z-rule"] {
        let mut rule = rule_json();
        rule["rule_id"] = json!(id);
        fixtures.write(&format!("{id}.json"), &rule);
        expected.push((id, rule));
    }
    // Not rule documents; the loader must keep excluding them.
    fixtures.write("a-rule.cases.json", &json!({"cases": []}));
    let rules = real_rules_in(&fixtures.0);
    assert_eq!(rules.len(), 2);
    for (id, source) in expected {
        assert_eq!(rules[id].source_json(), &source);
    }
}

#[test]
fn rule_filename_must_match_its_id_even_without_a_collision() {
    let fixtures = Fixtures::new();
    fixtures.write("renamed.json", &rule_json());
    rejects(
        || {
            real_rules_in(&fixtures.0);
        },
        &["renamed.json", "rule_id", "fixture-rule-001"],
    );
}

#[test]
fn duplicate_rule_ids_are_rejected_in_either_filename_order() {
    for alias in ["a-copy", "z-copy"] {
        let fixtures = Fixtures::new();
        let rule = rule_json();
        fixtures.write("fixture-rule-001.json", &rule);
        let mut different = rule.clone();
        different["amount"]["then"]["multiply_rate"][1] = json!("0.4");
        onjeon_rules_engine::Rule::from_json(&different).expect("both documents are valid rules");
        fixtures.write(&format!("{alias}.json"), &different);
        rejects(
            || {
                real_rules_in(&fixtures.0);
            },
            &[&format!("{alias}.json"), "rule_id", "fixture-rule-001"],
        );
    }
}

#[test]
fn duplicate_rule_id_is_reported_before_any_overwrite() {
    for identical in [true, false] {
        let fixtures = Fixtures::new();
        let rule = rule_json();
        fixtures.write("fixture-rule-001.json", &rule);
        let mut copy = rule.clone();
        if !identical {
            copy["amount"]["then"]["multiply_rate"][1] = json!("0.4");
        }
        onjeon_rules_engine::Rule::from_json(&copy).expect("valid duplicate rule");
        fixtures.write("z-copy.json", &copy);
        rejects(
            || {
                real_rules_in(&fixtures.0);
            },
            &["z-copy.json", "duplicate rule_id `fixture-rule-001`"],
        );
    }
}

fn table(real: bool) -> J {
    if real {
        json!({"rule_id": "example", "base": {"amount": 10, "flag": true}, "cases": [
            {"id": "shared", "rule": "example", "note": "allowed metadata", "set": {}, "expect": {}}
        ]})
    } else {
        json!({"rule_id": "example", "cases": [
            {"id": "shared", "note": "allowed metadata", "inputs": {"amount": 10}, "expect": {}}
        ]})
    }
}

fn multi_rule_table() -> J {
    json!({"rule_ids": ["example", "other"], "rule_id": "example", "base": {}, "cases": [
        {"id": "default", "expect": {}},
        {"id": "explicit", "rule": "other", "expect": {}}
    ]})
}

#[test]
fn multi_rule_inventory_preserves_order_defaults_and_supplements() {
    let fixtures = Fixtures::new();
    let mut shared = multi_rule_table();
    // Inventory order is independent of case order and is preserved, not normalized.
    shared["rule_ids"] = json!(["other", "example"]);
    fixtures.write("shared/example.cases.json", &shared);
    let extra = json!({"rule_ids": ["other", "example"], "cases": [
        {"id": "extra-default", "expect": {}},
        {"id": "extra", "rule": "other", "expect": {}}
    ]});
    fixtures.write("extra/example.cases.json", &extra);
    let loaded = fixtures.cases();
    assert_eq!(loaded["rule_ids"], shared["rule_ids"]);
    assert_eq!(loaded["rule_id"], shared["rule_id"]);
    assert_eq!(loaded["cases"][0], shared["cases"][0]);
    assert_eq!(loaded["cases"][1], shared["cases"][1]);
    assert_eq!(loaded["cases"][2], extra["cases"][0]);
    assert_eq!(loaded["cases"][3], extra["cases"][1]);
}

#[test]
fn malformed_rule_inventories_are_rejected_in_shared_files_and_supplements() {
    for origin in ["shared", "extra"] {
        for (ids, diagnostic) in [
            (J::Null, "rule_ids must be a nonempty array"),
            (json!("example"), "rule_ids must be a nonempty array"),
            (json!({}), "rule_ids must be a nonempty array"),
            (json!([]), "rule_ids must be a nonempty array"),
            (json!([1]), "rule_ids[0] must be a nonblank string"),
            (json!([null]), "rule_ids[0] must be a nonblank string"),
            (json!([""]), "rule_ids[0] must be a nonblank string"),
            (
                json!([" \t\u{3000}"]),
                "rule_ids[0] must be a nonblank string",
            ),
            (
                json!(["example", "example"]),
                "duplicate rule_ids entry `example`",
            ),
        ] {
            let fixtures = Fixtures::new();
            let mut broken = multi_rule_table();
            broken["rule_ids"] = ids;
            if origin == "extra" {
                fixtures.write("shared/example.cases.json", &multi_rule_table());
            }
            fixtures.write(&format!("{origin}/example.cases.json"), &broken);
            rejects(
                || {
                    fixtures.cases();
                },
                &[origin, "example.cases.json", diagnostic],
            );
        }
    }
}

#[test]
fn rule_inventory_must_equal_case_selections_in_each_source_file() {
    for origin in ["shared", "extra"] {
        for (ids, diagnostic) in [
            (
                json!(["example"]),
                "rule `other` is not declared in rule_ids",
            ),
            (
                json!(["example", "other", "unused"]),
                "rule_ids must equal the rules exercised by cases",
            ),
        ] {
            let fixtures = Fixtures::new();
            let mut broken = multi_rule_table();
            broken["rule_ids"] = ids;
            if origin == "extra" {
                fixtures.write("shared/example.cases.json", &multi_rule_table());
            }
            fixtures.write(&format!("{origin}/example.cases.json"), &broken);
            rejects(
                || {
                    fixtures.cases();
                },
                &[origin, "example.cases.json", diagnostic],
            );
        }
    }
    let fixtures = Fixtures::new();
    let mut broken = multi_rule_table();
    broken.as_object_mut().unwrap().remove("rule_id");
    fixtures.write("shared/example.cases.json", &broken);
    rejects(
        || {
            fixtures.cases();
        },
        &["shared", "example.cases.json", "cases[0] names no rule"],
    );
}

#[test]
fn supplements_cannot_select_rules_outside_the_shared_inventory() {
    // Both an absent inventory and a valid local inventory must obey the shared one.
    for declares_ids in [false, true] {
        let fixtures = Fixtures::new();
        fixtures.write("shared/example.cases.json", &multi_rule_table());
        let mut extra = json!({"cases": [
            {"id": "extra", "rule": "unexpected", "expect": {}}
        ]});
        if declares_ids {
            extra["rule_ids"] = json!(["unexpected"]);
        }
        fixtures.write("extra/example.cases.json", &extra);
        rejects(
            || {
                fixtures.cases();
            },
            &[
                "extra",
                "example.cases.json",
                "rule `unexpected` is not declared in rule_ids",
            ],
        );
    }
}

#[test]
fn supplements_cannot_hide_unexercised_shared_inventory_entries() {
    let fixtures = Fixtures::new();
    let mut shared = multi_rule_table();
    shared["cases"].as_array_mut().unwrap().pop();
    fixtures.write("shared/example.cases.json", &shared);
    fixtures.write(
        "extra/example.cases.json",
        &json!({"cases": [
            {"id": "extra", "rule": "other", "expect": {}}
        ]}),
    );
    rejects(
        || {
            fixtures.cases();
        },
        &[
            "shared",
            "example.cases.json",
            "rule_ids must equal the rules exercised by cases",
        ],
    );
}

#[test]
fn valid_shared_and_supplemental_case_formats_keep_their_inputs() {
    for real in [false, true] {
        let fixtures = Fixtures::new();
        let shared = table(real);
        fixtures.write("shared/example.cases.json", &shared);
        let mut extra_case = shared["cases"][0].clone();
        extra_case["id"] = json!("extra");
        if real {
            extra_case["set"] = json!({"amount": 20, "flag": null});
        }
        fixtures.write(
            "extra/example.cases.json",
            &json!({"cases": [extra_case.clone()]}),
        );
        let loaded = fixtures.cases();
        assert_eq!(loaded["cases"][0], shared["cases"][0]);
        assert_eq!(loaded["cases"][1], extra_case);
        if real {
            assert_eq!(merged(&loaded["base"], None), shared["base"]);
            assert_eq!(
                merged(&loaded["base"], loaded["cases"][0].get("set")),
                shared["base"]
            );
            assert_eq!(
                merged(&loaded["base"], loaded["cases"][1].get("set")),
                json!({"amount": 20, "flag": null})
            );
        } else {
            assert_eq!(loaded["cases"][1]["inputs"], json!({"amount": 10}));
        }
    }
}

fn unknown_case_keys_are_rejected(real: bool, keys: &[&str]) {
    for origin in ["shared", "extra"] {
        for key in keys {
            let fixtures = Fixtures::new();
            let mut shared = table(real);
            let mut extra = json!({"cases": [shared["cases"][0].clone()]});
            extra["cases"][0]["id"] = json!("extra");
            let broken = if origin == "shared" {
                &mut shared
            } else {
                &mut extra
            };
            // Leave the valid override intact: unknown additions must also be rejected.
            broken["cases"][0][key] = json!({"amount": 99});
            fixtures.write("shared/example.cases.json", &shared);
            fixtures.write("extra/example.cases.json", &extra);
            rejects(
                || {
                    fixtures.cases();
                },
                &["example.cases.json", origin, "unknown case key", key],
            );
        }
    }
}

#[test]
fn unknown_real_case_keys_are_rejected_in_shared_files_and_supplements() {
    unknown_case_keys_are_rejected(true, &["Set", "inputs", "Expect", "Rule", "unexpected"]);
    // Reproduce the exact typo: replacing `set` must not fall back to the base inputs.
    let fixtures = Fixtures::new();
    let mut shared = table(true);
    shared["cases"][0].as_object_mut().unwrap().remove("set");
    shared["cases"][0]["Set"] = json!({"amount": 99});
    fixtures.write("shared/example.cases.json", &shared);
    rejects(
        || {
            fixtures.cases();
        },
        &["unknown case key", "Set", "shared"],
    );
}

#[test]
fn unknown_synthetic_case_keys_are_rejected_in_shared_files_and_supplements() {
    unknown_case_keys_are_rejected(false, &["Inputs", "set", "rule", "Expect", "unexpected"]);
}

#[test]
fn malformed_overrides_cannot_silently_use_base_inputs() {
    for origin in ["shared", "extra"] {
        for value in [J::Null, json!(false), json!(1), json!("typo"), json!([])] {
            let fixtures = Fixtures::new();
            let mut shared = table(true);
            let mut extra = json!({"cases": [shared["cases"][0].clone()]});
            extra["cases"][0]["id"] = json!("extra");
            let broken = if origin == "shared" {
                &mut shared
            } else {
                &mut extra
            };
            broken["cases"][0]["set"] = value;
            fixtures.write("shared/example.cases.json", &shared);
            fixtures.write("extra/example.cases.json", &extra);
            rejects(
                || {
                    fixtures.cases();
                },
                &["example.cases.json", origin, "set must be an object"],
            );
        }
    }
}
