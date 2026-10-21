//! Analytics event allow list (02_구현계약 §3.2, C-17): `packages/schemas/analytics-events.json`.
//!
//! Only the listed fields may leave the device, and only with the listed value shapes.
//! [`AllowList::check_event`] rejects an event that has a field outside its allow list,
//! lacks a required field, or carries a value of the wrong shape (free text, nested
//! objects, a status that is not a vocabulary value). The leak scanner of T-CT-06 uses
//! [`AllowList::is_allowed_field`] on the code side. `codegen/check_allowlist.py` is the Python
//! twin for Python tools; the `examples` in the JSON file pin both implementations to the same
//! answers (every listed example must pass or fail identically in both).

use serde::Deserialize;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

const SOURCE: &str = include_str!("../analytics-events.json");
const VOCABULARY: &str = include_str!("../vocabulary.json");

#[derive(Debug, Clone, Deserialize)]
pub struct AllowList {
    pub contracts_version: String,
    pub event_key: String,
    pub allowed_fields: BTreeMap<String, FieldRule>,
    pub forbidden_categories: Vec<Forbidden>,
    pub events: BTreeMap<String, EventRule>,
    pub examples: Examples,
}

#[derive(Debug, Clone, Deserialize)]
pub struct FieldRule {
    pub kind: String,
    #[serde(default)]
    pub axes: Vec<String>,
    pub max_len: Option<usize>,
    pub minimum: Option<i64>,
    #[serde(default)]
    pub only_events: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Forbidden {
    pub category_ko: String,
    pub name_hints: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct EventRule {
    pub required: Vec<String>,
    pub optional: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Examples {
    pub valid: Vec<Value>,
    pub rejected: Vec<Rejected>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Rejected {
    pub example: Value,
    pub reason_ko: String,
}

/// The allow list compiled into the crate.
pub fn allow_list() -> AllowList {
    serde_json::from_str(SOURCE).expect("analytics-events.json matches the allow list types")
}

/// Values of one vocabulary axis (codes only, never deprecated aliases).
fn axis_codes(axis: &str) -> Vec<String> {
    let vocab: Value = serde_json::from_str(VOCABULARY).expect("vocabulary.json parses");
    vocab["axes"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|a| a["id"] == axis)
        .flat_map(|a| a["values"].as_array().into_iter().flatten())
        .filter_map(|v| v["code"].as_str().map(str::to_string))
        .collect()
}

fn is_token(s: &str, max_len: usize) -> bool {
    let mut chars = s.chars();
    chars.next().is_some_and(|c| c.is_ascii_lowercase())
        && s.len() <= max_len
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || "_.-".contains(c))
}

fn all_digits(s: &str) -> bool {
    !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit())
}

fn is_semver(s: &str) -> bool {
    let parts: Vec<&str> = s.split('.').collect();
    parts.len() == 3 && parts.iter().all(|p| all_digits(p))
}

fn is_release_id(s: &str) -> bool {
    s.strip_prefix("rel:")
        .and_then(|r| r.split_once('-'))
        .is_some_and(|(date, n)| date.len() == 8 && all_digits(date) && all_digits(n))
}

impl AllowList {
    /// Whether any event may carry a field with this name.
    pub fn is_allowed_field(&self, name: &str) -> bool {
        self.allowed_fields.contains_key(name)
    }

    /// The forbidden category a field name looks like, for the failure message.
    fn forbidden_category(&self, name: &str) -> Option<&str> {
        let lower = name.to_ascii_lowercase();
        self.forbidden_categories
            .iter()
            .find(|c| c.name_hints.iter().any(|h| lower.contains(h.as_str())))
            .map(|c| c.category_ko.as_str())
    }

    /// Everything wrong with one event; empty when it may be sent.
    /// An event is a flat JSON object: `event` names it and the other keys are its fields.
    pub fn check_event(&self, event: &Value) -> Vec<String> {
        let Some(obj) = event.as_object() else {
            return vec!["an event must be a JSON object".into()];
        };
        let Some(name) = obj.get(&self.event_key).and_then(Value::as_str) else {
            return vec![format!("missing event name `{}`", self.event_key)];
        };
        let Some(rule) = self.events.get(name) else {
            return vec![format!("event `{name}` is not on the allow list")];
        };
        let mut out = Vec::new();
        for (field, value) in obj.iter().filter(|(k, _)| **k != self.event_key) {
            let permitted = rule.required.contains(field) || rule.optional.contains(field);
            if !permitted {
                let why = match (self.is_allowed_field(field), self.forbidden_category(field)) {
                    (true, _) => "allowed only on other events".to_string(),
                    (false, Some(c)) => format!("forbidden category: {c}"),
                    (false, None) => "not on the allow list".to_string(),
                };
                out.push(format!("{name}: field `{field}` {why}"));
                continue;
            }
            if let Some(problem) = self.check_value(field, value) {
                out.push(format!("{name}: field `{field}` {problem}"));
            }
        }
        for field in &rule.required {
            if !obj.contains_key(field) {
                out.push(format!("{name}: required field `{field}` is missing"));
            }
        }
        out
    }

    fn check_value(&self, field: &str, value: &Value) -> Option<String> {
        let rule = self.allowed_fields.get(field)?;
        let text = value.as_str();
        let bad = |what: &str| Some(format!("must be {what}"));
        match rule.kind.as_str() {
            "token" => match text {
                Some(s) if is_token(s, rule.max_len.unwrap_or(64)) => None,
                _ => bad("a lowercase token (a-z 0-9 _ . -), not free text"),
            },
            "vocabulary" => match text {
                Some(s)
                    if rule
                        .axes
                        .iter()
                        .any(|a| axis_codes(a).iter().any(|c| c == s)) =>
                {
                    None
                }
                _ => bad(&format!("a vocabulary value of {}", rule.axes.join(", "))),
            },
            "integer" => match value.as_i64() {
                Some(n) if n >= rule.minimum.unwrap_or(i64::MIN) => None,
                _ => bad("an integer within the minimum"),
            },
            "release_id" => match text {
                Some(s) if is_release_id(s) => None,
                _ => bad("rel:<yyyymmdd>-<n>"),
            },
            "semver" => match text {
                Some(s) if is_semver(s) => None,
                _ => bad("x.y.z"),
            },
            other => Some(format!("has unknown kind `{other}` in the allow list")),
        }
    }

    /// Everything wrong with the allow list itself.
    pub fn problems(&self) -> Vec<String> {
        let mut out = Vec::new();
        if self.contracts_version != crate::CONTRACTS_VERSION {
            out.push("contracts_version differs from the package version".to_string());
        }
        let known: BTreeSet<&str> = self.events.keys().map(String::as_str).collect();
        for (name, rule) in &self.events {
            for f in rule.required.iter().chain(&rule.optional) {
                let Some(fr) = self.allowed_fields.get(f) else {
                    out.push(format!("{name}: `{f}` is not an allowed field"));
                    continue;
                };
                if !fr.only_events.is_empty() && !fr.only_events.iter().any(|e| e == name) {
                    out.push(format!(
                        "{name}: `{f}` is restricted to {:?}",
                        fr.only_events
                    ));
                }
            }
        }
        for (f, fr) in &self.allowed_fields {
            for e in &fr.only_events {
                if !known.contains(e.as_str()) {
                    out.push(format!("{f}: only_events names unknown event {e}"));
                }
            }
            if self.forbidden_category(f).is_some() {
                out.push(format!(
                    "{f}: an allowed field looks like a forbidden category"
                ));
            }
            for a in &fr.axes {
                if axis_codes(a).is_empty() {
                    out.push(format!("{f}: vocabulary axis {a} does not exist"));
                }
            }
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn allowlist_file_is_consistent() {
        assert_eq!(allow_list().problems(), Vec::<String>::new());
    }

    #[test]
    fn allowlist_listed_examples_pass_and_fail_as_declared() {
        let a = allow_list();
        assert!(!a.examples.valid.is_empty() && !a.examples.rejected.is_empty());
        for ok in &a.examples.valid {
            assert_eq!(a.check_event(ok), Vec::<String>::new(), "{ok}");
        }
        for bad in &a.examples.rejected {
            assert!(!a.check_event(&bad.example).is_empty(), "{}", bad.reason_ko);
        }
    }

    #[test]
    fn allowlist_event_with_a_field_outside_the_list_fails() {
        let a = allow_list();
        for (field, value) in [
            ("contract_amount", json!(53000)),
            ("coverage_name", json!("암진단")),
            ("family_history", json!(true)),
            ("dna_marker", json!("x")),
            ("free_text", json!("hello")),
            ("document_excerpt", json!("...")),
            ("user_id", json!("u-1")),
            ("session_id", json!("s-1")),
            ("something_new", json!(1)),
        ] {
            let e = json!({"event": "screen_view", "screen_id": "home", field: value});
            let problems = a.check_event(&e);
            assert_eq!(problems.len(), 1, "{field}: {problems:?}");
            assert!(problems[0].contains(field));
        }
        let e = json!({"event": "screen_view", "screen_id": "home", "coverage_name": "x"});
        assert!(a.check_event(&e)[0].contains("forbidden category"));
    }

    #[test]
    fn allowlist_checks_required_fields_and_event_names() {
        let a = allow_list();
        assert!(!a
            .check_event(&json!({"event": "state_shown", "screen_id": "home"}))
            .is_empty());
        assert!(!a.check_event(&json!({"screen_id": "home"})).is_empty());
        assert!(!a.check_event(&json!({"event": "page_hit"})).is_empty());
        assert!(!a.check_event(&json!("screen_view")).is_empty());
        // `purpose` is allowed, but only on consent_changed.
        let e = json!({"event": "screen_view", "screen_id": "home", "purpose": "p"});
        assert!(a.check_event(&e)[0].contains("other events"));
        let e = json!({"event": "consent_changed", "screen_id": "s", "purpose": "health_analysis"});
        assert!(a.check_event(&e).is_empty());
    }

    #[test]
    fn allowlist_checks_value_shapes() {
        let a = allow_list();
        let with = |k: &str, v: Value| {
            let mut e = json!({"event": "api_latency", "latency_ms": 5});
            e[k] = v;
            a.check_event(&e)
        };
        assert!(with("latency_ms", json!(0)).is_empty());
        assert!(!with("latency_ms", json!(-1)).is_empty());
        assert!(!with("latency_ms", json!(1.5)).is_empty());
        assert!(!with("latency_ms", json!("5")).is_empty());
        assert!(!with("screen_id", json!("내 설계")).is_empty());
        assert!(!with("screen_id", json!("Home")).is_empty());
        assert!(!with("screen_id", json!("a".repeat(65))).is_empty());
        assert!(!with("screen_id", json!({"a": 1})).is_empty());
        assert!(!with("screen_id", Value::Null).is_empty());
        assert!(with("release_id", json!("rel:20261017-1")).is_empty());
        assert!(!with("release_id", json!("rel:2026-1")).is_empty());
        assert!(with("app_version", json!("1.12.0")).is_empty());
        assert!(!with("app_version", json!("1.0")).is_empty());
        let state = |s: &str| {
            a.check_event(&json!({"event": "state_shown", "screen_id": "h", "state_code": s}))
        };
        assert!(state("hold").is_empty());
        assert!(state("blocked").is_empty());
        assert!(!state("persona_x").is_empty());
        assert!(!state("").is_empty());
        let class = |s: &str| {
            a.check_event(&json!({"event": "error_shown", "screen_id": "h", "error_class": s}))
        };
        // The same vocabulary value the wire `ErrorResponse.error_class` carries.
        assert!(class("timeout").is_empty());
        assert!(class("internal").is_empty());
        assert!(!class("T").is_empty());
        assert!(!class("Z").is_empty());
        assert!(!class("VA").is_empty());
        assert!(class("T")[0].contains("vocabulary value of error_class"));
    }

    #[test]
    fn allowlist_field_names_for_the_leak_scanner() {
        let a = allow_list();
        for f in [
            "screen_id",
            "state_code",
            "latency_ms",
            "error_class",
            "release_id",
            "app_version",
        ] {
            assert!(a.is_allowed_field(f), "{f}");
        }
        assert!(!a.is_allowed_field("user_id"));
    }

    #[test]
    fn allowlist_listing_a_forbidden_looking_field_is_a_problem() {
        let mut a = allow_list();
        let rule = a.allowed_fields["screen_id"].clone();
        a.allowed_fields.insert("coverage_name".into(), rule);
        assert!(a
            .problems()
            .iter()
            .any(|p| p.contains("forbidden category")));
        let mut a = allow_list();
        a.events
            .get_mut("screen_view")
            .unwrap()
            .optional
            .push("ghost".into());
        assert!(a.problems().iter().any(|p| p.contains("ghost")));
    }
}
